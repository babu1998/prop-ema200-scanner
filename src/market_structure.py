"""Market structure engine: swing detection, HH/HL/LH/LL, BOS, CHoCH."""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import pandas as pd
import config


@dataclass
class StructureResult:
    pattern:       str            # Bullish / Bearish / Range
    swing_highs:   List[float]    # Recent confirmed pivot highs (oldest → newest)
    swing_lows:    List[float]    # Recent confirmed pivot lows  (oldest → newest)
    last_high:     Optional[float]
    last_low:      Optional[float]
    prev_high:     Optional[float]
    prev_low:      Optional[float]
    bos:           bool           # Break of Structure
    choch:         bool           # Change of Character
    bos_direction: Optional[str]  # "Bullish BOS" | "Bearish BOS"
    hh_hl:         bool           # True when highs & lows both ascending
    lh_ll:         bool           # True when highs & lows both descending
    summary:       str            # Human-readable one-liner


def _pivot_highs(series: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """Pivot high: bar is >= all left neighbours and > all right neighbours."""
    pivots = []
    arr = series.values
    for i in range(left, len(arr) - right):
        if all(arr[i] >= arr[i - j] for j in range(1, left + 1)) and \
           all(arr[i] >  arr[i + j] for j in range(1, right + 1)):
            pivots.append((i, arr[i]))
    return pivots


def _pivot_lows(series: pd.Series, left: int, right: int) -> List[Tuple[int, float]]:
    """Pivot low: bar is <= all left neighbours and < all right neighbours."""
    pivots = []
    arr = series.values
    for i in range(left, len(arr) - right):
        if all(arr[i] <= arr[i - j] for j in range(1, left + 1)) and \
           all(arr[i] <  arr[i + j] for j in range(1, right + 1)):
            pivots.append((i, arr[i]))
    return pivots


def _is_ascending(seq: List[float]) -> bool:
    """Strict: every step must be higher."""
    return len(seq) >= 2 and all(seq[i] > seq[i - 1] for i in range(1, len(seq)))


def _is_descending(seq: List[float]) -> bool:
    """Strict: every step must be lower."""
    return len(seq) >= 2 and all(seq[i] < seq[i - 1] for i in range(1, len(seq)))


def _majority_ascending(seq: List[float]) -> bool:
    """True if ≥ 60% of consecutive steps are ascending."""
    if len(seq) < 2:
        return False
    ups = sum(seq[i] > seq[i - 1] for i in range(1, len(seq)))
    return ups / (len(seq) - 1) >= 0.60


def _majority_descending(seq: List[float]) -> bool:
    """True if ≥ 60% of consecutive steps are descending."""
    if len(seq) < 2:
        return False
    downs = sum(seq[i] < seq[i - 1] for i in range(1, len(seq)))
    return downs / (len(seq) - 1) >= 0.60


def analyze_market_structure(df: pd.DataFrame) -> StructureResult:
    lb = config.SWING_LOOKBACK
    ph = _pivot_highs(df["high"], lb, lb)
    pl = _pivot_lows( df["low"],  lb, lb)

    fallback_high = float(df["high"].tail(20).max())
    fallback_low  = float(df["low"].tail(20).min())

    if len(ph) < 2 or len(pl) < 2:
        return StructureResult(
            pattern="Range",
            swing_highs=[fallback_high],
            swing_lows=[fallback_low],
            last_high=fallback_high,
            last_low=fallback_low,
            prev_high=None,
            prev_low=None,
            bos=False,
            choch=False,
            bos_direction=None,
            hh_hl=False,
            lh_ll=False,
            summary="Range — insufficient swing data",
        )

    recent_highs = [p[1] for p in ph[-4:]]
    recent_lows  = [p[1] for p in pl[-4:]]

    highs_asc  = _majority_ascending(recent_highs)
    highs_desc = _majority_descending(recent_highs)
    lows_asc   = _majority_ascending(recent_lows)
    lows_desc  = _majority_descending(recent_lows)

    # Strict HH+HL / LH+LL check for clean trends
    hh_hl = _is_ascending(recent_highs)  and _is_ascending(recent_lows)
    lh_ll = _is_descending(recent_highs) and _is_descending(recent_lows)

    if highs_asc and lows_asc:
        pattern = "Bullish"
    elif highs_desc and lows_desc:
        pattern = "Bearish"
    elif lows_asc and not highs_desc:
        pattern = "Bullish"   # HL forming — accumulation bias
    elif highs_desc and not lows_asc:
        pattern = "Bearish"   # LH forming — distribution bias
    else:
        pattern = "Range"

    last_high = ph[-1][1]
    last_low  = pl[-1][1]
    prev_high = ph[-2][1] if len(ph) >= 2 else None
    prev_low  = pl[-2][1] if len(pl) >= 2 else None

    current_price = float(df["close"].iloc[-1])

    # BOS: price closes beyond the *previous* confirmed swing
    bos           = False
    bos_direction = None
    if prev_high and current_price > prev_high:
        bos           = True
        bos_direction = "Bullish BOS"
    elif prev_low and current_price < prev_low:
        bos           = True
        bos_direction = "Bearish BOS"

    # CHoCH: bos contradicts established pattern
    choch = bos and (
        (pattern == "Bullish"  and bos_direction == "Bearish BOS") or
        (pattern == "Bearish"  and bos_direction == "Bullish BOS")
    )

    # Human-readable summary
    h_label = "HH" if highs_asc else ("LH" if highs_desc else "EH")
    l_label = "HL" if lows_asc  else ("LL" if lows_desc  else "EL")
    parts = [f"{pattern} ({h_label}+{l_label})"]
    if bos:
        parts.append(bos_direction)
    if choch:
        parts.append("CHoCH")
    summary = " | ".join(parts)

    return StructureResult(
        pattern       = pattern,
        swing_highs   = [p[1] for p in ph[-6:]],
        swing_lows    = [p[1] for p in pl[-6:]],
        last_high     = last_high,
        last_low      = last_low,
        prev_high     = prev_high,
        prev_low      = prev_low,
        bos           = bos,
        choch         = choch,
        bos_direction = bos_direction,
        hh_hl         = hh_hl,
        lh_ll         = lh_ll,
        summary       = summary,
    )
