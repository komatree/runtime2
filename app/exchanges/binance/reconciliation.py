"""Binance order status reconciliation skeleton."""

from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Protocol

from app.storage.reconciliation_state import BinanceReconciliationCursorSnapshot

from .order_client import BinanceOrderClient
from .order_client import BinanceOrderStatusLookupTransport
from .private_payload_translator import BinancePrivatePayloadTranslator
from .private_stream_client import BinancePrivateStreamClient
from .reconciliation_coordinator import BinanceReconciliationCoordinator
from .reconciliation_coordinator import BinanceReconciliationWorkflowResult
from .models import BinanceOrderLookupResult
from .models import BinanceOrderReconciliationResult
from .models import BinancePrivateStreamEvent
from .models import BinancePrivatePayloadTranslation
from .models import BinancePrivateStreamHealth
from .models import BinanceRecoveryAction
from .models import BinanceRecoveryConvergenceState
from .models import BinanceRecoveryPlan
from .models import BinanceRecoveryTriggerReason
from .models import BinanceStatusQueryHealth


class BinanceReconciliationStateStore(Protocol):
    """Persistent state boundary for replay-safe reconciliation recovery."""

    def resume_expected_order_ids(self, expected_order_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return expected ids plus unresolved ids from prior restart-safe state."""

    def load_recovery_resume_state(self) -> BinanceReconciliationCursorSnapshot:
        """Return the latest persisted state for restart-safe recovery decisions."""

    def register_lookup_results(
        self,
        *,
        lookup_results: tuple[BinanceOrderLookupResult, ...],
        occurred_at: datetime,
        cursor_token: str | None,
    ) -> tuple[BinanceOrderLookupResult, ...]:
        """Assign replay-safe attempt numbers and ignore duplicated attempts."""

    def persist_workflow_state(
        self,
        *,
        workflow: BinanceReconciliationWorkflowResult,
        occurred_at: datetime,
        cursor_token: str | None,
        has_gap: bool,
    ) -> BinanceReconciliationCursorSnapshot:
        """Persist unresolved recovery state for restart-safe resume."""


@dataclass(frozen=True)
class BinanceTransportReconciliationResult:
    """Transport-backed reconciliation result for operator-visible recovery flow."""

    batch_health: BinancePrivateStreamHealth | None
    translations: tuple[BinancePrivatePayloadTranslation, ...]
    reconciliation_result: BinanceOrderReconciliationResult
    workflow_result: BinanceReconciliationWorkflowResult
    status_query_health: tuple[BinanceStatusQueryHealth, ...]
    cursor_snapshot: BinanceReconciliationCursorSnapshot | None = None


@dataclass(frozen=True)
class BinanceReconciliationService:
    """Stub for private-event and REST-backed reconciliation.

    Responsibilities:
    - reconcile open orders against authoritative private stream and REST views
    - detect missing or unknown executions
    - produce alertable summaries before canonical portfolio updates

    Pre-live blockers:
    - no fully automated recovery scheduler yet
    - replay-safe persistence exists but operational thresholds remain conservative
    - production cutover still requires long-running transport validation
    """

    max_automatic_recovery_rounds: int = 3

    def reconcile(
        self,
        *,
        expected_order_ids: tuple[str, ...],
        private_events: tuple[BinancePrivateStreamEvent, ...] = (),
    ) -> BinanceOrderReconciliationResult:
        """Return a stub reconciliation summary with unknown execution hooks."""

        seen_ids = {event.sequence_id for event in private_events if event.sequence_id}
        unknown_execution_ids = tuple(
            event.sequence_id
            for event in private_events
            if event.sequence_id and event.sequence_id not in expected_order_ids
        )
        matched = tuple(order_id for order_id in expected_order_ids if order_id in seen_ids)
        missing = tuple(order_id for order_id in expected_order_ids if order_id not in seen_ids)
        alerts: list[str] = []
        if missing:
            alerts.append("missing private-stream updates for one or more orders")
        if unknown_execution_ids:
            alerts.append("unknown execution ids observed; recovery flow required")
        recovery_actions: list[BinanceRecoveryAction] = []
        if missing:
            recovery_actions.extend(
                [
                    BinanceRecoveryAction.QUERY_ORDER_STATUS,
                    BinanceRecoveryAction.HOLD_PORTFOLIO_MUTATION,
                ]
            )
        if unknown_execution_ids:
            recovery_actions.extend(
                [
                    BinanceRecoveryAction.QUERY_OPEN_ORDERS,
                    BinanceRecoveryAction.ESCALATE_OPERATOR,
                ]
            )
        return BinanceOrderReconciliationResult(
            matched_order_ids=matched,
            missing_order_ids=missing,
            unknown_execution_ids=unknown_execution_ids,
            alerts=tuple(alerts),
            recovery_actions=tuple(recovery_actions),
        )

    def lookup_stub(
        self,
        *,
        lookup_field: str,
        lookup_value: str,
    ) -> BinanceOrderLookupResult:
        """Return a placeholder order lookup result for future REST convergence."""

        return BinanceOrderLookupResult(
            found=False,
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            source="order_status_placeholder",
            status_summary=None,
            alert="transport not implemented; lookup is placeholder only",
        )

    def build_recovery_plan(self, result: BinanceOrderReconciliationResult) -> BinanceRecoveryPlan:
        """Build a placeholder recovery plan from reconciliation output."""

        lookup_requests: list[tuple[str, str]] = []
        for order_id in result.missing_order_ids:
            lookup_requests.append(("exchange_order_id", order_id))
        for order_id in result.unknown_execution_ids:
            lookup_requests.append(("exchange_order_id", order_id))
        return BinanceRecoveryPlan(
            reason="reconciliation uncertainty",
            actions=result.recovery_actions or (BinanceRecoveryAction.NONE,),
            order_lookup_requests=tuple(lookup_requests),
            alerts=result.alerts,
        )

    def build_automatic_recovery_plan(
        self,
        *,
        result: BinanceOrderReconciliationResult,
        gap_detected: bool,
        resumed_from_snapshot: bool,
    ) -> BinanceRecoveryPlan:
        """Build an explicit automatic recovery plan when gap or unresolved state is active."""

        lookup_requests: list[tuple[str, str]] = []
        for order_id in (*result.missing_order_ids, *result.unknown_execution_ids):
            request = ("exchange_order_id", order_id)
            if request not in lookup_requests:
                lookup_requests.append(request)

        trigger_reason = BinanceRecoveryTriggerReason.NOT_REQUIRED
        reason = "no automatic recovery required"
        if gap_detected:
            trigger_reason = BinanceRecoveryTriggerReason.PRIVATE_STREAM_GAP
            reason = "automatic recovery triggered by private-stream gap"
        elif resumed_from_snapshot:
            trigger_reason = BinanceRecoveryTriggerReason.RESTART_RESUME
            reason = "automatic recovery resumed from persisted unresolved reconciliation state"
        elif result.unknown_execution_ids:
            trigger_reason = BinanceRecoveryTriggerReason.UNKNOWN_EXECUTION
            reason = "automatic recovery triggered by unknown execution"
        elif result.missing_order_ids:
            trigger_reason = BinanceRecoveryTriggerReason.MISSING_PRIVATE_UPDATES
            reason = "automatic recovery triggered by missing private-stream updates"

        automatic = bool(lookup_requests) and trigger_reason is not BinanceRecoveryTriggerReason.NOT_REQUIRED
        alerts = list(result.alerts)
        if automatic:
            alerts.append(reason)
        return BinanceRecoveryPlan(
            reason=reason,
            actions=result.recovery_actions or (BinanceRecoveryAction.NONE,),
            order_lookup_requests=tuple(lookup_requests),
            alerts=tuple(dict.fromkeys(alerts)),
            trigger_reason=trigger_reason,
            automatic_triggered=automatic,
            gap_detected=gap_detected,
            resumed_from_snapshot=resumed_from_snapshot,
        )

    def coordinate_recovery(
        self,
        *,
        reconciliation_result: BinanceOrderReconciliationResult,
        lookup_results: tuple[BinanceOrderLookupResult, ...] = (),
    ) -> BinanceReconciliationWorkflowResult:
        """Build explicit reconciliation workflow state transitions."""

        return BinanceReconciliationCoordinator().coordinate(
            reconciliation_result=reconciliation_result,
            lookup_results=lookup_results,
        )

    def reconcile_with_transports(
        self,
        *,
        expected_order_ids: tuple[str, ...],
        private_payloads: tuple[dict[str, object], ...],
        private_stream_client: BinancePrivateStreamClient,
        translator: BinancePrivatePayloadTranslator,
        order_client: BinanceOrderClient,
        lookup_transport: BinanceOrderStatusLookupTransport,
        state_store: BinanceReconciliationStateStore | None = None,
        session=None,
        cursor: str | None = None,
        has_gap: bool = False,
        occurred_at: datetime | None = None,
    ) -> BinanceTransportReconciliationResult:
        """Drive reconciliation from real adapter transports and canonical translation."""

        effective_time = occurred_at or datetime.now(UTC)
        resume_snapshot = (
            state_store.load_recovery_resume_state()
            if state_store is not None
            else None
        )
        resumed_expected_order_ids = (
            state_store.resume_expected_order_ids(expected_order_ids)
            if state_store is not None
            else expected_order_ids
        )
        batch = private_stream_client.ingest_payloads(
            payloads=private_payloads,
            cursor=cursor,
            has_gap=has_gap,
        )
        translations = private_stream_client.translate_payloads(
            payloads=private_payloads,
            translator=translator,
        )
        private_events = private_stream_client.events_for_reconciliation(batch=batch)
        reconciliation_result = self.reconcile(
            expected_order_ids=resumed_expected_order_ids,
            private_events=private_events,
        )
        gap_detected = has_gap or batch.has_gap or (
            resume_snapshot is not None and resume_snapshot.gap_active
        )
        resumed_from_snapshot = bool(
            resume_snapshot is not None and resume_snapshot.unresolved_order_ids
        )
        recovery_plan = self.build_automatic_recovery_plan(
            result=reconciliation_result,
            gap_detected=gap_detected,
            resumed_from_snapshot=resumed_from_snapshot,
        )

        lookup_results: list[BinanceOrderLookupResult] = []
        status_query_health: list[BinanceStatusQueryHealth] = []
        max_rounds = self.max_automatic_recovery_rounds if recovery_plan.automatic_triggered else 1
        terminal_statuses = {"filled", "cancelled", "rejected", "expired"}
        latest_by_lookup_value: dict[str, BinanceOrderLookupResult] = {}
        for _round in range(max_rounds):
            for lookup_field, lookup_value in recovery_plan.order_lookup_requests:
                if lookup_field == "client_order_id":
                    lookup = order_client.lookup_order_by_client_id(
                        lookup_value,
                        transport=lookup_transport,
                    )
                else:
                    lookup = order_client.lookup_order_by_exchange_id(
                        lookup_value,
                        transport=lookup_transport,
                    )
                lookup_results.append(lookup)
                latest_by_lookup_value[lookup.lookup_value] = lookup
                health = lookup_transport.last_health()
                if health is not None:
                    status_query_health.append(health)
            if not recovery_plan.automatic_triggered or not latest_by_lookup_value:
                break
            if all(
                lookup.found and lookup.status_summary in terminal_statuses
                for lookup in latest_by_lookup_value.values()
            ):
                break

        replay_safe_lookup_results = (
            state_store.register_lookup_results(
                lookup_results=tuple(lookup_results),
                occurred_at=effective_time,
                cursor_token=cursor,
            )
            if state_store is not None
            else tuple(lookup_results)
        )

        workflow_result = self.coordinate_recovery(
            reconciliation_result=reconciliation_result,
            lookup_results=replay_safe_lookup_results,
        )
        convergence_state = "not_required"
        if workflow_result.recovery_summaries:
            if any(
                summary.convergence_state
                is BinanceRecoveryConvergenceState.UNRECONCILED_MANUAL_ATTENTION
                for summary in workflow_result.recovery_summaries
            ):
                convergence_state = BinanceRecoveryConvergenceState.UNRECONCILED_MANUAL_ATTENTION.value
            elif any(
                summary.convergence_state is BinanceRecoveryConvergenceState.PENDING
                for summary in workflow_result.recovery_summaries
            ):
                convergence_state = BinanceRecoveryConvergenceState.PENDING.value
            else:
                convergence_state = BinanceRecoveryConvergenceState.CONVERGED_TERMINAL.value
        workflow_result = replace(
            workflow_result,
            alerts=tuple(dict.fromkeys((*workflow_result.alerts, *recovery_plan.alerts))),
            recovery_trigger_reason=recovery_plan.trigger_reason.value,
            recovery_automatic=recovery_plan.automatic_triggered,
            gap_detected=recovery_plan.gap_detected,
            resumed_from_snapshot=recovery_plan.resumed_from_snapshot,
            convergence_state=convergence_state,
        )
        cursor_snapshot = (
            state_store.persist_workflow_state(
                workflow=workflow_result,
                occurred_at=effective_time,
                cursor_token=cursor,
                has_gap=gap_detected,
            )
            if state_store is not None
            else None
        )
        batch_health = None
        if session is not None:
            batch_health = private_stream_client.build_health_snapshot(
                session=session,
                batch=batch,
                occurred_at=effective_time,
            )
        return BinanceTransportReconciliationResult(
            batch_health=batch_health,
            translations=translations,
            reconciliation_result=reconciliation_result,
            workflow_result=workflow_result,
            status_query_health=tuple(status_query_health),
            cursor_snapshot=cursor_snapshot,
        )
