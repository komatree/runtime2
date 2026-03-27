"""Restricted-live private transport controller for long-running rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Callable

from .models import BinancePrivateStreamHealth
from .models import BinancePrivateStreamSession
from .private_stream_client import BinancePrivateStreamClient
from .private_stream_client import BinancePrivateStreamTransport
from .private_transport import BinancePrivateStreamReadTimeout


def _now_utc() -> datetime:
    return datetime.now(UTC)


_HEARTBEAT_RECONNECT_GRACE_WINDOW = timedelta(seconds=30)


@dataclass(frozen=True)
class BinanceRestrictedLiveTransportStats:
    """Operator-visible private transport counters for soak reporting."""

    reconnect_count: int = 0
    refresh_attempts: int = 0
    refresh_failures: int = 0
    heartbeat_overdue_events: int = 0
    heartbeat_overdue_streak: int = 0
    session_bootstrap_count: int = 0
    last_refresh_result: str | None = None
    last_transport_error: str | None = None
    last_heartbeat_observed_at: datetime | None = None
    last_heartbeat_message_at: datetime | None = None
    last_heartbeat_delta_seconds: float | None = None
    last_heartbeat_timeout_seconds: float | None = None
    last_heartbeat_reconnect_executed: bool | None = None


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

    def _replace_stats(self, **changes: object) -> None:
        self._stats = replace(self._stats, **changes)

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
                last_message_at = self._session.last_message_at
                heartbeat_delta_seconds = None
                heartbeat_timeout_seconds = self.client.heartbeat_timeout.total_seconds()
                overdue_streak = self._stats.heartbeat_overdue_streak + 1
                if last_message_at is not None:
                    heartbeat_delta = occurred_at - last_message_at
                    heartbeat_delta_seconds = heartbeat_delta.total_seconds()
                    heartbeat_reconnect_threshold = (
                        self.client.heartbeat_timeout + _HEARTBEAT_RECONNECT_GRACE_WINDOW
                    )
                    self._replace_stats(
                        heartbeat_overdue_streak=overdue_streak,
                        last_heartbeat_observed_at=occurred_at,
                        last_heartbeat_message_at=last_message_at,
                        last_heartbeat_delta_seconds=heartbeat_delta_seconds,
                        last_heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                        last_heartbeat_reconnect_executed=False,
                    )
                    if heartbeat_delta <= heartbeat_reconnect_threshold:
                        return ()
                else:
                    self._replace_stats(
                        heartbeat_overdue_streak=overdue_streak,
                        last_heartbeat_observed_at=occurred_at,
                        last_heartbeat_message_at=None,
                        last_heartbeat_delta_seconds=None,
                        last_heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                        last_heartbeat_reconnect_executed=False,
                    )
                if overdue_streak < 2:
                    return ()
                self._replace_stats(
                    heartbeat_overdue_events=self._stats.heartbeat_overdue_events + 1,
                    last_heartbeat_reconnect_executed=True,
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
            self._replace_stats(
                last_transport_error=str(exc),
                heartbeat_overdue_streak=0,
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
        self._replace_stats(
            heartbeat_overdue_streak=0,
            last_heartbeat_reconnect_executed=None,
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
        self._replace_stats(
            heartbeat_overdue_streak=0,
            session_bootstrap_count=self._stats.session_bootstrap_count + 1,
            last_heartbeat_reconnect_executed=None,
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
            self._replace_stats(
                refresh_attempts=attempts,
                last_refresh_result="success",
            )
        except Exception as exc:
            self._replace_stats(
                refresh_attempts=attempts,
                refresh_failures=self._stats.refresh_failures + 1,
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
        self._replace_stats(
            reconnect_count=self._stats.reconnect_count + 1,
            heartbeat_overdue_streak=0,
            last_transport_error=reason,
        )
