# Binance Futures Funding Divergence Scanner

Continuously monitors the strongest-trending Binance USDⓈ-M futures and sends
a Discord webhook alert whenever **funding rate movement diverges from price
movement** — e.g. price rising while funding is falling. Built entirely on
Binance's **free public APIs** (no API key required).

## How it works

1. **Every hour** — download 24h ticker stats for all USDⓈ-M futures, sort by
   `priceChangePercent` descending, keep the **top 10 gainers**. Only these
   are monitored until the next refresh.
2. **Every 5 minutes** — for each monitored symbol, fetch the current funding
   rate and mark price, store a snapshot in SQLite, and compare it with the
   previous snapshot.
3. **Spot filter** (refreshed every 6 h from spot `exchangeInfo`):
   - Positive funding → only monitored if **no** spot market exists.
   - Negative funding → only monitored if a spot market **exists**.
   - Zero funding → ignored.
4. **Funding quotient** = `(current − previous) / abs(previous)`
   (division-by-zero safe: a zero previous funding never alerts).
5. **Alert** when *one* of these divergences occurs:
   - Price **up** ≥ 1 % **and** funding quotient **down** ≥ 20 %
   - Price **down** ≥ 1 % **and** funding quotient **up** ≥ 20 %

   Same-direction moves are ignored, and a symbol never alerts more than once
   per 30 minutes.

## Architecture

```
                       ┌────────────────────────────────────────────┐
                       │              APScheduler (UTC)             │
                       │  scan: 5 min · top: 1 h · spot: 6 h        │
                       └───────┬──────────────┬────────────┬────────┘
                               │              │            │
                        scan() │  refresh_top()│   refresh_spot()
                               ▼              ▼            ▼
┌──────────────┐      ┌─────────────────────────────────────────────┐
│ binance.py   │◄────►│                 main.Scanner                │
│ aiohttp      │      │  per-symbol pipeline (concurrent):          │
│ retry+backoff│      │  premiumIndex → snapshot → spot filter      │
└──────────────┘      │  → divergence → cooldown → [OI filter]      │
                      │  → [chart] → Discord / [Telegram]           │
                      └───────┬────────────────────────┬────────────┘
                              │                        │
                              ▼                        ▼
                      ┌──────────────┐         ┌───────────────────┐
                      │ database.py  │         │ alerts.py         │
                      │ SQLite       │         │ Discord webhook   │
                      │ snapshots    │         │ embed + PNG       │
                      │ alerts       │         └───────────────────┘
                      └──────────────┘
```

Every module is independent and unit-testable: `ranking.py` (top gainers),
`price.py` (price math), `funding.py` (quotient + divergence + spot rules),
`database.py` (persistence), `alerts.py` (Discord). Optional bonus modules:
`oi_filter.py`, `charting.py`, `leaderboard.py`, `telegram_alerts.py`,
`metrics.py`.

## Installation

```bash
git clone <repo>
cd scanner
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Setup

```bash
cp .env.example .env
# edit .env and set at minimum:
#   DISCORD_WEBHOOK=https://discord.com/api/webhooks/…
```

All `.env` settings (defaults shown in `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `BINANCE_BASE_URL` | `https://fapi.binance.com` | USDⓈ-M futures REST base |
| `BINANCE_SPOT_URL` | `https://api.binance.com` | Spot REST base |
| `DISCORD_WEBHOOK` | — | Discord webhook URL (required for alerts) |
| `PRICE_THRESHOLD` | `1.0` | Min \|price move\| in % |
| `FUNDING_THRESHOLD` | `20.0` | Min \|funding quotient\| in % |
| `TOP_COINS` | `10` | Number of top gainers to monitor |
| `SCAN_INTERVAL` | `300` | Seconds between scans |
| `TOP_REFRESH` | `3600` | Seconds between gainers refreshes |
| `SPOT_REFRESH` | `21600` | Seconds between spot exchangeInfo refreshes |
| `ALERT_COOLDOWN` | `1800` | Per-symbol alert dedupe window (s) |
| `DB_PATH` | `scanner.db` | SQLite file path |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_CONCURRENCY` | `8` | Max simultaneous Binance requests |

## Running

```bash
python main.py
```

The scanner performs an immediate spot refresh, top-gainers refresh and first
scan, then hands control to the scheduler. Stop with `Ctrl+C` (clean shutdown
on SIGINT/SIGTERM).

### Docker

```bash
docker compose up -d --build      # reads .env, persists DB in a volume
```

### Tests & lint

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check .
```

GitHub Actions (`.github/workflows/lint.yml`) runs ruff + pytest on every
push and pull request.

## Scheduler explanation

APScheduler's `AsyncIOScheduler` runs three (or four) interval jobs on the
asyncio event loop, all with `max_instances=1` and `coalesce=True` so a slow
cycle can never overlap or pile up behind the next trigger:

| Job | Interval | What it does |
|---|---|---|
| `scan` | `SCAN_INTERVAL` (5 min) | Snapshot + divergence check for all monitored symbols, fetched concurrently |
| `refresh_top` | `TOP_REFRESH` (1 h) | Rebuild the monitored top-gainers set |
| `refresh_spot` | `SPOT_REFRESH` (6 h) | Refresh the spot symbol list |
| `leaderboard` | `LEADERBOARD_INTERVAL` (1 h, optional) | Post top funding movers |

## Binance API endpoints used

| Endpoint | Purpose | Cadence |
|---|---|---|
| `GET /fapi/v1/ticker/24hr` | 24h stats for all futures → top gainers | hourly |
| `GET /fapi/v1/premiumIndex?symbol=` | Mark price + last funding rate | every 5 min × 10 symbols |
| `GET /api/v3/exchangeInfo` (spot) | Which futures symbols have a spot pair | every 6 h |
| `GET /fapi/v1/fundingRate?symbol=` | Funding history for chart attachment | per alert (optional) |
| `GET /futures/data/openInterestHist` | Open interest confirmation filter | per alert (optional) |

Rate-limit safety: only ~10 lightweight requests per 5-minute scan, bounded
by a concurrency semaphore, with exponential-backoff retries and automatic
handling of HTTP 429/418 `Retry-After`. A failing symbol is logged and
skipped — the scan never crashes and continues with the remaining symbols.

## Database

SQLite, two tables (timestamps are UTC epoch milliseconds):

- **snapshots** — `id, symbol, timestamp, price, funding, funding_quotient`;
  pruned automatically after 7 days.
- **alerts** — `id, symbol, timestamp, alert_type`; used for the 30-minute
  per-symbol cooldown.

## Bonus modules (all optional, all off-by-default except charts)

| Module | Enable via | Behaviour |
|---|---|---|
| Open interest filter | `OI_FILTER_ENABLED=true` | Alert only if OI rose ≥ `OI_THRESHOLD`% over `OI_LOOKBACK`×`OI_PERIOD`; fails open if data is missing |
| Funding history chart | `CHART_ENABLED=true` | Attaches a PNG of recent funding history to the Discord embed (needs matplotlib) |
| Funding movers leaderboard | `LEADERBOARD_ENABLED=true` | Hourly Discord embed of the biggest funding-quotient movers |
| Telegram alerts | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Mirrors every alert as a Telegram message |
| Prometheus metrics | `METRICS_ENABLED=true` | Exposes scan/alert/error counters, scan duration histogram and monitored-symbols gauge on `:9109` |
| Docker | — | `Dockerfile` + `docker-compose.yml` with persistent DB volume |
| CI linting | — | GitHub Actions: ruff + pytest |
| Unit tests | — | `tests/` covering quotient, divergence, spot rules, ranking, DB, leaderboard |

## Example alert

> **🚨 Funding Divergence**
> **Coin:** KORUSDT · **24h Rank:** #3
> **Price:** 12.44 → 12.71 (+2.17%)
> **Funding:** +0.0210% → +0.0150%
> **Funding Quotient:** −28.6%
> **Spot Available:** No
> **Signal:** Price ↑ Funding ↓
> *2026-07-30 12:05:00 UTC*
