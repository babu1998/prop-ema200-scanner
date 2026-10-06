"""
Scoring engine — 100-point system.

4H EMA200         30
1H EMA200         15
Daily EMA200      15
Market Structure  20
Volume            10
Open Interest      5
Support/Resistance 5
"""

from dataclasses import dataclass
import config
from src.ema_analysis      import EMAResult
from src.market_structure  import StructureResult
from src.volume_analysis   import VolumeResult
from src.sr_analysis       import SRResult
from src.oi_analysis       import OIResult


@dataclass
class ScoreBreakdown:
    daily_ema_score:    float  # 0-15
    h4_ema_score:       float  # 0-30
    h1_ema_score:       float  # 0-15
    structure_score:    float  # 0-20
    volume_score:       float  # 0-10
    oi_score:           float  # 0-5
    sr_score:           float  # 0-5
    total:              float  # 0-100
    conviction:         str    # High Conviction / Good Setup / Neutral / Avoid


# ── EMA scoring ────────────────────────────────────────────────────────────────

def _score_ema(ema: EMAResult, weight: float, direction: str) -> float:
    long_map = {
        "Strong Bullish": 1.00,
        "Bullish":        0.70,
        "Neutral":        0.25,
        "Bearish":        0.05,
        "Strong Bearish": 0.00,
    }
    short_map = {
        "Strong Bearish": 1.00,
        "Bearish":        0.70,
        "Neutral":        0.25,
        "Bullish":        0.05,
        "Strong Bullish": 0.00,
    }
    m = long_map if direction == "long" else short_map
    return weight * m.get(ema.trend, 0)


# ── Structure scoring ───────────────────────────────────────────────────────────

def _score_structure(s: StructureResult, weight: float, direction: str) -> float:
    if direction == "long":
        if s.pattern == "Bullish":
            base = 0.80
            if s.bos_direction == "Bullish BOS":
                base = 1.00
            if s.choch:
                base = 0.55   # CHoCH is early-reversal — promising but risky
        elif s.pattern == "Range":
            base = 0.35
        else:
            base = 0.00
    else:
        if s.pattern == "Bearish":
            base = 0.80
            if s.bos_direction == "Bearish BOS":
                base = 1.00
            if s.choch:
                base = 0.55
        elif s.pattern == "Range":
            base = 0.35
        else:
            base = 0.00
    return weight * base


# ── OI scoring (direction-aware) ────────────────────────────────────────────────

def _score_oi(oi: OIResult, weight: float, direction: str) -> float:
    if direction == "long":
        factor = 0.90 if oi.bullish  else 0.20
    else:
        factor = 0.90 if oi.bearish  else 0.20
    # No data → neutral
    if oi.signal == "No Data":
        factor = 0.50
    return weight * factor


# ── S/R scoring ────────────────────────────────────────────────────────────────

def _score_sr(sr: SRResult, weight: float, direction: str) -> float:
    base = sr.score / 100
    # Bonus if price is at the *right* level for the direction
    if direction == "long"  and sr.at_support:
        base = min(base + 0.15, 1.0)
    if direction == "short" and sr.at_resistance:
        base = min(base + 0.15, 1.0)
    return weight * base


# ── Public API ─────────────────────────────────────────────────────────────────

def calculate_score(
    daily_ema: EMAResult,
    h4_ema:    EMAResult,
    h1_ema:    EMAResult,
    structure: StructureResult,
    volume:    VolumeResult,
    oi:        OIResult,
    sr:        SRResult,
    direction: str = "long",
) -> ScoreBreakdown:
    w = config.SCORING_WEIGHTS

    d_ema_s  = _score_ema(daily_ema,  w["daily_ema200"],       direction)
    h4_ema_s = _score_ema(h4_ema,     w["4h_ema200"],          direction)
    h1_ema_s = _score_ema(h1_ema,     w["1h_ema200"],          direction)
    str_s    = _score_structure(structure, w["market_structure"], direction)
    vol_s    = (volume.score / 100) * w["volume"]
    oi_s     = _score_oi(oi,           w["open_interest"],     direction)
    sr_s     = _score_sr(sr,           w["support_resistance"], direction)

    total = d_ema_s + h4_ema_s + h1_ema_s + str_s + vol_s + oi_s + sr_s

    t = config.SCORE_THRESHOLDS
    if total >= t["high_conviction"]:
        conviction = "High Conviction"
    elif total >= t["good_setup"]:
        conviction = "Good Setup"
    elif total >= t["neutral"]:
        conviction = "Neutral"
    else:
        conviction = "Avoid"

    return ScoreBreakdown(
        daily_ema_score  = round(d_ema_s,  1),
        h4_ema_score     = round(h4_ema_s, 1),
        h1_ema_score     = round(h1_ema_s, 1),
        structure_score  = round(str_s,    1),
        volume_score     = round(vol_s,    1),
        oi_score         = round(oi_s,     1),
        sr_score         = round(sr_s,     1),
        total            = round(total,    1),
        conviction       = conviction,
    )
