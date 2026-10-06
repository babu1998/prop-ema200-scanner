# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run analysis once immediately (all symbols in data/symbols.txt)
python bot.py

# Analyse a single symbol and exit
python bot.py --symbol BTCUSDT

# Run on 4H schedule (blocks — fires at 00/04/08/12/16/20 UTC + 10 s buffer)
python bot.py --schedule

# Run immediately then continue on 4H schedule
python bot.py --schedule --now

# Install dependencies
pip install -r requirements.txt --break-system-packages
```

## Environment

Copy `.env.example` → `.env` and set `DISCORD_WEBHOOK_URL`. Without it the bot runs fully but skips Discord delivery and prints a warning.

## Architecture

The pipeline is linear and stateless per run. `bot.py:run_analysis()` orchestrates the full loop:

```
fetch_all_data(symbol)           # src/fetcher.py  — 4 timeframes + OI + funding
    ↓
analyze_ema200(df, tf)           # src/ema_analysis.py   × 4 timeframes
analyze_market_structure(df_4h)  # src/market_structure.py
analyze_volume(df_4h)            # src/volume_analysis.py
analyze_sr(df_4h, df_daily)      # src/sr_analysis.py
analyze_oi(history, Δprice, fr)  # src/oi_analysis.py
    ↓
calculate_score(..., direction)  # src/scorer.py   — called twice (long + short)
    ↓
generate_long_setup(...)         # src/setup_generator.py
generate_short_setup(...)        # src/setup_generator.py
    ↓
[rank by score, take top 5 each]
    ↓
generate_chart(symbol, ...)      # src/chart_generator.py  — top 3+3, deduped
send_to_discord(...)             # src/discord_reporter.py
save_report(lines, ts)           # bot.py  → reports/YYYY-MM-DD_HH-MM.txt
```

## Key Design Decisions

**Scoring weights** live in `config.SCORING_WEIGHTS` (must sum to 100). The dominant factor is Daily EMA200 (30 pts) + 4H EMA200 (25 pts) = 55 pts maximum from EMA alone. Changing weights changes which setups surface.

**`is_valid` gate** in `setup_generator.py` is the hard filter applied *after* scoring. For longs: `daily_above AND 4h_above AND (Bullish_structure OR Range_with_strong_EMA) AND volume≥1.0x AND score≥50 AND rr≥3.0`. Short is the mirror. A setup can score 90/100 yet be `is_valid=False` if R:R math falls below 3.0.

**Structure detection** (`src/market_structure.py`) uses `SWING_LOOKBACK=3` bars each side for pivot highs/lows, then applies a 60%-majority vote over the last 4 pivots to classify Bullish/Bearish/Range. Raising `SWING_LOOKBACK` in `config.py` produces fewer but cleaner pivots; lowering it gets noisier classifications in choppy markets.

**Stop loss placement** drives all targets. For longs: `min(last_low * 0.997, nearest_support * 0.995)`. For shorts: `max(last_high * 1.003, nearest_resistance * 1.005)`. TP1/2/3 are anchored to 1×/2×/3× risk from entry mid. TP1 may snap to the nearest S/R level if within ±15% of raw TP1; TP3 extends (never compresses) to major S/R if that level is beyond the raw 3× target.

**Probability formula** (in `setup_generator._probability`): base = `35 + score × 0.43` (range ~35–78%), then +6 for dual Strong EMA alignment, +4 for BOS, +3 for clean HH+HL or LH+LL. Clamped to [15, 92].

## Symbol List (`data/symbols.txt`)

One USDT perpetual futures symbol per line; `#` comments are stripped. Symbols must exist on Binance Futures (`fapi.binance.com`). Symbols are skipped automatically if they have <210 daily candles or if Binance returns a 400. Known issues: MATICUSDT → use POLUSDT; SHIBUSDT and PEPEUSDT have insufficient daily history for EMA200 warmup.

## Data Flow Notes

- `fetch_all_data` returns `None` for any symbol that fails — that symbol is silently skipped.
- Klines are fetched with `limit=350` to allow EMA200 warm-up (`KLINE_LIMIT` in config). The last (still-open) candle is always dropped.
- OI history endpoint (`/futures/data/openInterestHist`) sometimes 400s for delisted or low-liquidity symbols; `oi_history` falls back to `[]` and the OI component scores neutral (5/10).
- All analysis modules use `pandas` DataFrames with a `DatetimeIndex` (UTC, timezone-naive).

## Output Locations

| Path | Content |
|---|---|
| `reports/YYYY-MM-DD_HH-MM.txt` | Full text report for every run |
| `charts/<SYMBOL>_4h.png` | 4H chart for top 3 longs + top 3 shorts (overwritten each run) |
