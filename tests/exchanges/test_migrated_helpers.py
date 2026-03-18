"""Selective migration tests for low-coupling exchange helpers."""

from decimal import Decimal

from app.exchanges.binance import classify_binance_http_error
from app.exchanges.common import exponential_backoff_seconds
from app.exchanges.common import meets_min_notional
from app.exchanges.common import select_preferred_step_size
from app.exchanges.common import snap_to_increment


def test_snap_to_increment_uses_decimal_flooring() -> None:
    assert snap_to_increment(Decimal("1.239"), Decimal("0.01")) == Decimal("1.23")
    assert snap_to_increment(Decimal("0"), Decimal("0.01")) == Decimal("0")


def test_select_preferred_step_size_prefers_market_specific_value() -> None:
    assert select_preferred_step_size(Decimal("0.001"), Decimal("0.01")) == Decimal("0.001")
    assert select_preferred_step_size(None, Decimal("0.01")) == Decimal("0.01")


def test_min_notional_helper_is_pure_and_boolean() -> None:
    assert meets_min_notional(
        quantity=Decimal("0.1"),
        price=Decimal("100"),
        min_notional=Decimal("10"),
    ) is True
    assert meets_min_notional(
        quantity=Decimal("0.01"),
        price=Decimal("100"),
        min_notional=Decimal("10"),
    ) is False


def test_backoff_allows_deterministic_jitter_for_tests() -> None:
    value = exponential_backoff_seconds(
        3,
        base_seconds=1.0,
        cap_seconds=30.0,
        jitter="full",
        rand_fn=lambda low, high: high / 2.0,
    )
    assert value == 4.0


def test_binance_error_classifier_adapts_reference_behavior() -> None:
    rate_limit = classify_binance_http_error(
        http_status=429,
        json_code=-1003,
        message="Too many requests",
        headers={"Retry-After": "2"},
    )
    auth = classify_binance_http_error(
        http_status=401,
        json_code=None,
        message="invalid api key",
    )
    clock = classify_binance_http_error(
        http_status=400,
        json_code=-1021,
        message="timestamp for this request is outside of the recvWindow",
    )

    assert rate_limit.category.value == "rate_limit"
    assert rate_limit.retry_after_seconds == 2.0
    assert auth.category.value == "auth"
    assert clock.category.value == "clock_skew"
