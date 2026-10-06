"""Support & Resistance: nearest levels, daily majors, swing extremes."""

from dataclasses import dataclass
from typing import List
import pandas as pd
from src.market_structure import _pivot_highs, _pivot_lows
import config


@dataclass
class SRResult:
    nearest_support:    float
    nearest_resistance: float
    major_support:      float   # daily
    major_resistance:   float   # daily
    recent_swing_high:  float
    recent_swing_low:   float
    dist_to_support_pct:    float
    dist_to_resistance_pct: float
    at_support:    bool         # within 1.5%
    at_resistance: bool         # within 1.5%
    score:         float        # 0-100 (how close to a key level)


def _key_levels(df: pd.DataFrame, n: int = 10) -> List[float]:
    lb = config.SWING_LOOKBACK
    ph = _pivot_highs(df["high"], lb, lb)
    pl = _pivot_lows( df["low"],  lb, lb)
    levels = [p[1] for p in ph[-n:]] + [p[1] for p in pl[-n:]]
    return sorted(set(levels))


def analyze_sr(df_4h: pd.DataFrame, df_daily: pd.DataFrame) -> SRResult:
    price = float(df_4h["close"].iloc[-1])

    levels_4h = _key_levels(df_4h, n=12)
    supports_4h    = [l for l in levels_4h if l < price * 0.999]
    resistances_4h = [l for l in levels_4h if l > price * 1.001]

    nearest_sup = max(supports_4h)    if supports_4h    else price * 0.95
    nearest_res = min(resistances_4h) if resistances_4h else price * 1.05

    levels_d  = _key_levels(df_daily, n=6)
    sup_d     = [l for l in levels_d if l < price * 0.999]
    res_d     = [l for l in levels_d if l > price * 1.001]

    major_sup = max(sup_d) if sup_d else nearest_sup * 0.95
    major_res = min(res_d) if res_d else nearest_res * 1.05

    lb = config.SWING_LOOKBACK
    ph = _pivot_highs(df_4h["high"], lb, lb)
    pl = _pivot_lows( df_4h["low"],  lb, lb)

    recent_high = ph[-1][1] if ph else float(df_4h["high"].tail(20).max())
    recent_low  = pl[-1][1] if pl else float(df_4h["low"].tail(20).min())

    dist_sup = (price - nearest_sup) / price * 100
    dist_res = (nearest_res - price) / price * 100

    at_sup = dist_sup < 1.5
    at_res = dist_res < 1.5

    # Score: closer to a key level = better for entries
    min_dist = min(dist_sup, dist_res)
    if min_dist < 0.5:
        score = 100
    elif min_dist < 1.5:
        score = 80
    elif min_dist < 3.0:
        score = 55
    elif min_dist < 5.0:
        score = 35
    else:
        score = 15

    return SRResult(
        nearest_support         = round(nearest_sup,  8),
        nearest_resistance      = round(nearest_res,  8),
        major_support           = round(major_sup,    8),
        major_resistance        = round(major_res,    8),
        recent_swing_high       = round(recent_high,  8),
        recent_swing_low        = round(recent_low,   8),
        dist_to_support_pct     = round(dist_sup,     2),
        dist_to_resistance_pct  = round(dist_res,     2),
        at_support              = at_sup,
        at_resistance           = at_res,
        score                   = score,
    )
