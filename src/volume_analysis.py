"""Volume analysis: expansion/contraction, breakout detection, 0-100 score."""

from dataclasses import dataclass
import pandas as pd
import config


@dataclass
class VolumeResult:
    current:    float
    average:    float    # 20-bar average of closed candles
    ratio:      float    # current / average
    expanding:  bool
    contracting: bool
    signal:     str      # Breakout Volume / Strong Participation / Normal / Weak Volume
    score:      float    # 0-100


def analyze_volume(df: pd.DataFrame, period: int = None) -> VolumeResult:
    if period is None:
        period = config.VOLUME_MA_PERIOD

    vols     = df["volume"]
    current  = float(vols.iloc[-1])
    # Average of the last `period` *completed* (pre-current) candles
    avg      = float(vols.iloc[-(period + 1):-1].mean())

    ratio = current / avg if avg > 0 else 1.0

    if ratio >= 2.5:
        signal, score = "Breakout Volume",      100
    elif ratio >= 1.75:
        signal, score = "Strong Participation",  80
    elif ratio >= 1.25:
        signal, score = "Above Average",         65
    elif ratio >= 0.85:
        signal, score = "Normal Volume",         50
    elif ratio >= 0.60:
        signal, score = "Below Average",         30
    else:
        signal, score = "Weak Volume",           15

    return VolumeResult(
        current     = round(current, 2),
        average     = round(avg,     2),
        ratio       = round(ratio,   2),
        expanding   = ratio >= 1.25,
        contracting = ratio < 0.75,
        signal      = signal,
        score       = score,
    )
