#!/usr/bin/env python3
"""
EMA200 Touch Monitor — Breakout Prop
=====================================
Watches every coin in data/symbols.txt and fires a Discord alert whenever
the last CLOSED candle touches EMA200 on any of: 1H, 2H, 4H, 12H, 1D.

"Touch" = candle wick range (low–high) crosses the EMA200 level,
          OR closing price is within NEAR_TOUCH_PCT% of EMA200.

Usage:
  python ema_touch_monitor.py                  # scan once and exit
  python ema_touch_monitor.py --schedule       # run at every 1H close
  python ema_touch_monitor.py --schedule --now # run now, then hourly
  python ema_touch_monitor.py --symbol BTCUSDT # single-symbol debug scan
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# ── tunables ───────────────────────────────────────────────────────────────────

BINANCE_BASE   = "https://fapi.binance.com"
KLINE_LIMIT    = 250          # must be >200 for reliable EMA200 warm-up
REQUEST_DELAY  = 0.12         # seconds between Binance calls
NEAR_TOUCH_PCT = 0.30         # close within 0.30% of EMA200 triggers "near" alert
SCHEDULE_BUFFER_SEC = 20      # extra seconds after candle close before scanning

MONITOR_TIMEFRAMES: Dict[str, str] = {
    "1H":  "1h",
    "2H":  "2h",
    "4H":  "4h",
    "12H": "12h",
    "1D":  "1d",
}

# Minimum hours before re-alerting the same symbol on the same timeframe.
# Set to ~2× candle duration so the same candle never fires twice.
COOLDOWN_HOURS: Dict[str, int] = {
    "1H":  2,
    "2H":  4,
    "4H":  9,
    "12H": 25,
    "1D":  50,
}

BASE_DIR     = Path(__file__).parent
SYMBOLS_FILE = BASE_DIR / "data" / "symbols.txt"
STATE_FILE   = BASE_DIR / "data" / "ema_touch_state.json"

MAX_DISCORD_MSG = 1980        # Discord 2000-char limit with safety margin


# ── helpers ────────────────────────────────────────────────────────────────────

def _fp(v: float) -> str:
    """Format price intelligently."""
    if v >= 10_000: return f"{v:,.1f}"
    if v >= 1_000:  return f"{v:,.2f}"
    if v >= 10:     return f"{v:,.3f}"
    if v >= 1:      return f"{v:,.4f}"
    if v >= 0.01:   return f"{v:,.5f}"
    return f"{v:,.8f}"


def _split_messages(text: str) -> List[str]:
    """Split on newline boundaries keeping each chunk ≤ MAX_DISCORD_MSG."""
    if len(text) <= MAX_DISCORD_MSG:
        return [text]
    chunks, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > MAX_DISCORD_MSG:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


# ── symbol loader ──────────────────────────────────────────────────────────────

def load_symbols() -> List[str]:
    symbols: List[str] = []
    with open(SYMBOLS_FILE) as fh:
        for line in fh:
            sym = line.split("#")[0].strip()
            if sym:
                symbols.append(sym.upper())
    return symbols


# ── state (cooldown) persistence ───────────────────────────────────────────────

def load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: Dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _state_key(symbol: str, tf: str) -> str:
    return f"{symbol}_{tf}"


def is_on_cooldown(state: Dict, symbol: str, tf: str) -> bool:
    last = state.get(_state_key(symbol, tf))
    if not last:
        return False
    last_dt  = datetime.fromisoformat(last)
    cooldown = timedelta(hours=COOLDOWN_HOURS[tf])
    return (datetime.now(timezone.utc) - last_dt) < cooldown


def mark_alerted(state: Dict, symbol: str, tf: str) -> None:
    state[_state_key(symbol, tf)] = datetime.now(timezone.utc).isoformat()


# ── Binance kline fetch ────────────────────────────────────────────────────────

def fetch_klines(symbol: str, interval: str) -> Optional[List]:
    try:
        r = requests.get(
            f"{BINANCE_BASE}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": KLINE_LIMIT},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"    [API] {symbol} {interval}: {e}")
        return None


# ── EMA200 calculation ─────────────────────────────────────────────────────────

def calc_ema200(closes: List[float]) -> float:
    """Exponential moving average with span=200, adjust=False (matches pandas ewm)."""
    period = 200
    if len(closes) < period:
        return float("nan")
    k   = 2.0 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1.0 - k)
    return ema


# ── touch detection ────────────────────────────────────────────────────────────

def check_touch(symbol: str, tf_name: str, interval: str) -> Optional[Dict]:
    """
    Returns a touch-event dict if the last closed candle touches EMA200, else None.

    Touch types:
      TOUCH  — candle wick (low–high) crosses the EMA200 level
      NEAR   — closing price within NEAR_TOUCH_PCT% of EMA200
    """
    raw = fetch_klines(symbol, interval)
    if not raw or len(raw) < 210:
        return None

    candles = raw[:-1]                          # drop still-open last candle
    closes  = [float(c[4]) for c in candles]
    ema200  = calc_ema200(closes)
    if ema200 != ema200:                        # NaN guard
        return None

    last  = candles[-1]
    high  = float(last[2])
    low   = float(last[3])
    close = float(last[4])

    candle_touch = low <= ema200 <= high
    dist_pct     = abs(close - ema200) / ema200 * 100
    near_touch   = dist_pct <= NEAR_TOUCH_PCT

    if not (candle_touch or near_touch):
        return None

    return {
        "symbol":     symbol,
        "timeframe":  tf_name,
        "ema200":     round(ema200, 8),
        "price":      round(close,  8),
        "high":       round(high,   8),
        "low":        round(low,    8),
        "dist_pct":   round(dist_pct, 3),
        "direction":  "ABOVE" if close >= ema200 else "BELOW",
        "touch_type": "TOUCH" if candle_touch else "NEAR",
    }


# ── Discord sender ─────────────────────────────────────────────────────────────

def build_alert_text(events: List[Dict], ts: datetime) -> str:
    ts_str = ts.strftime("%Y-%m-%d  %H:%M  UTC")

    header = (
        "```\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  EMA200 TOUCH ALERT  ✦  Breakout Prop\n"
        f"  {ts_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "```\n"
    )

    # Group events by symbol, preserving TF order
    tf_order = list(MONITOR_TIMEFRAMES.keys())
    by_symbol: Dict[str, List[Dict]] = {}
    for ev in events:
        by_symbol.setdefault(ev["symbol"], []).append(ev)

    body = ""
    for symbol, evs in by_symbol.items():
        evs_sorted = sorted(evs, key=lambda x: tf_order.index(x["timeframe"]))

        # Determine dominant direction for icon
        above_count = sum(1 for e in evs_sorted if e["direction"] == "ABOVE")
        icon = "🟢" if above_count >= len(evs_sorted) / 2 else "🔴"

        body += f"**{icon} {symbol}**\n"
        for ev in evs_sorted:
            touch_icon = "📍" if ev["touch_type"] == "TOUCH" else "〰️"
            dir_label  = "from above" if ev["direction"] == "ABOVE" else "from below"
            body += (
                f"> {touch_icon} **{ev['timeframe']}**  "
                f"EMA200 `{_fp(ev['ema200'])}`  │  "
                f"Price `{_fp(ev['price'])}`  │  "
                f"`{ev['dist_pct']:.2f}%` away  │  {dir_label}\n"
            )
        body += "\n"

    footer = "*Algorithmic price alert — not financial advice.*\n"
    return header + body + footer


def send_alerts(webhook_url: str, events: List[Dict], ts: datetime) -> bool:
    if not webhook_url or not events:
        return False

    text     = build_alert_text(events, ts)
    messages = _split_messages(text)
    ok       = True

    for msg in messages:
        try:
            r = requests.post(webhook_url, json={"content": msg}, timeout=15)
            r.raise_for_status()
            time.sleep(0.5)
        except requests.RequestException as e:
            print(f"  [Discord] send failed: {e}")
            ok = False

    return ok


# ── scan loop ──────────────────────────────────────────────────────────────────

def run_scan(webhook_url: str, symbols: Optional[List[str]] = None) -> None:
    ts = datetime.now(timezone.utc)
    print(f"\n{'═'*55}")
    print(f"  EMA200 Touch Monitor  —  {ts:%Y-%m-%d %H:%M UTC}")
    print(f"{'═'*55}")

    if symbols is None:
        symbols = load_symbols()

    state  = load_state()
    events: List[Dict] = []

    total_checks = len(symbols) * len(MONITOR_TIMEFRAMES)
    skipped      = 0
    print(f"  Scanning {len(symbols)} symbols × {len(MONITOR_TIMEFRAMES)} timeframes "
          f"= {total_checks} checks")

    for symbol in symbols:
        for tf_name, interval in MONITOR_TIMEFRAMES.items():
            if is_on_cooldown(state, symbol, tf_name):
                skipped += 1
                continue

            ev = check_touch(symbol, tf_name, interval)
            time.sleep(REQUEST_DELAY)

            if ev:
                events.append(ev)
                mark_alerted(state, symbol, tf_name)
                tag = ev["touch_type"]
                print(f"    {tag:5s}  {symbol:<14} {tf_name:<4} "
                      f"EMA={_fp(ev['ema200'])}  "
                      f"price={_fp(ev['price'])}  "
                      f"dist={ev['dist_pct']:.2f}%  "
                      f"({ev['direction']})")

    save_state(state)

    print(f"\n  {len(events)} touch(es) found  |  {skipped} checks skipped (cooldown)")

    if events:
        if webhook_url:
            print("  Sending Discord alert...")
            ok = send_alerts(webhook_url, events, ts)
            print(f"  Discord: {'OK' if ok else 'FAILED'}")
        else:
            print("  [Discord] No webhook configured — alert suppressed.")
            print(build_alert_text(events, ts))
    else:
        print("  No EMA200 touches this scan.")


# ── hourly scheduler ───────────────────────────────────────────────────────────

def _next_hour_close() -> datetime:
    now    = datetime.now(timezone.utc)
    next_h = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_h


def run_scheduler(webhook_url: str, run_immediately: bool = False) -> None:
    if run_immediately:
        run_scan(webhook_url)

    while True:
        target    = _next_hour_close()
        delay_sec = (target - datetime.now(timezone.utc)).total_seconds() + SCHEDULE_BUFFER_SEC
        print(f"\n  Next scan at {target:%H:%M UTC}  (in {delay_sec / 60:.1f} min)  [Ctrl-C to stop]")
        time.sleep(max(delay_sec, 1))
        run_scan(webhook_url)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EMA200 Touch Monitor — alerts Discord on EMA200 touches",
    )
    parser.add_argument("--schedule", action="store_true",
                        help="Run at every 1H candle close (blocks forever)")
    parser.add_argument("--now",      action="store_true",
                        help="With --schedule: also run immediately on startup")
    parser.add_argument("--symbol",   type=str, default=None,
                        help="Scan a single symbol and exit (e.g. BTCUSDT)")
    args = parser.parse_args()

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        print("  WARNING: DISCORD_WEBHOOK_URL not set in .env — no Discord alerts will be sent.")

    if args.symbol:
        syms = [args.symbol.upper()]
        # Skip cooldown check for single-symbol debug mode
        state = {}
        events: List[Dict] = []
        for tf_name, interval in MONITOR_TIMEFRAMES.items():
            ev = check_touch(syms[0], tf_name, interval)
            time.sleep(REQUEST_DELAY)
            if ev:
                events.append(ev)
                tag = ev["touch_type"]
                print(f"  {tag:5s}  {syms[0]:<14} {tf_name:<4} "
                      f"EMA={_fp(ev['ema200'])}  price={_fp(ev['price'])}  "
                      f"dist={ev['dist_pct']:.2f}%")
        if events:
            if webhook:
                send_alerts(webhook, events, datetime.now(timezone.utc))
        else:
            print("  No EMA200 touches on any timeframe.")
    elif args.schedule:
        run_scheduler(webhook, run_immediately=args.now)
    else:
        run_scan(webhook)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Interrupted — exiting.")
        sys.exit(0)
