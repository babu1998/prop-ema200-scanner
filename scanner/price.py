"""Price movement calculations."""
from __future__ import annotations


def price_change_pct(prev_price: float, curr_price: float) -> float | None:
    """Percent change between two prices; None if the base price is zero."""
    if prev_price == 0:
        return None
    return (curr_price - prev_price) / prev_price * 100.0
