#!/usr/bin/env python3
"""
Breakout Prop — EMA200 Market Structure Bot
============================================
Analyses Binance USDT perpetual futures every 4H candle close.

Usage:
  python bot.py                     # Run once immediately
  python bot.py --schedule          # Wait for 4H closes then run
  python bot.py --schedule --now    # Run now, then continue on schedule
  python bot.py --symbol BTCUSDT    # Analyse a single symbol
"""

import sys
import argparse
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config
from src.fetcher          import fetch_all_data
from src.ema_analysis     import analyze_ema200
from src.market_structure import analyze_market_structure
from src.volume_analysis  import analyze_volume
from src.sr_analysis      import analyze_sr
from src.oi_analysis      import analyze_oi
from src.scorer           import calculate_score
from src.setup_generator  import generate_long_setup, generate_short_setup, TradeSetup
from src.chart_generator  import generate_chart
from src.discord_reporter import send_to_discord
from src.scheduler        import run_scheduler


# ── symbol loader ─────────────────────────────────────────────────────────────

def load_symbols() -> List[str]:
    symbols = []
    with open(config.SYMBOLS_FILE) as fh:
        for line in fh:
            sym = line.split("#")[0].strip()
            if sym:
                symbols.append(sym.upper())
    if not symbols:
        raise ValueError(f"No symbols found in {config.SYMBOLS_FILE}")
    return symbols


# ── report saver ─────────────────────────────────────────────────────────────

def save_report(lines: List[str], ts: datetime) -> str:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    name = ts.strftime("%Y-%m-%d_%H-%M") + ".txt"
    path = config.REPORTS_DIR / name
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ── single-symbol analysis ────────────────────────────────────────────────────

def analyze_symbol(symbol: str) -> Optional[Dict]:
    data = fetch_all_data(symbol)
    if data is None:
        return None

    try:
        df_d   = data["klines_daily"]
        df_4h  = data["klines_4h"]
        df_1h  = data["klines_1h"]
        df_15m = data["klines_15m"]

        price = float(df_4h["close"].iloc[-1])

        d_ema   = analyze_ema200(df_d,   "Daily")
        h4_ema  = analyze_ema200(df_4h,  "4H")
        h1_ema  = analyze_ema200(df_1h,  "1H")
        m15_ema = analyze_ema200(df_15m, "15M")

        structure = analyze_market_structure(df_4h)
        volume    = analyze_volume(df_4h)
        sr        = analyze_sr(df_4h, df_d)

        oi = analyze_oi(
            data.get("oi_history", []),
            data.get("stats", {}).get("price_change_pct", 0),
            data.get("funding_rate"),
        )

        long_score  = calculate_score(d_ema, h4_ema, h1_ema, structure, volume, oi, sr, "long")
        short_score = calculate_score(d_ema, h4_ema, h1_ema, structure, volume, oi, sr, "short")

        long_setup  = generate_long_setup(
            symbol, price, d_ema, h4_ema, h1_ema, m15_ema,
            structure, volume, sr, oi, long_score,
        )
        short_setup = generate_short_setup(
            symbol, price, d_ema, h4_ema, h1_ema, m15_ema,
            structure, volume, sr, oi, short_score,
        )

        return {
            "symbol":      symbol,
            "price":       price,
            "d_ema":       d_ema,
            "h4_ema":      h4_ema,
            "h1_ema":      h1_ema,
            "m15_ema":     m15_ema,
            "structure":   structure,
            "volume":      volume,
            "sr":          sr,
            "oi":          oi,
            "long_score":  long_score,
            "short_score": short_score,
            "long_setup":  long_setup,
            "short_setup": short_setup,
            "df_4h":       df_4h,
        }

    except Exception as e:
        print(f"  [Analyze] {symbol} error: {e}")
        traceback.print_exc()
        return None


# ── report builder ─────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    if v >= 1000: return f"{v:,.2f}"
    if v >= 1:    return f"{v:,.4f}"
    return f"{v:,.8f}"


def _setup_lines(setup: TradeSetup, rank: int) -> List[str]:
    return [
        f"  #{rank} {setup.symbol}",
        f"     Score       : {setup.score.total:.0f}/100  ({setup.score.conviction})",
        f"     Probability : {setup.probability:.0f}%",
        f"     Entry       : {_fmt(setup.entry_low)} — {_fmt(setup.entry_high)}",
        f"     Stop        : {_fmt(setup.stop_loss)}",
        f"     TP1/2/3     : {_fmt(setup.tp1)} / {_fmt(setup.tp2)} / {_fmt(setup.tp3)}",
        f"     R:R         : 1:{setup.risk_reward:.1f}",
        f"     Reasons     : {setup.reasoning[0] if setup.reasoning else 'N/A'}",
        "",
    ]


def build_text_report(
    results:    List[Dict],
    top_longs:  List[TradeSetup],
    top_shorts: List[TradeSetup],
    ts:         datetime,
) -> List[str]:
    lines = [
        "=" * 65,
        "  BREAKOUT PROP — EMA200 MARKET STRUCTURE REPORT",
        f"  Generated : {ts:%Y-%m-%d %H:%M:%S UTC}",
        f"  Symbols   : {len(results)} analysed",
        "=" * 65,
        "",
        "TOP LONG SETUPS",
        "-" * 40,
    ]
    for i, s in enumerate(top_longs, 1):
        lines.extend(_setup_lines(s, i))

    lines += ["TOP SHORT SETUPS", "-" * 40]
    for i, s in enumerate(top_shorts, 1):
        lines.extend(_setup_lines(s, i))

    lines += ["", "FULL MARKET SNAPSHOT", "-" * 40]
    for r in sorted(results, key=lambda x: max(x["long_score"].total,
                                                x["short_score"].total), reverse=True):
        ls, ss = r["long_score"], r["short_score"]
        lines.append(
            f"  {r['symbol']:<12}  Price {_fmt(r['price']):<16}"
            f"  Daily:{r['d_ema'].trend:<16}  4H:{r['h4_ema'].trend:<16}"
            f"  Struct:{r['structure'].pattern:<8}"
            f"  LongScore:{ls.total:>5.0f}  ShortScore:{ss.total:>5.0f}"
        )
        for reason in r["long_setup"].reasoning[:2] if r["long_setup"] else []:
            lines.append(f"              {reason}")
        lines.append("")

    return lines


# ── main analysis run ─────────────────────────────────────────────────────────

def run_analysis(symbols: Optional[List[str]] = None) -> None:
    ts = datetime.now(timezone.utc)
    print(f"\n{'═'*65}")
    print(f"  Breakout Prop EMA200 Bot  —  {ts:%Y-%m-%d %H:%M UTC}")
    print(f"{'═'*65}")

    if symbols is None:
        symbols = load_symbols()

    print(f"  Symbols to analyse: {len(symbols)}")
    results = []
    for sym in symbols:
        r = analyze_symbol(sym)
        if r:
            results.append(r)

    if not results:
        print("  No results — check API connectivity and symbol list.")
        return

    # ── rank setups ───────────────────────────────────────────────────────────
    valid_longs  = [r["long_setup"]  for r in results
                    if r["long_setup"]  and r["long_setup"].is_valid]
    valid_shorts = [r["short_setup"] for r in results
                    if r["short_setup"] and r["short_setup"].is_valid]

    top_longs  = sorted(valid_longs,  key=lambda x: x.score.total, reverse=True)[:config.TOP_N_SETUPS]
    top_shorts = sorted(valid_shorts, key=lambda x: x.score.total, reverse=True)[:config.TOP_N_SETUPS]

    print(f"\n  Valid long setups : {len(valid_longs)}   →  showing top {len(top_longs)}")
    print(f"  Valid short setups: {len(valid_shorts)}   →  showing top {len(top_shorts)}")

    # ── charts (top 3 longs + top 3 shorts, deduped) ─────────────────────────
    config.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_paths  = []
    charted_syms = set()
    top_all      = top_longs[:3] + top_shorts[:3]

    for setup in top_all:
        if setup.symbol in charted_syms:
            continue
        charted_syms.add(setup.symbol)
        res = next((r for r in results if r["symbol"] == setup.symbol), None)
        if res:
            print(f"  Generating chart for {setup.symbol}...")
            path = generate_chart(
                setup.symbol, res["df_4h"], res["h4_ema"], res["sr"], setup,
            )
            if path:
                chart_paths.append(path)

    # ── save text report ─────────────────────────────────────────────────────
    report_lines = build_text_report(results, top_longs, top_shorts, ts)
    report_path  = save_report(report_lines, ts)
    print(f"\n  Report saved → {report_path}")

    # ── console preview ───────────────────────────────────────────────────────
    print()
    for line in report_lines[:60]:
        print(line)
    if len(report_lines) > 60:
        print(f"  ... ({len(report_lines) - 60} more lines in file)")

    # ── discord ───────────────────────────────────────────────────────────────
    if config.DISCORD_WEBHOOK_URL:
        print("\n  Sending to Discord...")
        ok = send_to_discord(
            config.DISCORD_WEBHOOK_URL,
            top_longs, top_shorts, ts, chart_paths,
        )
        print(f"  Discord: {'OK' if ok else 'FAILED'}")
    else:
        print("\n  DISCORD_WEBHOOK_URL not set — skipping Discord send.")
        print("  Set it in .env or export DISCORD_WEBHOOK_URL=... to enable.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Breakout Prop EMA200 Market Structure Bot",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run on 4H Binance candle-close schedule (blocks forever)",
    )
    parser.add_argument(
        "--now", action="store_true",
        help="With --schedule: also run immediately on startup",
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="Analyse a single symbol (e.g. BTCUSDT) and exit",
    )
    args = parser.parse_args()

    if args.symbol:
        run_analysis(symbols=[args.symbol.upper()])
    elif args.schedule:
        run_scheduler(run_analysis, run_immediately=args.now)
    else:
        run_analysis()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Interrupted — exiting.")
        sys.exit(0)
