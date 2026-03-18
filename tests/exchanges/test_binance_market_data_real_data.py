"""Tests for real-data kline parsing into closed candle inputs."""

from datetime import UTC
from datetime import datetime

import pytest

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceMarketDataClient


def _client() -> BinanceMarketDataClient:
    return BinanceMarketDataClient(
        config=BinanceAdapterConfig(
            rest_base_url="https://api.binance.com",
            websocket_base_url="wss://stream.binance.com:9443",
        )
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def test_closed_candle_acceptance() -> None:
    client = _client()
    context = client.build_report_only_market_context(
        instrument_id="BTC-USDT",
        execution_timeframe="4h",
        context_timeframe="1d",
        execution_klines=(
            [1735689600000, "100", "103", "99", "101", "10", 1735703999000, "1000", 100],
            [1735704000000, "101", "106", "100", "104", "11", 1735718399000, "1200", 110],
        ),
        context_klines=(
            [1735603200000, "95", "105", "90", "100", "100", 1735689599000, "9000", 900],
            [1735689600000, "100", "110", "98", "108", "120", 1735775999000, "10000", 950],
        ),
        reference_time=_dt(2025, 1, 2, 1),
    )

    assert context.execution_bar_slice.candles[-1].is_closed is True
    assert context.context_bar_slice.candles[-1].is_closed is True


def test_incomplete_candle_rejection() -> None:
    client = _client()

    with pytest.raises(ValueError, match="insufficient closed candles"):
        client.build_report_only_market_context(
            instrument_id="BTC-USDT",
            execution_timeframe="4h",
            context_timeframe="1d",
            execution_klines=(
                [1735689600000, "100", "103", "99", "101", "10", 1735703999000, "1000", 100],
                [1735704000000, "101", "106", "100", "104", "11", 1735790399000, "1200", 110],
            ),
            context_klines=(
                [1735603200000, "95", "105", "90", "100", "100", 1735689599000, "9000", 900],
                [1735689600000, "100", "110", "98", "108", "120", 1735775999000, "10000", 950],
            ),
            reference_time=_dt(2025, 1, 2, 0),
        )
