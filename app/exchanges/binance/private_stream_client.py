"""Binance private account and order event ingestion client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Protocol
from typing import TYPE_CHECKING

from .models import BinanceAccountSyncSummary
from .models import BinanceAdapterConfig
from .models import BinancePrivateEventFamily
from .models import BinancePrivateStreamBatch
from .models import BinancePrivateStreamEvent
from .models import BinancePrivateStreamHealth
from .models import BinancePrivateStreamSession
from .models import BinancePrivateStreamState
from .models import BinancePrivateStreamSubscription

if TYPE_CHECKING:
    from .models import BinancePrivatePayloadTranslation
    from .private_payload_translator import BinancePrivatePayloadTranslator


class BinancePrivateStreamTransport(Protocol):
    """Transport boundary for authenticated private-stream lifecycle work.

    Implementations keep Binance WS-API authentication and subscription details
    inside the exchange adapter boundary. The runtime only consumes normalized
    lifecycle state and internal adapter events.
    """

    def open_connection(self, *, account_scope: str) -> str:
        """Return a transport-specific connection identifier."""

    def subscribe(
        self,
        *,
        connection_id: str,
        account_scope: str,
    ) -> BinancePrivateStreamSubscription:
        """Return an authenticated Binance user-data subscription receipt."""

    def close_connection(self, *, connection_id: str) -> None:
        """Close the active transport connection."""


@dataclass(frozen=True)
class BinancePrivateStreamClient:
    """Lifecycle-aware private account/order event ingestion client.

    Responsibilities:
    - maintain authenticated private-session metadata and lifecycle state
    - normalize balance, order, execution, and stream-status payloads
    - expose operator-visible health for reconnect, rollover, and termination
    - forward normalized private events to reconciliation and account sync

    Non-goals:
    - expose exchange-native payloads outside the adapter boundary
    - translate directly into strategy contracts
    - imply unrestricted production-readiness from transport scaffolding
    """

    config: BinanceAdapterConfig
    account_scope: str = "spot"
    session_ttl: timedelta = timedelta(hours=24)
    rollover_window: timedelta = timedelta(minutes=55)
    heartbeat_timeout: timedelta = timedelta(seconds=90)
    subscription_method: str = "userDataStream.subscribe.signature"

    def describe_private_stream_requirement(self) -> str:
        """Return why private-stream ingestion is mandatory before live trading."""

        return "private stream required for authoritative order and fill ingestion"

    def initialize_session(
        self,
        *,
        stream_key: str,
        started_at: datetime,
        connection_id: str | None = None,
        subscription_id: str | None = None,
        expires_at: datetime | None = None,
        bootstrap_method: str | None = None,
    ) -> BinancePrivateStreamSession:
        """Return initialized authenticated session metadata."""

        return BinancePrivateStreamSession(
            stream_key=stream_key,
            state=BinancePrivateStreamState.AUTHENTICATED,
            account_scope=self.account_scope,
            started_at=started_at,
            expires_at=expires_at or (started_at + self.session_ttl),
            connection_id=connection_id,
            subscription_id=subscription_id,
            bootstrap_method=bootstrap_method or self.subscription_method,
        )

    def bootstrap_session(
        self,
        *,
        transport: BinancePrivateStreamTransport,
        started_at: datetime,
    ) -> BinancePrivateStreamSession:
        """Open an authenticated WS-API connection and subscribe in one step."""

        connection_id = transport.open_connection(account_scope=self.account_scope)
        subscription = transport.subscribe(
            connection_id=connection_id,
            account_scope=self.account_scope,
        )
        session = self.initialize_session(
            stream_key=subscription.stream_key,
            started_at=started_at,
            connection_id=connection_id,
            subscription_id=subscription.subscription_id,
            expires_at=subscription.expires_at,
            bootstrap_method=subscription.bootstrap_method,
        )
        return self.subscribe(session)

    def subscribe(
        self,
        session: BinancePrivateStreamSession,
    ) -> BinancePrivateStreamSession:
        """Advance an authenticated session into subscribed state."""

        return BinancePrivateStreamSession(
            stream_key=session.stream_key,
            state=BinancePrivateStreamState.SUBSCRIBED,
            account_scope=session.account_scope,
            started_at=session.started_at,
            expires_at=session.expires_at,
            connection_id=session.connection_id,
            subscription_id=session.subscription_id,
            bootstrap_method=session.bootstrap_method,
            last_message_at=session.last_message_at,
            last_keepalive_at=session.last_keepalive_at,
            reconnect_attempts=session.reconnect_attempts,
            alerts=session.alerts,
        )

    def mark_streaming(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
    ) -> BinancePrivateStreamSession:
        """Mark the session as actively streaming after subscribe/restore."""

        return BinancePrivateStreamSession(
            stream_key=session.stream_key,
            state=BinancePrivateStreamState.STREAMING,
            account_scope=session.account_scope,
            started_at=session.started_at,
            expires_at=session.expires_at,
            connection_id=session.connection_id,
            subscription_id=session.subscription_id,
            bootstrap_method=session.bootstrap_method,
            last_message_at=occurred_at,
            last_keepalive_at=session.last_keepalive_at,
            reconnect_attempts=session.reconnect_attempts,
            alerts=session.alerts,
        )

    def refresh_session(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
        transport: BinancePrivateStreamTransport | None = None,
    ) -> BinancePrivateStreamSession:
        """Renew the authenticated WS-API subscription before expiry."""

        connection_id = session.connection_id
        if transport is not None:
            if session.connection_id is not None:
                transport.close_connection(connection_id=session.connection_id)
            connection_id = transport.open_connection(account_scope=session.account_scope)
            subscription = transport.subscribe(
                connection_id=connection_id,
                account_scope=session.account_scope,
            )
            stream_key = subscription.stream_key
            subscription_id = subscription.subscription_id
            expires_at = subscription.expires_at or (occurred_at + self.session_ttl)
            bootstrap_method = subscription.bootstrap_method
        else:
            stream_key = session.stream_key
            subscription_id = session.subscription_id
            expires_at = occurred_at + self.session_ttl
            bootstrap_method = session.bootstrap_method
        return BinancePrivateStreamSession(
            stream_key=stream_key,
            state=BinancePrivateStreamState.STREAMING,
            account_scope=session.account_scope,
            started_at=occurred_at,
            expires_at=expires_at,
            connection_id=connection_id,
            subscription_id=subscription_id,
            bootstrap_method=bootstrap_method,
            last_message_at=session.last_message_at,
            last_keepalive_at=occurred_at,
            reconnect_attempts=session.reconnect_attempts,
            alerts=(*session.alerts, "private stream subscription renewed"),
        )

    def on_reconnect(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
        connection_id: str | None = None,
    ) -> BinancePrivateStreamHealth:
        """Return lifecycle health after reconnecting the private stream."""

        return BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.STREAMING,
            reconnect_attempts=session.reconnect_attempts + 1,
            last_message_at=occurred_at,
            last_reconnect_at=occurred_at,
            session_expires_at=session.expires_at,
            is_authoritative=True,
            alerts=(
                "private stream reconnected",
                *(("private stream connection replaced",) if connection_id else ()),
            ),
        )

    def reconnect_session(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
        transport: BinancePrivateStreamTransport,
    ) -> BinancePrivateStreamSession:
        """Open a replacement authenticated WS-API connection and resubscribe."""

        if session.connection_id is not None:
            transport.close_connection(connection_id=session.connection_id)
        connection_id = transport.open_connection(account_scope=session.account_scope)
        subscription = transport.subscribe(
            connection_id=connection_id,
            account_scope=session.account_scope,
        )
        return BinancePrivateStreamSession(
            stream_key=subscription.stream_key,
            state=BinancePrivateStreamState.STREAMING,
            account_scope=session.account_scope,
            started_at=session.started_at,
            expires_at=subscription.expires_at or session.expires_at,
            connection_id=connection_id,
            subscription_id=subscription.subscription_id,
            bootstrap_method=subscription.bootstrap_method,
            last_message_at=occurred_at,
            last_keepalive_at=session.last_keepalive_at,
            reconnect_attempts=session.reconnect_attempts + 1,
            alerts=("private stream reconnected",),
        )

    def check_session_rollover(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
    ) -> BinancePrivateStreamHealth | None:
        """Return rollover health when the current authenticated session is near expiry."""

        if session.expires_at is None:
            return None
        if session.expires_at - occurred_at > self.session_ttl - self.rollover_window:
            return None
        return BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.SESSION_ROLLOVER,
            reconnect_attempts=session.reconnect_attempts,
            last_message_at=session.last_message_at or occurred_at,
            session_expires_at=session.expires_at,
            is_authoritative=False,
            alerts=("private stream subscription rollover required",),
        )

    def shutdown(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime,
        transport: BinancePrivateStreamTransport | None = None,
    ) -> BinancePrivateStreamHealth:
        """Return graceful shutdown state for the current private stream session."""

        if transport is not None and session.connection_id is not None:
            transport.close_connection(connection_id=session.connection_id)
        return BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.SHUTDOWN,
            reconnect_attempts=session.reconnect_attempts,
            last_message_at=occurred_at,
            session_expires_at=session.expires_at,
            is_authoritative=False,
            alerts=("private stream shutdown complete",),
        )

    def placeholder_event(self) -> BinancePrivateStreamEvent:
        """Return a representative private-stream event stub."""

        return BinancePrivateStreamEvent(
            event_type="account_update",
            event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
            event_time=datetime.now(UTC),
            account_scope=self.account_scope,
            sequence_id=None,
            client_order_id=None,
            exchange_order_id=None,
            payload_summary={"transport": "placeholder"},
        )

    def normalize_event_payload(self, *, payload: dict[str, object]) -> BinancePrivateStreamEvent:
        """Normalize a Binance private-stream payload into an internal adapter event."""

        event_type = str(payload.get("e", "unknown"))
        event_time = datetime.fromtimestamp(int(payload.get("E", 0)) / 1000, tz=UTC)
        if event_type == "executionReport":
            return BinancePrivateStreamEvent(
                event_type="execution_report",
                event_family=BinancePrivateEventFamily.ORDER_UPDATE,
                event_time=event_time,
                account_scope=self.account_scope,
                sequence_id=str(payload.get("i")) if payload.get("i") is not None else None,
                client_order_id=str(payload.get("c")) if payload.get("c") is not None else None,
                exchange_order_id=str(payload.get("i")) if payload.get("i") is not None else None,
                payload_summary={
                    "order_status": str(payload.get("X", "")),
                    "execution_type": str(payload.get("x", "")),
                    "symbol": str(payload.get("s", "")),
                },
            )
        if event_type == "outboundAccountPosition":
            balances = payload.get("B", ())
            updated_assets = ",".join(
                str(balance.get("a", ""))
                for balance in balances
                if isinstance(balance, dict) and balance.get("a") is not None
            )
            return BinancePrivateStreamEvent(
                event_type="account_update",
                event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
                event_time=event_time,
                account_scope=self.account_scope,
                payload_summary={"updated_assets": updated_assets},
            )
        if event_type == "balanceUpdate":
            return BinancePrivateStreamEvent(
                event_type="balance_update",
                event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
                event_time=event_time,
                account_scope=self.account_scope,
                payload_summary={
                    "asset": str(payload.get("a", "")),
                    "delta": str(payload.get("d", "")),
                },
            )
        if event_type in {"listenKeyExpired", "eventStreamTerminated", "userDataStreamExpired", "sessionExpired"}:
            return BinancePrivateStreamEvent(
                event_type="stream_terminated",
                event_family=BinancePrivateEventFamily.STREAM_STATUS,
                event_time=event_time,
                account_scope=self.account_scope,
                payload_summary={"reason": event_type},
            )
        raise ValueError("unsupported private-stream payload")

    def ingest_payloads(
        self,
        *,
        payloads: tuple[dict[str, object], ...],
        cursor: str | None = None,
        has_gap: bool = False,
    ) -> BinancePrivateStreamBatch:
        """Normalize raw transport payloads into an adapter-internal batch."""

        return self.ingest_events(
            events=tuple(self.normalize_event_payload(payload=payload) for payload in payloads),
            cursor=cursor,
            has_gap=has_gap,
        )

    def translate_payloads(
        self,
        *,
        payloads: tuple[dict[str, object], ...],
        translator: BinancePrivatePayloadTranslator,
    ) -> tuple[BinancePrivatePayloadTranslation, ...]:
        """Translate raw payloads into canonical runtime models via the authoritative bridge."""

        return translator.translate_payloads(payloads=payloads)

    def ingest_events(
        self,
        *,
        events: tuple[BinancePrivateStreamEvent, ...] = (),
        cursor: str | None = None,
        has_gap: bool = False,
        stream_state: BinancePrivateStreamState = BinancePrivateStreamState.STREAMING,
    ) -> BinancePrivateStreamBatch:
        """Return a normalized batch for downstream reconciliation and observability."""

        family_counts: dict[str, int] = {}
        last_event_time = None
        last_sequence_id = None
        terminated = stream_state is BinancePrivateStreamState.TERMINATED
        alerts: list[str] = []
        for event in events:
            family_counts[event.event_family.value] = family_counts.get(event.event_family.value, 0) + 1
            if last_event_time is None or event.event_time > last_event_time:
                last_event_time = event.event_time
            if event.sequence_id is not None:
                last_sequence_id = event.sequence_id
            if event.event_family is BinancePrivateEventFamily.STREAM_STATUS:
                terminated = True
        if has_gap:
            alerts.append("private-stream gap detected; reconciliation fallback required")
        if terminated:
            alerts.append("private stream terminated; session reinitialization required")
        return BinancePrivateStreamBatch(
            events=events,
            source="binance_private_stream",
            cursor=cursor,
            has_gap=has_gap,
            alerts=tuple(alerts),
            stream_state=(
                BinancePrivateStreamState.TERMINATED
                if terminated
                else stream_state
            ),
            family_counts=family_counts,
            last_event_time=last_event_time,
            last_sequence_id=last_sequence_id,
        )

    def build_health_snapshot(
        self,
        *,
        session: BinancePrivateStreamSession,
        batch: BinancePrivateStreamBatch | None = None,
        occurred_at: datetime | None = None,
        last_reconnect_at: datetime | None = None,
    ) -> BinancePrivateStreamHealth:
        """Build operator-facing health from session and latest batch state."""

        resolved_time = occurred_at
        if batch is not None and batch.last_event_time is not None:
            resolved_time = batch.last_event_time
        elif resolved_time is None:
            resolved_time = session.last_message_at
        stream_state = session.state
        alerts = list(session.alerts)
        is_authoritative = session.state is BinancePrivateStreamState.STREAMING
        if batch is not None:
            stream_state = batch.stream_state
            alerts.extend(batch.alerts)
            if batch.has_gap and stream_state is not BinancePrivateStreamState.TERMINATED:
                stream_state = BinancePrivateStreamState.DEGRADED
            is_authoritative = stream_state is BinancePrivateStreamState.STREAMING
        watchdog = self.check_runtime_health(
            session=session,
            occurred_at=occurred_at,
        )
        if watchdog is not None and stream_state is not BinancePrivateStreamState.TERMINATED:
            stream_state = watchdog.state
            alerts.extend(watchdog.alerts)
            is_authoritative = watchdog.is_authoritative
        return BinancePrivateStreamHealth(
            state=stream_state,
            reconnect_attempts=session.reconnect_attempts,
            last_message_at=resolved_time,
            last_reconnect_at=last_reconnect_at,
            session_expires_at=session.expires_at,
            is_authoritative=is_authoritative,
            alerts=tuple(dict.fromkeys(alerts)),
        )

    def check_runtime_health(
        self,
        *,
        session: BinancePrivateStreamSession,
        occurred_at: datetime | None,
    ) -> BinancePrivateStreamHealth | None:
        """Return watchdog health for heartbeat overdue or expired private-stream state."""

        if occurred_at is None:
            return None
        if session.expires_at is not None and occurred_at >= session.expires_at:
            return BinancePrivateStreamHealth(
                state=BinancePrivateStreamState.TERMINATED,
                reconnect_attempts=session.reconnect_attempts,
                last_message_at=session.last_message_at,
                session_expires_at=session.expires_at,
                is_authoritative=False,
                alerts=("private stream subscription expired; reauthentication required",),
            )
        if (
            session.last_message_at is not None
            and occurred_at - session.last_message_at > self.heartbeat_timeout
        ):
            return BinancePrivateStreamHealth(
                state=BinancePrivateStreamState.DEGRADED,
                reconnect_attempts=session.reconnect_attempts,
                last_message_at=session.last_message_at,
                session_expires_at=session.expires_at,
                is_authoritative=False,
                alerts=("private stream heartbeat overdue",),
            )
        return None

    def map_account_sync_summary(
        self,
        *,
        events: tuple[BinancePrivateStreamEvent, ...],
    ) -> BinanceAccountSyncSummary | None:
        """Summarize balance/account updates for portfolio sync wiring."""

        account_events = tuple(
            event for event in events if event.event_family is BinancePrivateEventFamily.ACCOUNT_UPDATE
        )
        if not account_events:
            return None
        assets: list[str] = []
        for event in account_events:
            payload_summary = event.payload_summary or {}
            updated = payload_summary.get("updated_assets")
            if updated:
                assets.extend(asset for asset in updated.split(",") if asset)
            asset = payload_summary.get("asset")
            if asset:
                assets.append(asset)
        return BinanceAccountSyncSummary(
            account_scope=self.account_scope,
            event_time=account_events[-1].event_time,
            updated_assets=tuple(dict.fromkeys(assets)),
            alerts=(),
        )

    def events_for_reconciliation(
        self,
        *,
        batch: BinancePrivateStreamBatch,
    ) -> tuple[BinancePrivateStreamEvent, ...]:
        """Return only order/execution relevant events for reconciliation."""

        return tuple(
            event for event in batch.events if event.event_family is BinancePrivateEventFamily.ORDER_UPDATE
        )

    def terminated_stream_health(
        self,
        *,
        occurred_at: datetime,
        reason: str,
    ) -> BinancePrivateStreamHealth:
        """Return operator-visible health after stream termination/invalidation."""

        return BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.TERMINATED,
            reconnect_attempts=0,
            last_message_at=occurred_at,
            session_expires_at=None,
            is_authoritative=False,
            alerts=(f"private stream terminated: {reason}",),
        )
