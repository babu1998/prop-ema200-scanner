"""Small shared helpers."""
from __future__ import annotations

import time
from datetime import datetime, timezone


def utc_now_ms() -> int:
    """Current UNIX epoch in milliseconds."""
    return int(time.time() * 1000)


def ms_to_iso(ms: int) -> str:
    """Millisecond epoch -> ISO-8601 UTC string (second precision)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def safe_float(value: object, default: float = 0.0) -> float:
    """Parse a float, returning ``default`` on any failure."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def fmt_funding(rate: float) -> str:
    """Format a raw funding rate (e.g. 0.0001) as a percent string."""
    return f"{rate * 100:+.4f}%"


def fmt_pct(pct: float, decimals: int = 2) -> str:
    """Format a percentage value with an explicit sign."""
    return f"{pct:+.{decimals}f}%"
