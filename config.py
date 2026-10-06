import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
CHARTS_DIR = BASE_DIR / "charts"

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

SYMBOLS_FILE = DATA_DIR / "symbols.txt"

BINANCE_FUTURES_BASE = "https://fapi.binance.com"

TIMEFRAMES = {
    "daily": "1d",
    "4h":    "4h",
    "1h":    "1h",
    "15m":   "15m",
}

KLINE_LIMIT     = 350   # need >200 for reliable EMA200 warm-up
EMA_PERIOD      = 200
VOLUME_MA_PERIOD = 20
SWING_LOOKBACK  = 2     # bars each side for pivot detection (2 = more sensitive)

# Scoring weights (must sum to 100)
# Shifted toward 4H+1H for short-term setup detection
SCORING_WEIGHTS = {
    "4h_ema200":          30,   # primary timeframe
    "1h_ema200":          15,   # short-term momentum
    "daily_ema200":       15,   # macro context (was dominant at 30)
    "market_structure":   20,
    "volume":             10,
    "open_interest":       5,
    "support_resistance":  5,
}

SCORE_THRESHOLDS = {
    "high_conviction": 75,
    "good_setup":      60,
    "neutral":         45,
}

MIN_RISK_REWARD = 2.0   # lowered from 3.0 for shorter-term setups
TOP_N_SETUPS    = 5
CHART_CANDLES   = 120   # candles to render in chart

REQUEST_DELAY   = 0.12  # seconds between Binance requests
