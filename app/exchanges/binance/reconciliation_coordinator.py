"""Binance reconciliation coordinator for explicit recovery workflow visibility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import OrderSide
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import OrderType
from app.contracts import FillEvent
from app.contracts import ReconciliationEvent
from app.contracts import ReconciliationState
from app.execution import OrderLifecycleMachine

from .models import BinanceOrderLookupResult
from .models import BinanceRecoveryConvergenceState
from .models import BinanceRecoverySummary
from .models import BinanceOrderReconciliationResult


@dataclass(frozen=True)
class BinanceReconciliationWorkflowResult:
    """Inspectable recovery workflow result with explicit state transitions."""

    reconciliation_result: BinanceOrderReconciliationResult
    order_states: tuple[OrderState, ...]
    recovered_fill_events: tuple[FillEvent, ...]
    reconciliation_events: tuple[ReconciliationEvent, ...]
    recovery_attempts: tuple[BinanceOrderLookupResult, ...]
    recovery_summaries: tuple[BinanceRecoverySummary, ...]
    alerts: tuple[str, ...]
    recovery_trigger_reason: str | None = None
    recovery_automatic: bool = False
    gap_detected: bool = False
    resumed_from_snapshot: bool = False
    convergence_state: str | None = None


@dataclass(frozen=True)
class BinanceReconciliationCoordinator:
    """Coordinates recovery state transitions without hiding transport gaps."""

    venue: str = "binance"
    lifecycle: OrderLifecycleMachine = OrderLifecycleMachine()
    max_recovery_attempts: int = 3

    def coordinate(
        self,
        *,
        reconciliation_result: BinanceOrderReconciliationResult,
        lookup_results: tuple[BinanceOrderLookupResult, ...] = (),
        occurred_at: datetime | None = None,
    ) -> BinanceReconciliationWorkflowResult:
        effective_time = occurred_at or datetime.now(UTC)
        order_states: list[OrderState] = []
        events: list[ReconciliationEvent] = []
        alerts = list(reconciliation_result.alerts)
        recovery_summaries: list[BinanceRecoverySummary] = []
        recovered_fill_events: list[FillEvent] = []

        for order_id in reconciliation_result.matched_order_ids:
            base_state = self._make_order_state(
                order_id=order_id,
                reconciliation_state=ReconciliationState.SUBMIT_SENT,
                occurred_at=effective_time,
                detail="submit observed or matched by reconciliation",
            )
            acknowledged, _ = self.lifecycle.acknowledge(
                base_state,
                order_id=order_id,
                occurred_at=effective_time,
            )
            order_states.append(acknowledged)

        for order_id in reconciliation_result.unknown_execution_ids:
            base_state, _ = self.lifecycle.mark_recovering(
                self._make_order_state(
                    order_id=order_id,
                    reconciliation_state=ReconciliationState.UNKNOWN_EXECUTION,
                    occurred_at=effective_time,
                    detail="unknown execution detected; transport convergence required",
                ),
                occurred_at=effective_time,
                detail="unknown execution detected; recovery started",
                reconciliation_state=ReconciliationState.UNKNOWN_EXECUTION,
            )
            order_states.append(base_state)
            events.append(
                ReconciliationEvent(
                    venue=self.venue,
                    order_id=order_id,
                    reconciliation_state=ReconciliationState.UNKNOWN_EXECUTION,
                    occurred_at=effective_time,
                    detail="unknown execution detected; transport convergence required",
                )
            )

        for order_id in reconciliation_result.missing_order_ids:
            base_state, _ = self.lifecycle.mark_recovering(
                self._make_order_state(
                    order_id=order_id,
                    reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
                    occurred_at=effective_time,
                    detail="status query pending for missing order update",
                ),
                occurred_at=effective_time,
                detail="status query pending for missing order update",
                reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
            )
            order_states.append(base_state)
            events.append(
                ReconciliationEvent(
                    venue=self.venue,
                    order_id=order_id,
                    reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
                    occurred_at=effective_time,
                    detail="status query pending for missing order update",
                )
            )

        lookups_by_value: dict[str, list[BinanceOrderLookupResult]] = {}
        for lookup in lookup_results:
            lookups_by_value.setdefault(lookup.lookup_value, []).append(lookup)

        for lookup_value, attempts in lookups_by_value.items():
            last_lookup = attempts[-1]
            detail = last_lookup.alert or "recovery unresolved"
            base_state, _ = self.lifecycle.mark_recovering(
                self._make_order_state(
                    order_id=lookup_value,
                    reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
                    occurred_at=effective_time,
                    detail="status lookup initiated for reconciliation recovery",
                ),
                occurred_at=effective_time,
                detail="recovery in progress",
                reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
            )
            state = ReconciliationState.STATUS_QUERY_PENDING
            convergence_state = BinanceRecoveryConvergenceState.PENDING
            resolved_order = base_state

            terminal_lookup = next(
                (
                    attempt
                    for attempt in reversed(attempts)
                    if attempt.found and attempt.status_summary in {"filled", "cancelled", "rejected", "expired"}
                ),
                None,
            )

            if terminal_lookup is not None:
                state = ReconciliationState.RECOVERED_TERMINAL_STATE
                convergence_state = BinanceRecoveryConvergenceState.CONVERGED_TERMINAL
                detail = f"recovered via status lookup after {len(attempts)} attempt(s): {terminal_lookup.status_summary}"
                resolved_status = {
                    "filled": OrderStatus.FILLED,
                    "cancelled": OrderStatus.CANCELED,
                    "rejected": OrderStatus.REJECTED,
                    "expired": OrderStatus.EXPIRED,
                }[terminal_lookup.status_summary]
                if terminal_lookup.recovered_order_state is not None:
                    base_state = terminal_lookup.recovered_order_state
                resolved_order, _ = self.lifecycle.resolve_recovery(
                    base_state,
                    resolved_status=resolved_status,
                    occurred_at=effective_time,
                    detail=detail,
                )
                recovered_fill_events.extend(terminal_lookup.recovered_fill_events)
            elif last_lookup.found:
                detail = f"non-terminal recovery status after {len(attempts)} attempt(s): {last_lookup.status_summary}"
                if last_lookup.recovered_order_state is not None:
                    base_state = last_lookup.recovered_order_state
            elif len(attempts) >= self.max_recovery_attempts:
                state = ReconciliationState.UNRECONCILED_MANUAL_ATTENTION
                convergence_state = BinanceRecoveryConvergenceState.UNRECONCILED_MANUAL_ATTENTION
                detail = (
                    f"recovery unresolved after {len(attempts)} attempt(s): "
                    f"{last_lookup.alert or 'manual attention required'}"
                )
                resolved_order, _ = self.lifecycle.mark_unreconciled(
                    base_state,
                    occurred_at=effective_time,
                    detail=detail,
                )
                alerts.append(
                    f"manual attention required for {last_lookup.lookup_field}={lookup_value} "
                    f"after {len(attempts)} attempt(s)"
                )

            order_states.append(
                OrderState(
                    venue=resolved_order.venue,
                    order_id=resolved_order.order_id,
                    client_order_id=resolved_order.client_order_id,
                    instrument_id=resolved_order.instrument_id,
                    side=resolved_order.side,
                    order_type=resolved_order.order_type,
                    status=resolved_order.status,
                    requested_quantity=resolved_order.requested_quantity,
                    filled_quantity=resolved_order.filled_quantity,
                    remaining_quantity=resolved_order.remaining_quantity,
                    last_update_time=resolved_order.last_update_time,
                    limit_price=resolved_order.limit_price,
                    average_fill_price=resolved_order.average_fill_price,
                    reconciliation_state=state,
                    reconciliation_detail=detail,
                )
            )
            events.append(
                ReconciliationEvent(
                    venue=self.venue,
                    order_id=lookup_value,
                    reconciliation_state=state,
                    occurred_at=effective_time,
                    detail=detail,
                )
            )
            recovery_summaries.append(
                BinanceRecoverySummary(
                    order_id=lookup_value,
                    attempts=len(attempts),
                    convergence_state=convergence_state,
                    last_lookup_field=last_lookup.lookup_field,
                    last_lookup_source=last_lookup.source,
                    terminal_status=terminal_lookup.status_summary if terminal_lookup is not None else None,
                    detail=detail,
                )
            )

        convergence_state = "not_required"
        if recovery_summaries:
            if any(
                summary.convergence_state
                is BinanceRecoveryConvergenceState.UNRECONCILED_MANUAL_ATTENTION
                for summary in recovery_summaries
            ):
                convergence_state = BinanceRecoveryConvergenceState.UNRECONCILED_MANUAL_ATTENTION.value
            elif any(
                summary.convergence_state is BinanceRecoveryConvergenceState.PENDING
                for summary in recovery_summaries
            ):
                convergence_state = BinanceRecoveryConvergenceState.PENDING.value
            else:
                convergence_state = BinanceRecoveryConvergenceState.CONVERGED_TERMINAL.value

        return BinanceReconciliationWorkflowResult(
            reconciliation_result=reconciliation_result,
            order_states=tuple(order_states),
            recovered_fill_events=tuple(recovered_fill_events),
            reconciliation_events=tuple(events),
            recovery_attempts=lookup_results,
            recovery_summaries=tuple(recovery_summaries),
            alerts=tuple(alerts),
            convergence_state=convergence_state,
        )

    def _make_order_state(
        self,
        *,
        order_id: str,
        reconciliation_state: ReconciliationState,
        occurred_at: datetime,
        detail: str,
    ) -> OrderState:
        return OrderState(
            venue=self.venue,
            order_id=order_id,
            client_order_id=order_id,
            instrument_id="UNKNOWN",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.NEW,
            requested_quantity=Decimal("0"),
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0"),
            last_update_time=occurred_at,
            reconciliation_state=reconciliation_state,
            reconciliation_detail=detail,
        )
