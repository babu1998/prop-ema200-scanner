"""Funding snapshots, funding quotient and divergence detection."""
from __future__ import annotations

from dataclasses import dataclass

from price import price_change_pct

PRICE_UP_FUNDING_DOWN = "PRICE_UP_FUNDING_DOWN"
PRICE_DOWN_FUNDING_UP = "PRICE_DOWN_FUNDING_UP"


@dataclass(frozen=True)
class FundingSnapshot:
    """One observation of a symbol's mark price and funding rate."""

    symbol: str
    timestamp: int          # epoch ms, UTC
    price: float            # mark price
    funding: float          # raw funding rate, e.g. 0.0001 == 0.01%
    funding_quotient: float | None = None


@dataclass(frozen=True)
class Divergence:
    """A detected price/funding divergence ready to be alerted."""

    symbol: str
    alert_type: str
    timestamp: int
    prev_price: float
    curr_price: float
    price_change_pct: float
    prev_funding: float
    curr_funding: float
    quotient: float         # fractional, e.g. -0.28 == -28%

    @property
    def signal(self) -> str:
        if self.alert_type == PRICE_UP_FUNDING_DOWN:
            return "Price ↑  Funding ↓"
        return "Price ↓  Funding ↑"


def funding_quotient(prev_funding: float, curr_funding: float) -> float | None:
    """(current - previous) / abs(previous); None when previous is zero."""
    if prev_funding == 0:
        return None
    return (curr_funding - prev_funding) / abs(prev_funding)


def spot_filter_passes(current_funding: float, has_spot_market: bool) -> bool:
    """Apply the spot-market monitoring rules.

    - Positive funding: only monitor if NO spot market exists.
    - Negative funding: only monitor if a spot market exists.
    - Zero funding: ignored.
    """
    if current_funding > 0:
        return not has_spot_market
    if current_funding < 0:
        return has_spot_market
    return False


def detect_divergence(
    prev: FundingSnapshot,
    curr: FundingSnapshot,
    price_threshold_pct: float,
    funding_threshold_pct: float,
) -> Divergence | None:
    """Return a Divergence when price and funding move against each other.

    Alert cases:
      1. price rises  >= threshold while the funding quotient is <= -threshold
      2. price falls  >= threshold while the funding quotient is >= +threshold
    Same-direction moves are ignored.
    """
    change = price_change_pct(prev.price, curr.price)
    quotient = funding_quotient(prev.funding, curr.funding)
    if change is None or quotient is None:
        return None
    if abs(change) < price_threshold_pct:
        return None
    if abs(quotient) * 100.0 < funding_threshold_pct:
        return None

    if change > 0 and quotient < 0:
        alert_type = PRICE_UP_FUNDING_DOWN
    elif change < 0 and quotient > 0:
        alert_type = PRICE_DOWN_FUNDING_UP
    else:
        return None

    return Divergence(
        symbol=curr.symbol,
        alert_type=alert_type,
        timestamp=curr.timestamp,
        prev_price=prev.price,
        curr_price=curr.price,
        price_change_pct=change,
        prev_funding=prev.funding,
        curr_funding=curr.funding,
        quotient=quotient,
    )
