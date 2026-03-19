"""Explicit order lifecycle state machine shared across runtime modes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import ExecutionIntent
from app.contracts import FillEvent
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import ReconciliationState


@dataclass(frozen=True)
class OrderLifecycleTransition:
    """Auditable lifecycle transition produced by the shared state machine."""

    order_id: str
    from_status: OrderStatus
    to_status: OrderStatus
    detail: str
    occurred_at: object


@dataclass(frozen=True)
class OrderLifecycleMachine:
    """Canonical order lifecycle transition logic.

    Non-goals:
    - venue payload parsing
    - persistence
    - retry scheduling
    """

    def new_from_intent(self, intent: ExecutionIntent) -> OrderState:
        """Create a canonical order state at submission intent time."""

        return OrderState(
            venue=intent.venue,
            order_id=f"pending:{intent.intent_id}",
            client_order_id=intent.intent_id,
            instrument_id=intent.instrument_id,
            side=intent.side,
            order_type=intent.order_type,
            status=OrderStatus.NEW,
            requested_quantity=intent.quantity,
            filled_quantity=Decimal("0"),
            remaining_quantity=intent.quantity,
            last_update_time=intent.submitted_at,
            limit_price=intent.limit_price,
        )

    def acknowledge(self, order_state: OrderState, *, order_id: str | None = None, occurred_at) -> tuple[OrderState, OrderLifecycleTransition]:
        """Move a new order into acknowledged state."""

        updated = OrderState(
            venue=order_state.venue,
            order_id=order_id or order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=OrderStatus.ACKNOWLEDGED,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=order_state.filled_quantity,
            remaining_quantity=order_state.remaining_quantity,
            last_update_time=occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=order_state.average_fill_price,
            reconciliation_state=order_state.reconciliation_state,
            reconciliation_detail=order_state.reconciliation_detail,
        )
        return updated, self._transition(order_state, updated, "order acknowledged", occurred_at)

    def apply_fill(self, order_state: OrderState, *, fill_event: FillEvent) -> tuple[OrderState, OrderLifecycleTransition]:
        """Apply a fill and move into partial or terminal filled state."""

        cumulative_filled = order_state.filled_quantity + fill_event.quantity
        remaining_quantity = order_state.requested_quantity - cumulative_filled
        status = OrderStatus.FILLED if remaining_quantity == Decimal("0") else OrderStatus.PARTIALLY_FILLED
        average_fill_price = self._average_fill_price(
            order_state=order_state,
            fill_event=fill_event,
            cumulative_filled=cumulative_filled,
        )
        updated = OrderState(
            venue=order_state.venue,
            order_id=order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=status,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=cumulative_filled,
            remaining_quantity=remaining_quantity,
            last_update_time=fill_event.occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=average_fill_price,
            reconciliation_state=order_state.reconciliation_state,
            reconciliation_detail=order_state.reconciliation_detail,
        )
        detail = "order fully filled" if status is OrderStatus.FILLED else "order partially filled"
        return updated, self._transition(order_state, updated, detail, fill_event.occurred_at)

    def cancel(self, order_state: OrderState, *, occurred_at, detail: str = "order canceled") -> tuple[OrderState, OrderLifecycleTransition]:
        """Cancel a non-terminal order without mutating filled quantity."""

        updated = self._replace_status(order_state, status=OrderStatus.CANCELED, occurred_at=occurred_at)
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def expire(self, order_state: OrderState, *, occurred_at, detail: str = "order expired") -> tuple[OrderState, OrderLifecycleTransition]:
        """Expire a non-terminal order without mutating filled quantity."""

        updated = self._replace_status(order_state, status=OrderStatus.EXPIRED, occurred_at=occurred_at)
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def reject(self, order_state: OrderState, *, occurred_at, detail: str = "order rejected") -> tuple[OrderState, OrderLifecycleTransition]:
        """Reject a non-terminal order without mutating filled quantity."""

        updated = self._replace_status(order_state, status=OrderStatus.REJECTED, occurred_at=occurred_at)
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def mark_recovering(
        self,
        order_state: OrderState,
        *,
        occurred_at,
        detail: str,
        reconciliation_state: ReconciliationState = ReconciliationState.UNKNOWN_EXECUTION,
    ) -> tuple[OrderState, OrderLifecycleTransition]:
        """Move an order into explicit recovery mode during reconciliation uncertainty."""

        updated = OrderState(
            venue=order_state.venue,
            order_id=order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=OrderStatus.RECOVERING,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=order_state.filled_quantity,
            remaining_quantity=order_state.remaining_quantity,
            last_update_time=occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=order_state.average_fill_price,
            reconciliation_state=reconciliation_state,
            reconciliation_detail=detail,
        )
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def mark_unreconciled(self, order_state: OrderState, *, occurred_at, detail: str) -> tuple[OrderState, OrderLifecycleTransition]:
        """Move an order into explicit unreconciled state after failed recovery."""

        updated = OrderState(
            venue=order_state.venue,
            order_id=order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=OrderStatus.UNRECONCILED,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=order_state.filled_quantity,
            remaining_quantity=order_state.remaining_quantity,
            last_update_time=occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=order_state.average_fill_price,
            reconciliation_state=ReconciliationState.UNRECONCILED_MANUAL_ATTENTION,
            reconciliation_detail=detail,
        )
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def resolve_recovery(
        self,
        order_state: OrderState,
        *,
        resolved_status: OrderStatus,
        occurred_at,
        detail: str,
    ) -> tuple[OrderState, OrderLifecycleTransition]:
        """Resolve a recovering/unreconciled order into a canonical lifecycle state."""

        updated = OrderState(
            venue=order_state.venue,
            order_id=order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=resolved_status,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=order_state.filled_quantity,
            remaining_quantity=order_state.remaining_quantity,
            last_update_time=occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=order_state.average_fill_price,
            reconciliation_state=ReconciliationState.RECOVERED_TERMINAL_STATE,
            reconciliation_detail=detail,
        )
        return updated, self._transition(order_state, updated, detail, occurred_at)

    def _replace_status(self, order_state: OrderState, *, status: OrderStatus, occurred_at) -> OrderState:
        return OrderState(
            venue=order_state.venue,
            order_id=order_state.order_id,
            client_order_id=order_state.client_order_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            order_type=order_state.order_type,
            status=status,
            requested_quantity=order_state.requested_quantity,
            filled_quantity=order_state.filled_quantity,
            remaining_quantity=order_state.remaining_quantity,
            last_update_time=occurred_at,
            limit_price=order_state.limit_price,
            average_fill_price=order_state.average_fill_price,
            reconciliation_state=order_state.reconciliation_state,
            reconciliation_detail=order_state.reconciliation_detail,
        )

    def _average_fill_price(
        self,
        *,
        order_state: OrderState,
        fill_event: FillEvent,
        cumulative_filled: Decimal,
    ) -> Decimal:
        prior_filled = order_state.filled_quantity
        prior_avg = order_state.average_fill_price or Decimal("0")
        return ((prior_filled * prior_avg) + (fill_event.quantity * fill_event.price)) / cumulative_filled

    def _transition(
        self,
        before: OrderState,
        after: OrderState,
        detail: str,
        occurred_at,
    ) -> OrderLifecycleTransition:
        return OrderLifecycleTransition(
            order_id=after.order_id,
            from_status=before.status,
            to_status=after.status,
            detail=detail,
            occurred_at=occurred_at,
        )
