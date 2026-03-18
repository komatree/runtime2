"""Binance public websocket market-data tests.

TODO:
- Add real transport lifecycle tests when websocket IO is implemented.
- Add multi-symbol buffering tests when runtime feed multiplexing is added.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceMarketDataClient
from app.exchanges.binance import BinancePublicStreamState
from app.exchanges.binance import BinancePublicWebSocketClient


def test_message_normalization() -> None:
    client = _ws_client()
    event = client.normalize_public_message(
        payload=_closed_kline_payload(),
        instrument_id="BTC-USDT",
    )

    assert event.event_type == "kline"
    assert event.kline is not None
    assert event.kline.candle.instrument_id == "BTC-USDT"
    assert event.kline.candle.timeframe == "4h"


def test_reconnect_behavior() -> None:
    client = _ws_client()
    degraded = client.on_disconnect(
        reason="network drop",
        reconnect_attempts=1,
        occurred_at=_dt(0, 0),
    )
    failover = client.on_disconnect(
        reason="network drop",
        reconnect_attempts=3,
        occurred_at=_dt(0, 5),
    )
    recovered = client.on_reconnect(
        reconnect_attempts=2,
        occurred_at=_dt(0, 6),
    )

    assert degraded.state is BinancePublicStreamState.DEGRADED
    assert failover.state is BinancePublicStreamState.FAILOVER_REST
    assert failover.failover_active is True
    assert recovered.state is BinancePublicStreamState.STREAMING


def test_closed_bar_event_detection() -> None:
    market_data = BinanceMarketDataClient(config=_config())
    closed = market_data.detect_closed_bar_event(
        payload=_closed_kline_payload(),
        instrument_id="BTC-USDT",
    )
    open_bar = market_data.detect_closed_bar_event(
        payload=_open_kline_payload(),
        instrument_id="BTC-USDT",
    )
    previous = market_data.detect_closed_bar_event(
        payload={
            "e": "kline",
            "E": 1735704000000,
            "s": "BTCUSDT",
            "k": {
                "t": 1735689600000,
                "T": 1735703999000,
                "i": "4h",
                "o": "100",
                "c": "101",
                "h": "103",
                "l": "99",
                "v": "10",
                "q": "1000",
                "n": 100,
                "x": True,
            },
        },
        instrument_id="BTC-USDT",
    )
    bar_slice = market_data.build_bar_slice_from_closed_candles(
        instrument_id="BTC-USDT",
        timeframe="4h",
        candles=(previous, closed),
        limit=2,
    )

    assert closed is not None
    assert open_bar is None
    assert bar_slice.candles[-1].is_closed is True


def test_feed_degradation_handling() -> None:
    client = _ws_client()
    heartbeat = client.on_heartbeat(
        occurred_at=_dt(0, 2),
        last_heartbeat_at=_dt(0, 0),
    )
    rollover = client.check_session_rollover(
        session_started_at=_dt(0, 0),
        occurred_at=_dt(24, 0),
    )

    assert heartbeat.state is BinancePublicStreamState.DEGRADED
    assert "heartbeat overdue" in heartbeat.alerts[0]
    assert rollover is not None
    assert rollover.state is BinancePublicStreamState.SESSION_ROLLOVER


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
    )


def _ws_client() -> BinancePublicWebSocketClient:
    return BinancePublicWebSocketClient(
        config=_config(),
        market_data_client=BinanceMarketDataClient(config=_config()),
        heartbeat_timeout=timedelta(seconds=60),
        session_rollover=timedelta(hours=23),
        failover_reconnect_attempts=3,
    )


def _closed_kline_payload() -> dict[str, object]:
    return {
        "e": "kline",
        "E": 1735718400000,
        "s": "BTCUSDT",
        "k": {
            "t": 1735704000000,
            "T": 1735718399000,
            "i": "4h",
            "o": "101",
            "c": "104",
            "h": "106",
            "l": "100",
            "v": "11",
            "q": "1200",
            "n": 110,
            "x": True,
        },
    }


def _open_kline_payload() -> dict[str, object]:
    payload = _closed_kline_payload()
    payload["k"] = dict(payload["k"])
    payload["k"]["x"] = False
    return payload


def _dt(hour: int, minute: int) -> datetime:
    base_hour = hour if hour < 24 else 23
    value = datetime(2026, 3, 13, base_hour, minute, tzinfo=UTC)
    if hour < 24:
        return value
    return value + timedelta(hours=hour - 23)
