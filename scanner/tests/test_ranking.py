"""Tests for top-gainers ranking."""
from ranking import top_gainers


def ticker(symbol: str, pct: str) -> dict:
    return {"symbol": symbol, "priceChangePercent": pct}


def test_sorts_descending_and_ranks():
    ranked = top_gainers(
        [ticker("AUSDT", "5.0"), ticker("BUSDT", "12.3"), ticker("CUSDT", "-2.0")],
        top_n=10,
    )
    assert [r.symbol for r in ranked] == ["BUSDT", "AUSDT", "CUSDT"]
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_keeps_only_top_n():
    tickers = [ticker(f"COIN{i}USDT", str(i)) for i in range(20)]
    ranked = top_gainers(tickers, top_n=10)
    assert len(ranked) == 10
    assert ranked[0].price_change_percent == 19.0


def test_filters_non_usdt_and_quarterlies():
    ranked = top_gainers(
        [
            ticker("BTCUSDT", "1.0"),
            ticker("BTCBUSD", "99.0"),
            ticker("BTCUSDT_250926", "50.0"),
        ],
        top_n=10,
    )
    assert [r.symbol for r in ranked] == ["BTCUSDT"]


def test_bad_percent_treated_as_zero():
    ranked = top_gainers(
        [ticker("AUSDT", "not-a-number"), ticker("BUSDT", "3.0")], top_n=10
    )
    assert ranked[0].symbol == "BUSDT"
