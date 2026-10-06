"""Open Interest analysis: OI vs price direction, funding rate context."""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class OIResult:
    current_oi:      float
    oi_change_pct:   float
    price_change_pct: float
    signal:          str    # Long Accumulation / Short Covering / Short Building / Long Liquidation
    interpretation:  str
    bullish:         bool   # OI reading favours longs
    bearish:         bool   # OI reading favours shorts
    raw_score:       float  # 0-10 (direction-neutral quality; adjusted by scorer)


def analyze_oi(
    oi_history:      List[Dict],
    price_change_pct: float,
    funding_rate:    Optional[float] = None,
) -> OIResult:
    if not oi_history or len(oi_history) < 2:
        return OIResult(
            current_oi       = 0,
            oi_change_pct    = 0,
            price_change_pct = price_change_pct,
            signal           = "No Data",
            interpretation   = "Open interest data unavailable.",
            bullish          = False,
            bearish          = False,
            raw_score        = 5,
        )

    cur_oi  = oi_history[-1]["oi"]
    prev_oi = oi_history[0]["oi"]
    oi_chg  = (cur_oi - prev_oi) / prev_oi * 100 if prev_oi else 0

    price_up = price_change_pct > 0
    oi_up    = oi_chg > 0

    if price_up and oi_up:
        signal  = "Long Accumulation"
        interp  = ("Price rising with OI increasing — new longs entering. "
                   "Strong bullish trend continuation signal.")
        bullish, bearish = True, False
        raw_score = 9
    elif price_up and not oi_up:
        signal  = "Short Covering"
        interp  = ("Price rising with OI declining — shorts closing. "
                   "Rally may lack fresh conviction; watch for fade.")
        bullish, bearish = True, False
        raw_score = 5
    elif not price_up and oi_up:
        signal  = "Short Building"
        interp  = ("Price falling with OI increasing — new shorts entering. "
                   "Strong bearish trend continuation signal.")
        bullish, bearish = False, True
        raw_score = 9
    else:
        signal  = "Long Liquidation"
        interp  = ("Price falling with OI declining — longs exiting. "
                   "Possible exhaustion of selling; watch for reversal.")
        bullish, bearish = False, True
        raw_score = 5

    # Funding rate colour
    if funding_rate is not None:
        if funding_rate > 0.01:
            interp += " Funding positive — longs paying shorts (crowded long)."
        elif funding_rate < -0.01:
            interp += " Funding negative — shorts paying longs (crowded short)."

    return OIResult(
        current_oi       = round(cur_oi,  2),
        oi_change_pct    = round(oi_chg,  2),
        price_change_pct = round(price_change_pct, 2),
        signal           = signal,
        interpretation   = interp,
        bullish          = bullish,
        bearish          = bearish,
        raw_score        = raw_score,
    )
