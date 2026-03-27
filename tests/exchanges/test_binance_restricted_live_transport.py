from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamSubscription
from app.exchanges.binance import BinancePrivateStreamReadTimeout
from app.exchanges.binance import BinanceRestrictedLivePayloadSource


def test_payload_source_skips_reconnect_during_heartbeat_grace_window() -> None:
    clock = _Clock((_dt(0, 0), _dt(0, 1)))
    transport = _FakeTransport(
        payloads=[
            _execution_payload(order_id=1001),
            _execution_payload(order_id=1002),
        ]
    )
    source = BinanceRestrictedLivePayloadSource(
        client=_client(),
        transport=transport,
        time_provider=clock.now,
    )

    first = source.poll_private_payloads()
    second = source.poll_private_payloads()
    stats = source.stats_snapshot()

    assert first[0]["i"] == 1001
    assert second == ()
    assert stats.heartbeat_overdue_events == 0
    assert stats.reconnect_count == 0


def test_payload_source_reconnects_after_heartbeat_overdue() -> None:
    clock = _Clock((_dt(0, 0), _dt(0, 1), _dt(0, 2)))
    transport = _FakeTransport(
        payloads=[
            _execution_payload(order_id=1001),
            _execution_payload(order_id=1002),
        ]
    )
    source = BinanceRestrictedLivePayloadSource(
        client=_client(),
        transport=transport,
        time_provider=clock.now,
    )

    first = source.poll_private_payloads()
    second = source.poll_private_payloads()
    third = source.poll_private_payloads()
    stats = source.stats_snapshot()

    assert first[0]["i"] == 1001
    assert second == ()
    assert third[0]["i"] == 1002
    assert stats.heartbeat_overdue_events == 1
    assert stats.reconnect_count == 1
    assert stats.heartbeat_overdue_streak == 0
    assert stats.last_heartbeat_delta_seconds == 120.0
    assert stats.last_heartbeat_timeout_seconds == 30.0
    assert stats.last_heartbeat_reconnect_executed is None
    assert source.current_health() is not None


def test_payload_source_requires_two_consecutive_heartbeat_overdue_observations() -> None:
    clock = _Clock((_dt(0, 0), _dt(0, 2), _dt(0, 4)))
    transport = _FakeTransport(
        payloads=[
            _execution_payload(order_id=3001),
            _execution_payload(order_id=3002),
        ]
    )
    source = BinanceRestrictedLivePayloadSource(
        client=_client(),
        transport=transport,
        time_provider=clock.now,
    )

    first = source.poll_private_payloads()
    second = source.poll_private_payloads()
    second_stats = source.stats_snapshot()
    third = source.poll_private_payloads()
    final_stats = source.stats_snapshot()

    assert first[0]["i"] == 3001
    assert second == ()
    assert second_stats.reconnect_count == 0
    assert second_stats.heartbeat_overdue_events == 0
    assert second_stats.heartbeat_overdue_streak == 1
    assert second_stats.last_heartbeat_delta_seconds == 120.0
    assert second_stats.last_heartbeat_reconnect_executed is False
    assert third[0]["i"] == 3002
    assert final_stats.reconnect_count == 1
    assert final_stats.heartbeat_overdue_events == 1
    assert final_stats.heartbeat_overdue_streak == 0


def test_payload_source_refreshes_on_rollover_window() -> None:
    clock = _Clock((_dt(0, 0), _dt(0, 56)))
    transport = _FakeTransport(
        payloads=[
            _execution_payload(order_id=2001),
            _execution_payload(order_id=2002),
        ]
    )
    source = BinanceRestrictedLivePayloadSource(
        client=_client(heartbeat_timeout=timedelta(hours=2)),
        transport=transport,
        time_provider=clock.now,
    )

    source.poll_private_payloads()
    source.poll_private_payloads()
    stats = source.stats_snapshot()

    assert stats.refresh_attempts == 1
    assert stats.refresh_failures == 0
    assert stats.last_refresh_result == "success"


def test_payload_source_returns_no_payload_on_read_timeout_without_forcing_reconnect() -> None:
    clock = _Clock((_dt(0, 0), _dt(0, 0), _dt(0, 1)))
    transport = _TimeoutTransport()
    source = BinanceRestrictedLivePayloadSource(
        client=_client(),
        transport=transport,
        time_provider=clock.now,
    )

    first = source.poll_private_payloads()
    second = source.poll_private_payloads()
    stats = source.stats_snapshot()

    assert first[0]["i"] == 1001
    assert second == ()
    assert stats.reconnect_count == 0
    assert stats.session_bootstrap_count == 1
    assert source.current_health() is not None


@dataclass
class _Clock:
    values: tuple[datetime, ...]

    def __post_init__(self) -> None:
        self._index = 0

    def now(self) -> datetime:
        value = self.values[min(self._index, len(self.values) - 1)]
        self._index += 1
        return value


@dataclass
class _FakeTransport:
    payloads: list[dict[str, object]]

    def __post_init__(self) -> None:
        self._connection_index = 0

    def open_connection(self, *, account_scope: str) -> str:
        self._connection_index += 1
        return f"connection-{self._connection_index}"

    def subscribe(self, *, connection_id: str, account_scope: str) -> BinancePrivateStreamSubscription:
        subscription_id = f"{account_scope}.{connection_id}.subscription"
        return BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=subscription_id,
            bootstrap_method="userDataStream.subscribe.signature",
            expires_at=_dt(1, 0),
        )

    def close_connection(self, *, connection_id: str) -> None:
        return None

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        return self.payloads.pop(0)


@dataclass
class _TimeoutTransport:
    def __post_init__(self) -> None:
        self._reads = 0

    def open_connection(self, *, account_scope: str) -> str:
        return "connection-1"

    def subscribe(self, *, connection_id: str, account_scope: str) -> BinancePrivateStreamSubscription:
        subscription_id = f"{account_scope}.{connection_id}.subscription"
        return BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=subscription_id,
            bootstrap_method="userDataStream.subscribe.signature",
            expires_at=_dt(1, 0),
        )

    def close_connection(self, *, connection_id: str) -> None:
        return None

    def read_payload(self, *, connection_id: str) -> dict[str, object]:
        if self._reads == 0:
            self._reads += 1
            return _execution_payload(order_id=1001)
        raise BinancePrivateStreamReadTimeout("private websocket read timed out")


def _client(*, heartbeat_timeout: timedelta | None = None) -> BinancePrivateStreamClient:
    return BinancePrivateStreamClient(
        config=BinanceAdapterConfig(
            rest_base_url="https://api.binance.com",
            websocket_base_url="wss://stream.binance.com:9443",
        ),
        heartbeat_timeout=timedelta(seconds=30) if heartbeat_timeout is None else heartbeat_timeout,
        session_ttl=timedelta(minutes=60),
        rollover_window=timedelta(minutes=55),
    )


def _execution_payload(*, order_id: int) -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360000000,
        "s": "BTCUSDT",
        "c": f"client-{order_id}",
        "i": order_id,
        "x": "TRADE",
        "X": "FILLED",
    }


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
