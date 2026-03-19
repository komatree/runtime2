"""Unified operator-facing exchange health aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Any

from app.contracts import ReconciliationState

from .models import ExchangeComponentHealth
from .models import ExchangeHealthSnapshot
from .models import ExchangeHealthState


def current_or_unknown_exchange_health(
    *,
    venue: str | None,
    provider: Any | None,
) -> ExchangeHealthSnapshot | None:
    """Return current exchange health or an explicit unknown snapshot for Binance paths."""

    if provider is not None:
        snapshot = provider.current_health()
        if snapshot is not None:
            return snapshot
    normalized_venue = (venue or "").strip().lower()
    if normalized_venue == "binance":
        return BinanceExchangeHealthService(venue="binance").build_snapshot()
    return None


@dataclass(frozen=True)
class BinanceExchangeHealthService:
    """Aggregates Binance transport/recovery/clock health into one operator view."""

    venue: str = "binance"

    def build_snapshot(
        self,
        *,
        private_stream_health: Any | None = None,
        reconciliation_workflow: Any | None = None,
        clock_status: Any | None = None,
        status_query_health: tuple[Any, ...] = (),
        cursor_snapshot: Any | None = None,
        generated_at: datetime | None = None,
    ) -> ExchangeHealthSnapshot:
        """Return one operator-readable exchange health snapshot."""

        private_stream = self._private_stream_component(private_stream_health)
        reconciliation = self._reconciliation_component(reconciliation_workflow, cursor_snapshot)
        clock_sync = self._clock_component(clock_status)
        status_query = self._status_query_component(status_query_health)
        overall = self._overall_state(
            private_stream.state,
            reconciliation.state,
            clock_sync.state,
            status_query.state,
        )
        alerts = tuple(
            dict.fromkeys(
                (
                    *private_stream.alerts,
                    *reconciliation.alerts,
                    *clock_sync.alerts,
                    *status_query.alerts,
                )
            )
        )
        return ExchangeHealthSnapshot(
            venue=self.venue,
            generated_at=generated_at or datetime.now(UTC),
            overall_state=overall,
            private_stream=private_stream,
            reconciliation=reconciliation,
            clock_sync=clock_sync,
            status_query=status_query,
            alerts=alerts,
        )

    def render_operator_summary(self, *, snapshot: ExchangeHealthSnapshot) -> str:
        """Render a short markdown exchange-health section for operators."""

        alerts = ", ".join(snapshot.alerts) or "none"
        return "\n".join(
            [
                "## Exchange Health",
                f"- venue: {snapshot.venue}",
                f"- overall_state: {snapshot.overall_state.value}",
                f"- private_stream: {snapshot.private_stream.state.value} ({snapshot.private_stream.detail})",
                f"- reconciliation: {snapshot.reconciliation.state.value} ({snapshot.reconciliation.detail})",
                f"- clock_sync: {snapshot.clock_sync.state.value} ({snapshot.clock_sync.detail})",
                f"- status_query: {snapshot.status_query.state.value} ({snapshot.status_query.detail})",
                f"- alerts: {alerts}",
            ]
        )

    def _private_stream_component(
        self,
        health: Any | None,
    ) -> ExchangeComponentHealth:
        if health is None:
            return ExchangeComponentHealth(
                component="private_stream",
                state=ExchangeHealthState.UNKNOWN,
                detail="private stream health unavailable",
            )
        state_value = getattr(getattr(health, "state", None), "value", None)
        if state_value == "streaming" and getattr(health, "is_authoritative", False):
            state = ExchangeHealthState.HEALTHY
            detail = "private stream connected and authoritative"
        elif state_value == "terminated":
            state = ExchangeHealthState.FATAL
            detail = "private stream terminated"
        else:
            state = ExchangeHealthState.DEGRADED
            detail = f"private stream {state_value or 'unknown'}"
        return ExchangeComponentHealth(
            component="private_stream",
            state=state,
            detail=detail,
            alerts=tuple(getattr(health, "alerts", ())),
        )

    def _reconciliation_component(
        self,
        workflow: Any | None,
        cursor_snapshot: Any | None,
    ) -> ExchangeComponentHealth:
        unresolved_ids = tuple(getattr(cursor_snapshot, "unresolved_order_ids", ())) if cursor_snapshot is not None else ()
        manual_attention_ids = tuple(getattr(cursor_snapshot, "manual_attention_order_ids", ())) if cursor_snapshot is not None else ()
        if workflow is None and cursor_snapshot is None:
            return ExchangeComponentHealth(
                component="reconciliation",
                state=ExchangeHealthState.UNKNOWN,
                detail="reconciliation health unavailable",
            )

        states = (
            tuple(event.reconciliation_state for event in workflow.reconciliation_events)
            if workflow is not None
            else ()
        )
        if manual_attention_ids or ReconciliationState.UNRECONCILED_MANUAL_ATTENTION in states:
            return ExchangeComponentHealth(
                component="reconciliation",
                state=ExchangeHealthState.FATAL,
                detail="manual attention required",
                alerts=tuple(f"manual attention order: {order_id}" for order_id in manual_attention_ids),
            )
        if (
            unresolved_ids
            or (cursor_snapshot is not None and cursor_snapshot.gap_active)
            or ReconciliationState.UNKNOWN_EXECUTION in states
            or ReconciliationState.STATUS_QUERY_PENDING in states
        ):
            alerts = []
            if cursor_snapshot is not None and bool(getattr(cursor_snapshot, "gap_active", False)):
                alerts.append("private-stream gap recovery active")
            alerts.extend(f"unresolved order: {order_id}" for order_id in unresolved_ids)
            return ExchangeComponentHealth(
                component="reconciliation",
                state=ExchangeHealthState.DEGRADED,
                detail="reconciliation convergence pending",
                alerts=tuple(alerts),
            )
        return ExchangeComponentHealth(
            component="reconciliation",
            state=ExchangeHealthState.HEALTHY,
            detail="reconciliation converged",
            alerts=tuple(getattr(workflow, "alerts", ())) if workflow is not None else (),
        )

    def _clock_component(self, status: Any | None) -> ExchangeComponentHealth:
        if status is None:
            return ExchangeComponentHealth(
                component="clock_sync",
                state=ExchangeHealthState.UNKNOWN,
                detail="clock sync unavailable",
            )
        if bool(getattr(status, "is_uncertain", False)) or not bool(getattr(status, "is_within_tolerance", False)):
            return ExchangeComponentHealth(
                component="clock_sync",
                state=ExchangeHealthState.FATAL,
                detail="clock sync uncertain or out of tolerance",
                alerts=((getattr(status, "alert"),) if getattr(status, "alert", None) else ()),
            )
        return ExchangeComponentHealth(
            component="clock_sync",
            state=ExchangeHealthState.HEALTHY,
            detail="clock sync within tolerance",
            alerts=((getattr(status, "alert"),) if getattr(status, "alert", None) else ()),
        )

    def _status_query_component(
        self,
        health_items: tuple[Any, ...],
    ) -> ExchangeComponentHealth:
        if not health_items:
            return ExchangeComponentHealth(
                component="status_query",
                state=ExchangeHealthState.UNKNOWN,
                detail="no status-query attempts recorded",
            )
        latest = health_items[-1]
        latest_state = getattr(getattr(latest, "state", None), "value", None)
        if latest_state == "success":
            state = ExchangeHealthState.HEALTHY
            detail = "latest signed status query succeeded"
        elif latest_state == "failed":
            state = ExchangeHealthState.DEGRADED
            detail = "latest signed status query failed"
        else:
            state = ExchangeHealthState.DEGRADED
            detail = "status query blocked"
        return ExchangeComponentHealth(
            component="status_query",
            state=state,
            detail=detail,
            alerts=((getattr(latest, "alert"),) if getattr(latest, "alert", None) else ()),
        )

    def _overall_state(self, *states: ExchangeHealthState) -> ExchangeHealthState:
        if ExchangeHealthState.FATAL in states:
            return ExchangeHealthState.FATAL
        if ExchangeHealthState.DEGRADED in states:
            return ExchangeHealthState.DEGRADED
        if all(state is ExchangeHealthState.UNKNOWN for state in states):
            return ExchangeHealthState.UNKNOWN
        return ExchangeHealthState.HEALTHY
