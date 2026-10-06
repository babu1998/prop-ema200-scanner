"""Optional open interest confirmation filter (bonus module).

When enabled (OI_FILTER_ENABLED=true) an alert is only sent if open interest
increased by at least OI_THRESHOLD percent over the last OI_LOOKBACK periods:
rising open interest means new positions are driving the divergence rather
than old positions closing out.

The filter fails OPEN — if Binance returns no data (common for freshly listed
or low-liquidity symbols) the alert goes through.
"""
from __future__ import annotations

import logging

from binance import BinanceClient, BinanceError
from utils import safe_float

logger = logging.getLogger("oi_filter")


async def oi_change_pct(
    client: BinanceClient, symbol: str, period: str, lookback: int
) -> float | None:
    """Percent change of open interest over the lookback window, or None."""
    try:
        history = await client.open_interest_hist(symbol, period, lookback)
    except BinanceError as exc:
        logger.warning("OI history unavailable for %s: %s", symbol, exc)
        return None
    if len(history) < 2:
        return None
    first = safe_float(history[0].get("sumOpenInterest"))
    last = safe_float(history[-1].get("sumOpenInterest"))
    if first == 0:
        return None
    return (last - first) / first * 100.0


async def oi_confirms(
    client: BinanceClient,
    symbol: str,
    period: str,
    lookback: int,
    threshold_pct: float,
) -> tuple[bool, str | None]:
    """Return (passes, note). Fails open when data is unavailable."""
    change = await oi_change_pct(client, symbol, period, lookback)
    if change is None:
        return True, None
    note = f"{change:+.2f}% over last {lookback}×{period}"
    return change >= threshold_pct, note
