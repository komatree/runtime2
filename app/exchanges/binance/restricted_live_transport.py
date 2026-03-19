"""Restricted-live private transport controller for long-running rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Callable

from .models import BinancePrivateStreamHealth
from .models import BinancePrivateStreamSession
from .private_stream_client import BinancePrivateStreamClient
from .private_stream_client import BinancePrivateStreamTransport
from .private_transport import BinancePrivateStreamReadTimeout


def _now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class BinanceRestrictedLiveTransportStats:
    """Operator-visible private transport counters for soak reporting."""

    reconnect_count: int = 0
    refresh_attempts: int = 0
    refresh_failures: int = 0
    heartbeat_overdue_events: int = 0
    session_bootstrap_count: int = 0
    last_refresh_result: str | None = None
    last_transport_error: str | None = None


@dataclass
class BinanceRestrictedLivePayloadSource:
    """Transport-backed private payload source for repeated restricted-live cycles."""

    client: BinancePrivateStreamClient
    transport: BinancePrivateStreamTransport
    time_provider: Callable[[], datetime] = _now_utc

    def __post_init__(self) -> None:
        self._session: BinancePrivateStreamSession | None = None
        self._last_health: BinancePrivateStreamHealth | None = None
        self._stats = BinanceRestrictedLiveTransportStats()

    def poll_private_payloads(self) -> tuple[dict[str, object], ...]:
        """Return the next private payload batch while maintaining session health."""

        occurred_at = self.time_provider()
        self._bootstrap_if_needed(occurred_at=occurred_at)
        assert self._session is not None

        watchdog = self.client.check_runtime_health(
            session=self._session,
            occurred_at=occurred_at,
        )
        if watchdog is not None:
            self._last_health = watchdog
            if any("heartbeat overdue" in alert for alert in watchdog.alerts):
                self._stats = BinanceRestrictedLiveTransportStats(
                    reconnect_count=self._stats.reconnect_count,
                    refresh_attempts=self._stats.refresh_attempts,
                    refresh_failures=self._stats.refresh_failures,
                    heartbeat_overdue_events=self._stats.heartbeat_overdue_events + 1,
                    session_bootstrap_count=self._stats.session_bootstrap_count,
                    last_refresh_result=self._stats.last_refresh_result,
                    last_transport_error=self._stats.last_transport_error,
                )
                self._reconnect(occurred_at=occurred_at, reason="heartbeat overdue")
            elif watchdog.alerts and "subscription expired" in watchdog.alerts[0]:
                self._bootstrap_new_session(occurred_at=occurred_at)

        rollover = self.client.check_session_rollover(
            session=self._session,
            occurred_at=occurred_at,
        )
        if rollover is not None:
            self._refresh_session(occurred_at=occurred_at)

        try:
            payload = self.transport.read_payload(connection_id=self._session.connection_id or "")
        except BinancePrivateStreamReadTimeout:
            self._last_health = self.client.build_health_snapshot(
                session=self._session,
                occurred_at=occurred_at,
            )
            return ()
        except Exception as exc:
            self._stats = BinanceRestrictedLiveTransportStats(
                reconnect_count=self._stats.reconnect_count,
                refresh_attempts=self._stats.refresh_attempts,
                refresh_failures=self._stats.refresh_failures,
                heartbeat_overdue_events=self._stats.heartbeat_overdue_events,
                session_bootstrap_count=self._stats.session_bootstrap_count,
                last_refresh_result=self._stats.last_refresh_result,
                last_transport_error=str(exc),
            )
            self._reconnect(occurred_at=occurred_at, reason=str(exc))
            return (
                {
                    "e": "eventStreamTerminated",
                    "E": int(occurred_at.timestamp() * 1000),
                },
            )

        self._session = self.client.mark_streaming(
            session=self._session,
            occurred_at=occurred_at,
        )
        self._last_health = self.client.build_health_snapshot(
            session=self._session,
            occurred_at=occurred_at,
        )
        return (payload,)

    def current_health(self) -> BinancePrivateStreamHealth | None:
        """Return the latest private-stream health view."""

        return self._last_health

    def current_session(self) -> BinancePrivateStreamSession | None:
        """Return the latest private-stream session metadata."""

        return self._session

    def stats_snapshot(self) -> BinanceRestrictedLiveTransportStats:
        """Return the latest private transport counters."""

        return self._stats

    def _bootstrap_if_needed(self, *, occurred_at: datetime) -> None:
        if self._session is not None:
            return
        self._bootstrap_new_session(occurred_at=occurred_at)

    def _bootstrap_new_session(self, *, occurred_at: datetime) -> None:
        self._session = self.client.bootstrap_session(
            transport=self.transport,
            started_at=occurred_at,
        )
        self._stats = BinanceRestrictedLiveTransportStats(
            reconnect_count=self._stats.reconnect_count,
            refresh_attempts=self._stats.refresh_attempts,
            refresh_failures=self._stats.refresh_failures,
            heartbeat_overdue_events=self._stats.heartbeat_overdue_events,
            session_bootstrap_count=self._stats.session_bootstrap_count + 1,
            last_refresh_result=self._stats.last_refresh_result,
            last_transport_error=self._stats.last_transport_error,
        )
        self._last_health = self.client.build_health_snapshot(
            session=self._session,
            occurred_at=occurred_at,
        )

    def _refresh_session(self, *, occurred_at: datetime) -> None:
        assert self._session is not None
        attempts = self._stats.refresh_attempts + 1
        try:
            self._session = self.client.refresh_session(
                session=self._session,
                occurred_at=occurred_at,
                transport=self.transport,
            )
            self._stats = BinanceRestrictedLiveTransportStats(
                reconnect_count=self._stats.reconnect_count,
                refresh_attempts=attempts,
                refresh_failures=self._stats.refresh_failures,
                heartbeat_overdue_events=self._stats.heartbeat_overdue_events,
                session_bootstrap_count=self._stats.session_bootstrap_count,
                last_refresh_result="success",
                last_transport_error=self._stats.last_transport_error,
            )
        except Exception as exc:
            self._stats = BinanceRestrictedLiveTransportStats(
                reconnect_count=self._stats.reconnect_count,
                refresh_attempts=attempts,
                refresh_failures=self._stats.refresh_failures + 1,
                heartbeat_overdue_events=self._stats.heartbeat_overdue_events,
                session_bootstrap_count=self._stats.session_bootstrap_count,
                last_refresh_result="failed",
                last_transport_error=str(exc),
            )
            self._last_health = self.client.terminated_stream_health(
                occurred_at=occurred_at,
                reason=f"private stream subscription renewal failed: {exc}",
            )

    def _reconnect(self, *, occurred_at: datetime, reason: str) -> None:
        assert self._session is not None
        try:
            self._session = self.client.reconnect_session(
                session=self._session,
                occurred_at=occurred_at,
                transport=self.transport,
            )
            self._last_health = self.client.build_health_snapshot(
                session=self._session,
                occurred_at=occurred_at,
            )
        except Exception:
            self._bootstrap_new_session(occurred_at=occurred_at)
        self._stats = BinanceRestrictedLiveTransportStats(
            reconnect_count=self._stats.reconnect_count + 1,
            refresh_attempts=self._stats.refresh_attempts,
            refresh_failures=self._stats.refresh_failures,
            heartbeat_overdue_events=self._stats.heartbeat_overdue_events,
            session_bootstrap_count=self._stats.session_bootstrap_count,
            last_refresh_result=self._stats.last_refresh_result,
            last_transport_error=reason,
        )
