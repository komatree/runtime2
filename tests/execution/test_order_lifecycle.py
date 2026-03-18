"""Shared order lifecycle state machine tests.

TODO:
- Add exchange-normalized amend and replace semantics when adapters support them.
- Add lifecycle persistence tests when transition history is stored directly.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import ExecutionIntent
from app.contracts import FillEvent
from app.contracts import OrderSide
from app.contracts import OrderStatus
from app.contracts import OrderType
from app.contracts import ReconciliationState
from app.contracts import TimeInForce
from app.execution import OrderLifecycleMachine


def test_partial_fill_progression() -> None:
    lifecycle = OrderLifecycleMachine()
    order = lifecycle.new_from_intent(_intent())
    acknowledged, _ = lifecycle.acknowledge(order, order_id="order-1", occurred_at=_dt(0, 1))
    partially_filled, transition = lifecycle.apply_fill(
        acknowledged,
        fill_event=_fill("order-1", quantity="0.4", price="101", occurred_at=_dt(0, 2)),
    )

    assert order.status is OrderStatus.NEW
    assert acknowledged.status is OrderStatus.ACKNOWLEDGED
    assert partially_filled.status is OrderStatus.PARTIALLY_FILLED
    assert partially_filled.filled_quantity == Decimal("0.4")
    assert partially_filled.remaining_quantity == Decimal("0.6")
    assert transition.to_status is OrderStatus.PARTIALLY_FILLED


def test_cancel_flow() -> None:
    lifecycle = OrderLifecycleMachine()
    order = lifecycle.new_from_intent(_intent())
    acknowledged, _ = lifecycle.acknowledge(order, order_id="order-2", occurred_at=_dt(0, 1))
    canceled, transition = lifecycle.cancel(acknowledged, occurred_at=_dt(0, 3))

    assert canceled.status is OrderStatus.CANCELED
    assert canceled.remaining_quantity == Decimal("1")
    assert transition.to_status is OrderStatus.CANCELED


def test_expire_flow() -> None:
    lifecycle = OrderLifecycleMachine()
    order = lifecycle.new_from_intent(_intent())
    acknowledged, _ = lifecycle.acknowledge(order, order_id="order-3", occurred_at=_dt(0, 1))
    expired, transition = lifecycle.expire(acknowledged, occurred_at=_dt(0, 4))

    assert expired.status is OrderStatus.EXPIRED
    assert transition.to_status is OrderStatus.EXPIRED


def test_recovery_after_unknown_execution() -> None:
    lifecycle = OrderLifecycleMachine()
    order = lifecycle.new_from_intent(_intent())
    recovering, recovering_transition = lifecycle.mark_recovering(
        order,
        occurred_at=_dt(0, 5),
        detail="unknown execution observed",
        reconciliation_state=ReconciliationState.UNKNOWN_EXECUTION,
    )
    resolved, resolved_transition = lifecycle.resolve_recovery(
        recovering,
        resolved_status=OrderStatus.FILLED,
        occurred_at=_dt(0, 6),
        detail="resolved by status lookup",
    )

    assert recovering.status is OrderStatus.RECOVERING
    assert recovering.reconciliation_state is ReconciliationState.UNKNOWN_EXECUTION
    assert recovering_transition.to_status is OrderStatus.RECOVERING
    assert resolved.status is OrderStatus.FILLED
    assert resolved.reconciliation_state is ReconciliationState.RECOVERED_TERMINAL_STATE
    assert resolved_transition.to_status is OrderStatus.FILLED


def _intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="intent-001",
        venue="binance",
        instrument_id="BTC-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.IOC,
        quantity=Decimal("1"),
        submitted_at=_dt(0, 0),
        source_strategy="breakout",
        rationale="lifecycle test",
    )


def _fill(order_id: str, *, quantity: str, price: str, occurred_at: datetime) -> FillEvent:
    return FillEvent(
        venue="binance",
        order_id=order_id,
        fill_id=f"fill:{order_id}:{quantity}",
        instrument_id="BTC-USDT",
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fee=Decimal("0"),
        fee_asset="USDT",
        occurred_at=occurred_at,
    )


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
