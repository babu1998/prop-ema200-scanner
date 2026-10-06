"""Tests for funding quotient, spot filter and divergence detection."""
from funding import (
    PRICE_DOWN_FUNDING_UP,
    PRICE_UP_FUNDING_DOWN,
    FundingSnapshot,
    detect_divergence,
    funding_quotient,
    spot_filter_passes,
)


def snap(price: float, funding: float, ts: int = 0) -> FundingSnapshot:
    return FundingSnapshot(symbol="TESTUSDT", timestamp=ts, price=price,
                           funding=funding)


class TestFundingQuotient:
    def test_decrease(self):
        assert funding_quotient(0.021, 0.015) == (0.015 - 0.021) / 0.021

    def test_increase_from_negative(self):
        assert funding_quotient(-0.01, -0.005) == 0.5

    def test_zero_previous_is_safe(self):
        assert funding_quotient(0.0, 0.01) is None


class TestSpotFilter:
    def test_positive_funding_requires_no_spot(self):
        assert spot_filter_passes(0.01, has_spot_market=False)
        assert not spot_filter_passes(0.01, has_spot_market=True)

    def test_negative_funding_requires_spot(self):
        assert spot_filter_passes(-0.01, has_spot_market=True)
        assert not spot_filter_passes(-0.01, has_spot_market=False)

    def test_zero_funding_ignored(self):
        assert not spot_filter_passes(0.0, has_spot_market=True)
        assert not spot_filter_passes(0.0, has_spot_market=False)


class TestDetectDivergence:
    def test_price_up_funding_down(self):
        div = detect_divergence(
            snap(12.44, 0.00021), snap(12.71, 0.00015, ts=1),
            price_threshold_pct=1.0, funding_threshold_pct=20.0,
        )
        assert div is not None
        assert div.alert_type == PRICE_UP_FUNDING_DOWN
        assert div.price_change_pct > 1.0
        assert div.quotient < 0

    def test_price_down_funding_up(self):
        div = detect_divergence(
            snap(100.0, 0.0001), snap(98.0, 0.0002, ts=1),
            price_threshold_pct=1.0, funding_threshold_pct=20.0,
        )
        assert div is not None
        assert div.alert_type == PRICE_DOWN_FUNDING_UP

    def test_same_direction_ignored(self):
        assert detect_divergence(
            snap(100.0, 0.0001), snap(105.0, 0.0002, ts=1), 1.0, 20.0,
        ) is None
        assert detect_divergence(
            snap(100.0, 0.0002), snap(95.0, 0.0001, ts=1), 1.0, 20.0,
        ) is None

    def test_small_price_move_ignored(self):
        assert detect_divergence(
            snap(100.0, 0.0002), snap(100.5, 0.0001, ts=1), 1.0, 20.0,
        ) is None

    def test_small_funding_change_ignored(self):
        assert detect_divergence(
            snap(100.0, 0.00100), snap(102.0, 0.00095, ts=1), 1.0, 20.0,
        ) is None

    def test_zero_previous_funding_is_safe(self):
        assert detect_divergence(
            snap(100.0, 0.0), snap(102.0, 0.0001, ts=1), 1.0, 20.0,
        ) is None
