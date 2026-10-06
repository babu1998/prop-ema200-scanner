"""Application configuration loaded from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _float(key: str, default: float) -> float:
    raw = os.getenv(key)
    try:
        return float(raw) if raw is not None else default
    except ValueError:
        return default


def _int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def _bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration."""

    # Endpoints / credentials
    binance_base_url: str
    binance_spot_url: str
    discord_webhook: str

    # Core thresholds
    price_threshold: float      # minimum |price move| in percent (e.g. 1.0)
    funding_threshold: float    # minimum |funding quotient| in percent (e.g. 20.0)

    # Scheduling
    top_coins: int
    scan_interval: int          # seconds between scans
    top_refresh: int            # seconds between top-gainers refreshes
    spot_refresh: int           # seconds between spot exchangeInfo refreshes
    alert_cooldown: int         # seconds of per-symbol alert deduplication

    # Infrastructure
    db_path: str
    log_level: str
    max_concurrency: int

    # Optional: open interest filter
    oi_filter_enabled: bool
    oi_period: str
    oi_lookback: int
    oi_threshold: float         # minimum OI increase in percent to confirm an alert

    # Optional: funding history chart attached to Discord alerts
    chart_enabled: bool
    chart_points: int

    # Optional: top funding movers leaderboard
    leaderboard_enabled: bool
    leaderboard_interval: int
    leaderboard_size: int

    # Optional: Telegram alerts
    telegram_bot_token: str
    telegram_chat_id: str

    # Optional: Prometheus metrics
    metrics_enabled: bool
    metrics_port: int

    @classmethod
    def load(cls) -> "Config":
        """Build a Config from the process environment."""
        return cls(
            binance_base_url=_str("BINANCE_BASE_URL", "https://fapi.binance.com"),
            binance_spot_url=_str("BINANCE_SPOT_URL", "https://api.binance.com"),
            discord_webhook=_str("DISCORD_WEBHOOK", ""),
            price_threshold=_float("PRICE_THRESHOLD", 1.0),
            funding_threshold=_float("FUNDING_THRESHOLD", 20.0),
            top_coins=_int("TOP_COINS", 10),
            scan_interval=_int("SCAN_INTERVAL", 300),
            top_refresh=_int("TOP_REFRESH", 3600),
            spot_refresh=_int("SPOT_REFRESH", 21600),
            alert_cooldown=_int("ALERT_COOLDOWN", 1800),
            db_path=_str("DB_PATH", "scanner.db"),
            log_level=_str("LOG_LEVEL", "INFO"),
            max_concurrency=_int("MAX_CONCURRENCY", 8),
            oi_filter_enabled=_bool("OI_FILTER_ENABLED", False),
            oi_period=_str("OI_PERIOD", "5m"),
            oi_lookback=_int("OI_LOOKBACK", 6),
            oi_threshold=_float("OI_THRESHOLD", 0.0),
            chart_enabled=_bool("CHART_ENABLED", True),
            chart_points=_int("CHART_POINTS", 48),
            leaderboard_enabled=_bool("LEADERBOARD_ENABLED", False),
            leaderboard_interval=_int("LEADERBOARD_INTERVAL", 3600),
            leaderboard_size=_int("LEADERBOARD_SIZE", 5),
            telegram_bot_token=_str("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=_str("TELEGRAM_CHAT_ID", ""),
            metrics_enabled=_bool("METRICS_ENABLED", False),
            metrics_port=_int("METRICS_PORT", 9109),
        )
