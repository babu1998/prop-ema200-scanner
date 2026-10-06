"""
Trade setup generator.

Long requirements : Daily above EMA200, 4H above EMA200, Bullish structure,
                    Volume >= 1.0x, R:R >= 3.0
Short requirements: Daily below EMA200, 4H below EMA200, Bearish structure,
                    Volume >= 1.0x, R:R >= 3.0
"""

from dataclasses import dataclass, field
from typing import List, Optional
import config
from src.ema_analysis      import EMAResult
from src.market_structure  import StructureResult
from src.volume_analysis   import VolumeResult
from src.sr_analysis       import SRResult
from src.oi_analysis       import OIResult
from src.scorer            import ScoreBreakdown


@dataclass
class TradeSetup:
    symbol:      str
    direction:   str          # LONG | SHORT
    probability: float        # 0-100
    entry_low:   float
    entry_high:  float
    stop_loss:   float
    tp1:         float
    tp2:         float
    tp3:         float
    invalidation: float
    risk_reward: float
    score:       ScoreBreakdown
    reasoning:   List[str] = field(default_factory=list)
    is_valid:    bool = False


# ── probability ────────────────────────────────────────────────────────────────

def _probability(
    score:     float,
    direction: str,
    d_ema:     EMAResult,
    h4_ema:    EMAResult,
    structure: StructureResult,
) -> float:
    # Base curve: score 0→35 %, score 100→78 %
    p = 35 + score * 0.43

    # Strong dual-EMA alignment bonus
    if direction == "long":
        if d_ema.trend in ("Strong Bullish",) and h4_ema.trend in ("Strong Bullish",):
            p += 6
        if structure.bos_direction == "Bullish BOS":
            p += 4
        if structure.hh_hl:
            p += 3
    else:
        if d_ema.trend in ("Strong Bearish",) and h4_ema.trend in ("Strong Bearish",):
            p += 6
        if structure.bos_direction == "Bearish BOS":
            p += 4
        if structure.lh_ll:
            p += 3

    return round(min(max(p, 15), 92), 1)


# ── reasoning builder ──────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:,.4f}"
    return f"{v:,.6f}"


def _build_reasoning(
    direction: str,
    d_ema:  EMAResult, h4_ema: EMAResult,
    h1_ema: EMAResult, m15_ema: EMAResult,
    structure: StructureResult,
    volume:    VolumeResult,
    oi:        OIResult,
    sr:        SRResult,
) -> List[str]:
    r = []

    pos_d = "above" if d_ema.price_above else "below"
    r.append(f"Price {pos_d} Daily EMA200 ({_fmt(d_ema.ema200)}) — {d_ema.trend} "
             f"[dist {d_ema.dist_pct:+.1f}%]")

    pos_4h = "above" if h4_ema.price_above else "below"
    r.append(f"Price {pos_4h} 4H EMA200 ({_fmt(h4_ema.ema200)}) — {h4_ema.trend} "
             f"[slope {h4_ema.slope_pct:+.3f}%/10bars]")

    r.append(f"Market structure: {structure.summary}")

    r.append(f"Volume: {volume.signal} — {volume.ratio:.2f}x the 20-bar average")

    r.append(f"OI: {oi.signal} — {oi.interpretation[:80]}")

    if direction == "long" and sr.at_support:
        r.append(f"Price at key support ({_fmt(sr.nearest_support)}) — "
                 f"confluence with entry zone")
    elif direction == "short" and sr.at_resistance:
        r.append(f"Price at key resistance ({_fmt(sr.nearest_resistance)}) — "
                 f"confluence with entry zone")
    else:
        nearest = sr.nearest_support if direction == "long" else sr.nearest_resistance
        dist = sr.dist_to_support_pct if direction == "long" else sr.dist_to_resistance_pct
        r.append(f"Nearest {'support' if direction == 'long' else 'resistance'}: "
                 f"{_fmt(nearest)} ({dist:.1f}% away)")

    # 1H/15M context
    r.append(f"1H EMA200: {h1_ema.trend} | 15M EMA200: {m15_ema.trend}")

    return r


# ── long setup ─────────────────────────────────────────────────────────────────

def generate_long_setup(
    symbol:    str,
    price:     float,
    d_ema:     EMAResult,
    h4_ema:    EMAResult,
    h1_ema:    EMAResult,
    m15_ema:   EMAResult,
    structure: StructureResult,
    volume:    VolumeResult,
    sr:        SRResult,
    oi:        OIResult,
    score:     ScoreBreakdown,
) -> TradeSetup:

    # Short-term gate: 4H + 1H alignment (daily is scored but not required)
    ema_ok   = h4_ema.price_above and h1_ema.price_above
    str_ok   = structure.pattern == "Bullish"
    str_ok_range = (
        structure.pattern == "Range" and
        h4_ema.trend in ("Strong Bullish", "Bullish") and
        h1_ema.trend in ("Strong Bullish", "Bullish") and
        score.total  >= config.SCORE_THRESHOLDS["good_setup"]
    )
    vol_ok   = volume.ratio >= 1.0
    is_valid = ema_ok and (str_ok or str_ok_range) and vol_ok and \
               score.total >= config.SCORE_THRESHOLDS["neutral"]

    # Entry zone: favour support or EMA200 retest
    sup_dist  = (price - sr.nearest_support) / price
    ema_dist  = abs(price - h4_ema.ema200)  / price

    if sr.at_support:
        mid   = sr.nearest_support
        e_low = mid * 0.997
        e_hi  = mid * 1.005
    elif ema_dist < 0.012:
        mid   = h4_ema.ema200
        e_low = mid * 0.997
        e_hi  = mid * 1.005
    else:
        mid   = price
        e_low = price * 0.997
        e_hi  = price * 1.005

    # Stop: below swing low (or support), with buffer
    swing_sl = structure.last_low * 0.997 if structure.last_low else mid * 0.95
    sup_sl   = sr.nearest_support * 0.995
    sl       = min(swing_sl, sup_sl)
    sl       = min(sl, mid * 0.97)   # cap stop at 3% below mid (short-term)

    risk = mid - sl
    if risk <= 0:
        risk = mid * 0.03

    tp1 = mid + risk * 1.0
    tp2 = mid + risk * 2.0
    tp3 = mid + risk * 3.0

    # Align TP1 to nearest resistance if it falls within ±15% of raw TP1
    if (sr.nearest_resistance > mid and
            tp1 * 0.85 < sr.nearest_resistance < tp1 * 1.15):
        tp1 = sr.nearest_resistance * 0.998
        tp2 = mid + risk * 2.0   # keep tp2/tp3 anchored to risk multiples
        tp3 = mid + risk * 3.0

    # Extend TP3 to major resistance only if it improves R:R (resistance is higher)
    if sr.major_resistance > tp3:
        tp3 = sr.major_resistance * 0.998

    rr = (tp3 - mid) / risk
    invalidation = sl * 0.995
    prob         = _probability(score.total, "long", d_ema, h4_ema, structure)
    reasoning    = _build_reasoning("long", d_ema, h4_ema, h1_ema, m15_ema,
                                     structure, volume, oi, sr)

    return TradeSetup(
        symbol      = symbol,
        direction   = "LONG",
        probability = prob,
        entry_low   = round(e_low, 8),
        entry_high  = round(e_hi,  8),
        stop_loss   = round(sl,    8),
        tp1         = round(tp1,   8),
        tp2         = round(tp2,   8),
        tp3         = round(tp3,   8),
        invalidation = round(invalidation, 8),
        risk_reward  = round(rr,   2),
        score        = score,
        reasoning    = reasoning,
        is_valid     = is_valid and rr >= config.MIN_RISK_REWARD,
    )


# ── short setup ────────────────────────────────────────────────────────────────

def generate_short_setup(
    symbol:    str,
    price:     float,
    d_ema:     EMAResult,
    h4_ema:    EMAResult,
    h1_ema:    EMAResult,
    m15_ema:   EMAResult,
    structure: StructureResult,
    volume:    VolumeResult,
    sr:        SRResult,
    oi:        OIResult,
    score:     ScoreBreakdown,
) -> TradeSetup:

    # Short-term gate: 4H + 1H alignment (daily is scored but not required)
    ema_ok   = not h4_ema.price_above and not h1_ema.price_above
    str_ok   = structure.pattern == "Bearish"
    str_ok_range = (
        structure.pattern == "Range" and
        h4_ema.trend in ("Strong Bearish", "Bearish") and
        h1_ema.trend in ("Strong Bearish", "Bearish") and
        score.total  >= config.SCORE_THRESHOLDS["good_setup"]
    )
    vol_ok   = volume.ratio >= 1.0
    is_valid = ema_ok and (str_ok or str_ok_range) and vol_ok and \
               score.total >= config.SCORE_THRESHOLDS["neutral"]

    res_dist  = (sr.nearest_resistance - price) / price
    ema_dist  = abs(price - h4_ema.ema200) / price

    if sr.at_resistance:
        mid   = sr.nearest_resistance
        e_low = mid * 0.995
        e_hi  = mid * 1.003
    elif ema_dist < 0.012:
        mid   = h4_ema.ema200
        e_low = mid * 0.995
        e_hi  = mid * 1.003
    else:
        mid   = price
        e_low = price * 0.995
        e_hi  = price * 1.003

    swing_sl = structure.last_high * 1.003 if structure.last_high else mid * 1.05
    res_sl   = sr.nearest_resistance * 1.005
    sl       = max(swing_sl, res_sl)
    sl       = max(sl, mid * 1.03)   # cap stop at 3% above mid (short-term)

    risk = sl - mid
    if risk <= 0:
        risk = mid * 0.03

    tp1 = mid - risk * 1.0
    tp2 = mid - risk * 2.0
    tp3 = mid - risk * 3.0

    # Align TP1 to nearest support if it falls within ±15% of raw TP1
    if (sr.nearest_support < mid and
            tp1 * 0.85 < sr.nearest_support < tp1 * 1.15):
        tp1 = sr.nearest_support * 1.002
        tp2 = mid - risk * 2.0   # keep tp2/tp3 anchored to risk multiples
        tp3 = mid - risk * 3.0

    # Extend TP3 to major support only if it improves R:R (support is lower)
    if 0 < sr.major_support < tp3:
        tp3 = sr.major_support * 1.002

    rr = (mid - tp3) / risk
    invalidation  = sl * 1.005
    prob          = _probability(score.total, "short", d_ema, h4_ema, structure)
    reasoning     = _build_reasoning("short", d_ema, h4_ema, h1_ema, m15_ema,
                                      structure, volume, oi, sr)

    return TradeSetup(
        symbol      = symbol,
        direction   = "SHORT",
        probability = prob,
        entry_low   = round(e_low, 8),
        entry_high  = round(e_hi,  8),
        stop_loss   = round(sl,    8),
        tp1         = round(tp1,   8),
        tp2         = round(tp2,   8),
        tp3         = round(tp3,   8),
        invalidation = round(invalidation, 8),
        risk_reward  = round(rr,   2),
        score        = score,
        reasoning    = reasoning,
        is_valid     = is_valid and rr >= config.MIN_RISK_REWARD,
    )
