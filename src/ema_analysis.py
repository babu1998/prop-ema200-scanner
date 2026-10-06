"""EMA200 calculation and multi-timeframe trend classification."""

from dataclasses import dataclass
import pandas as pd
import config


@dataclass
class EMAResult:
    timeframe:   str
    ema200:      float
    price:       float
    price_above: bool
    dist_pct:    float   # % distance from EMA200 (+ = above, - = below)
    slope_pct:   float   # EMA200 % change over last 10 bars
    trend:       str     # Strong Bullish / Bullish / Neutral / Bearish / Strong Bearish


def calculate_ema(series: pd.Series, period: int = 200) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def analyze_ema200(df: pd.DataFrame, timeframe: str) -> EMAResult:
    closes  = df["close"]
    ema     = calculate_ema(closes, config.EMA_PERIOD)

    current  = closes.iloc[-1]
    ema_now  = ema.iloc[-1]
    ema_back = ema.iloc[-11] if len(ema) > 11 else ema.iloc[0]

    price_above = current > ema_now
    dist_pct    = (current - ema_now) / ema_now * 100
    slope_pct   = (ema_now - ema_back) / ema_back * 100

    if price_above and slope_pct > 0.5:
        trend = "Strong Bullish"
    elif price_above and slope_pct > -0.15:
        trend = "Bullish"
    elif not price_above and slope_pct < -0.5:
        trend = "Strong Bearish"
    elif not price_above and slope_pct < 0.15:
        trend = "Bearish"
    else:
        trend = "Neutral"

    return EMAResult(
        timeframe   = timeframe,
        ema200      = round(ema_now,   8),
        price       = round(current,   8),
        price_above = price_above,
        dist_pct    = round(dist_pct,  2),
        slope_pct   = round(slope_pct, 4),
        trend       = trend,
    )
