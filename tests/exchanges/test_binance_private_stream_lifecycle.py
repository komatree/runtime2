"""Binance private stream lifecycle and normalization tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinancePrivateEventFamily
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamState
from app.exchanges.binance import BinancePrivateStreamSubscription


def test_transport_bootstrap_and_lifecycle_state_transitions() -> None:
    client = _client()
    transport = _FakePrivateTransport()

    session = client.bootstrap_session(
        transport=transport,
        started_at=_dt(0, 0),
    )
    streaming = client.mark_streaming(
        session=session,
        occurred_at=_dt(0, 1),
    )
    rollover = client.check_session_rollover(
        session=streaming,
        occurred_at=_dt(0, 56),
    )
    refreshed = client.refresh_session(
        session=streaming,
        occurred_at=_dt(0, 57),
        transport=transport,
    )
    shutdown = client.shutdown(
        session=refreshed,
        occurred_at=_dt(1, 0),
        transport=transport,
    )

    assert session.state is BinancePrivateStreamState.SUBSCRIBED
    assert session.connection_id == "connection-1"
    assert session.subscription_id == "subscription-1"
    assert streaming.state is BinancePrivateStreamState.STREAMING
    assert rollover is not None
    assert rollover.state is BinancePrivateStreamState.SESSION_ROLLOVER
    assert refreshed.stream_key == "subscription-2"
    assert refreshed.last_keepalive_at == _dt(0, 57)
    assert shutdown.state is BinancePrivateStreamState.SHUTDOWN
    assert transport.closed_connection_ids == ["connection-1", "connection-2"]


def test_reconnect_behavior_replaces_connection_and_records_health() -> None:
    client = _client()
    transport = _FakePrivateTransport()
    session = client.bootstrap_session(
        transport=transport,
        started_at=_dt(0, 0),
    )

    reconnected_session = client.reconnect_session(
        session=session,
        occurred_at=_dt(0, 10),
        transport=transport,
    )
    reconnected_health = client.on_reconnect(
        session=reconnected_session,
        occurred_at=_dt(0, 10),
        connection_id=reconnected_session.connection_id,
    )

    assert reconnected_session.state is BinancePrivateStreamState.STREAMING
    assert reconnected_session.connection_id == "connection-2"
    assert reconnected_session.subscription_id == "subscription-2"
    assert reconnected_session.reconnect_attempts == 1
    assert reconnected_health.state is BinancePrivateStreamState.STREAMING
    assert reconnected_health.reconnect_attempts == 2
    assert "reconnected" in reconnected_health.alerts[0]


def test_normalized_event_mapping_and_batch_observability() -> None:
    client = _client()
    batch = client.ingest_payloads(
        payloads=(
            _execution_report_payload(),
            _account_update_payload(),
            _balance_update_payload(),
        ),
        cursor="cursor-1",
        has_gap=False,
    )
    account_sync = client.map_account_sync_summary(events=batch.events)
    reconciliation_events = client.events_for_reconciliation(batch=batch)
    health = client.build_health_snapshot(
        session=client.mark_streaming(
            session=client.initialize_session(
                stream_key="subscription-1",
                started_at=_dt(0, 0),
                connection_id="connection-1",
                subscription_id="subscription-1",
            ),
            occurred_at=_dt(0, 1),
        ),
        batch=batch,
    )

    assert batch.family_counts == {
        "order_update": 1,
        "account_update": 2,
    }
    assert batch.last_sequence_id == "123456"
    assert batch.stream_state is BinancePrivateStreamState.STREAMING
    assert order_event(batch).event_family is BinancePrivateEventFamily.ORDER_UPDATE
    assert account_sync is not None
    assert account_sync.updated_assets == ("USDT", "BTC")
    assert len(reconciliation_events) == 1
    assert reconciliation_events[0].client_order_id == "client-123"
    assert health.state is BinancePrivateStreamState.STREAMING
    assert health.is_authoritative is True


def test_terminated_stream_handling_marks_batch_and_health_non_authoritative() -> None:
    client = _client()
    batch = client.ingest_payloads(
        payloads=(_terminated_payload(),),
    )
    health = client.build_health_snapshot(
        session=client.mark_streaming(
            session=client.initialize_session(
                stream_key="subscription-1",
                started_at=_dt(0, 0),
                connection_id="connection-1",
                subscription_id="subscription-1",
            ),
            occurred_at=_dt(0, 1),
        ),
        batch=batch,
    )
    terminated = client.terminated_stream_health(
        occurred_at=_dt(0, 20),
        reason="listenKeyExpired",
    )

    assert batch.stream_state is BinancePrivateStreamState.TERMINATED
    assert "session reinitialization required" in batch.alerts[0]
    assert health.state is BinancePrivateStreamState.TERMINATED
    assert health.is_authoritative is False
    assert terminated.state is BinancePrivateStreamState.TERMINATED
    assert "listenKeyExpired" in terminated.alerts[0]


def test_gap_batch_reports_degraded_health() -> None:
    client = _client()
    session = client.mark_streaming(
        session=client.initialize_session(
            stream_key="subscription-1",
            started_at=_dt(0, 0),
            connection_id="connection-1",
            subscription_id="subscription-1",
        ),
        occurred_at=_dt(0, 1),
    )

    batch = client.ingest_payloads(
        payloads=(_execution_report_payload(),),
        cursor="cursor-gap",
        has_gap=True,
    )
    health = client.build_health_snapshot(
        session=session,
        batch=batch,
        last_reconnect_at=_dt(0, 5),
    )

    assert batch.stream_state is BinancePrivateStreamState.STREAMING
    assert "gap detected" in batch.alerts[0]
    assert health.state is BinancePrivateStreamState.DEGRADED
    assert health.is_authoritative is False
    assert health.last_reconnect_at == _dt(0, 5)


def test_runtime_watchdog_marks_heartbeat_overdue_and_expired() -> None:
    client = _client()
    session = client.mark_streaming(
        session=client.initialize_session(
            stream_key="subscription-1",
            started_at=_dt(0, 0),
            connection_id="connection-1",
            subscription_id="subscription-1",
        ),
        occurred_at=_dt(0, 1),
    )

    overdue = client.build_health_snapshot(
        session=session,
        occurred_at=_dt(0, 3),
    )
    expired = client.build_health_snapshot(
        session=client.refresh_session(
            session=session,
            occurred_at=_dt(0, 2),
        ),
        occurred_at=_dt(1, 3),
    )

    assert overdue.state is BinancePrivateStreamState.DEGRADED
    assert "heartbeat overdue" in overdue.alerts[0]
    assert overdue.is_authoritative is False
    assert expired.state is BinancePrivateStreamState.TERMINATED
    assert any("subscription expired" in alert for alert in expired.alerts)


@dataclass
class _FakePrivateTransport:
    next_connection_id: int = 1
    next_subscription_id: int = 1
    closed_connection_ids: list[str] | None = None

    def __post_init__(self) -> None:
        if self.closed_connection_ids is None:
            self.closed_connection_ids = []

    def open_connection(self, *, account_scope: str) -> str:
        assert account_scope == "spot"
        connection_id = f"connection-{self.next_connection_id}"
        self.next_connection_id += 1
        return connection_id

    def subscribe(self, *, connection_id: str, account_scope: str) -> BinancePrivateStreamSubscription:
        subscription_id = f"subscription-{self.next_subscription_id}"
        self.next_subscription_id += 1
        return BinancePrivateStreamSubscription(
            subscription_id=subscription_id,
            stream_key=subscription_id,
            bootstrap_method="userDataStream.subscribe.signature",
            expires_at=_dt(1, 0),
        )

    def close_connection(self, *, connection_id: str) -> None:
        assert self.closed_connection_ids is not None
        self.closed_connection_ids.append(connection_id)


def _client() -> BinancePrivateStreamClient:
    return BinancePrivateStreamClient(
        config=BinanceAdapterConfig(
            rest_base_url="https://api.binance.com",
            websocket_base_url="wss://stream.binance.com:9443",
        ),
        session_ttl=timedelta(minutes=60),
        rollover_window=timedelta(minutes=55),
    )


def order_event(batch):
    return next(event for event in batch.events if event.event_family is BinancePrivateEventFamily.ORDER_UPDATE)


def _execution_report_payload() -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360000000,
        "s": "BTCUSDT",
        "c": "client-123",
        "i": 123456,
        "x": "TRADE",
        "X": "FILLED",
    }


def _account_update_payload() -> dict[str, object]:
    return {
        "e": "outboundAccountPosition",
        "E": 1773360005000,
        "B": [
            {"a": "USDT", "f": "1000", "l": "0"},
            {"a": "BTC", "f": "0.1", "l": "0"},
        ],
    }


def _balance_update_payload() -> dict[str, object]:
    return {
        "e": "balanceUpdate",
        "E": 1773360007000,
        "a": "USDT",
        "d": "15.5",
    }


def _terminated_payload() -> dict[str, object]:
    return {
        "e": "listenKeyExpired",
        "E": 1773360010000,
    }


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
