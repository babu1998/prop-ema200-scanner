"""Binance Futures public API — no keys required."""

import time
import requests
import pandas as pd
from typing import Optional, Dict, List
import config


def _get(endpoint: str, params: dict = None, timeout: int = 10) -> Optional[object]:
    url = f"{config.BINANCE_FUTURES_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"    [API] {endpoint} error: {e}")
        return None


def get_klines(symbol: str, interval: str, limit: int = 350) -> Optional[pd.DataFrame]:
    data = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data:
        return None

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    # Drop the last (still-open) candle
    return df.iloc[:-1]


def get_24h_stats(symbol: str) -> Dict:
    data = _get("/fapi/v1/ticker/24hr", {"symbol": symbol})
    if data:
        return {
            "price_change_pct": float(data.get("priceChangePercent", 0)),
            "high":             float(data.get("highPrice",          0)),
            "low":              float(data.get("lowPrice",           0)),
            "volume":           float(data.get("volume",             0)),
            "last_price":       float(data.get("lastPrice",          0)),
        }
    return {}


def get_open_interest(symbol: str) -> Optional[float]:
    data = _get("/fapi/v1/openInterest", {"symbol": symbol})
    return float(data["openInterest"]) if data else None


def get_oi_history(symbol: str, period: str = "4h", limit: int = 10) -> List[Dict]:
    data = _get("/futures/data/openInterestHist", {
        "symbol": symbol,
        "period": period,
        "limit":  limit,
    })
    if not data:
        return []
    return [{"oi": float(d["sumOpenInterest"]), "ts": d["timestamp"]} for d in data]


def get_funding_rate(symbol: str) -> Optional[float]:
    data = _get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1})
    if data and len(data) > 0:
        return float(data[0].get("fundingRate", 0))
    return None


def fetch_all_data(symbol: str) -> Optional[Dict]:
    """Fetch all timeframe klines + auxiliary data for one symbol."""
    print(f"  Fetching {symbol}...")
    result: Dict = {"symbol": symbol}

    for tf_name, tf_interval in config.TIMEFRAMES.items():
        df = get_klines(symbol, tf_interval, config.KLINE_LIMIT)
        if df is None or len(df) < config.EMA_PERIOD + 10:
            print(f"    Skipping {symbol}: insufficient {tf_name} data "
                  f"(need {config.EMA_PERIOD + 10})")
            return None
        result[f"klines_{tf_name}"] = df
        time.sleep(config.REQUEST_DELAY)

    result["stats"]        = get_24h_stats(symbol)
    time.sleep(config.REQUEST_DELAY)
    result["oi_current"]   = get_open_interest(symbol)
    time.sleep(config.REQUEST_DELAY)
    result["oi_history"]   = get_oi_history(symbol)
    time.sleep(config.REQUEST_DELAY)
    result["funding_rate"] = get_funding_rate(symbol)
    time.sleep(config.REQUEST_DELAY)

    return result
