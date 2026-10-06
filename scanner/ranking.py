"""Top-gainers ranking from Binance futures 24h ticker data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils import safe_float


@dataclass(frozen=True)
class RankedSymbol:
    """A monitored symbol with its 24h gainers rank (1 = biggest gainer)."""

    symbol: str
    rank: int
    price_change_percent: float


def _is_usdt_perpetual(symbol: str) -> bool:
    """USDT-margined perpetuals only; quarterly contracts contain '_'."""
    return symbol.endswith("USDT") and "_" not in symbol


def top_gainers(
    tickers: list[dict[str, Any]], top_n: int
) -> list[RankedSymbol]:
    """Sort 24h tickers by priceChangePercent desc and keep the top N."""
    candidates = [
        (t["symbol"], safe_float(t.get("priceChangePercent")))
        for t in tickers
        if _is_usdt_perpetual(t.get("symbol", ""))
    ]
    candidates.sort(key=lambda item: item[1], reverse=True)
    return [
        RankedSymbol(symbol=sym, rank=i, price_change_percent=pct)
        for i, (sym, pct) in enumerate(candidates[:top_n], start=1)
    ]
