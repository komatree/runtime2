"""Paper-mode execution simulation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import ExecutionIntent
from app.contracts import FillEvent
from app.contracts import LiquidityRole
from app.contracts import OrderState

from .order_lifecycle import OrderLifecycleMachine


@dataclass(frozen=True)
class PaperExecutionSimulator:
    """Simulates immediate acceptance and fill for paper-mode intents.

    Non-goals:
    - partial fills
    - slippage models
    - venue-specific matching behavior
    """

    fee_bps: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    lifecycle: OrderLifecycleMachine = OrderLifecycleMachine()

    def simulate(
        self,
        *,
        intents: tuple[ExecutionIntent, ...],
        fill_price: Decimal,
        occurred_at,
    ) -> tuple[tuple[OrderState, ...], tuple[FillEvent, ...]]:
        """Return accepted-and-filled order states and synthetic fills."""

        order_states: list[OrderState] = []
        fill_events: list[FillEvent] = []
        for intent in intents:
            fee = (intent.quantity * fill_price * self.fee_bps) / Decimal("10000")
            new_state = self.lifecycle.new_from_intent(intent)
            acknowledged, _ = self.lifecycle.acknowledge(
                new_state,
                order_id=f"paper:{intent.intent_id}",
                occurred_at=occurred_at,
            )
            fill_events.append(
                FillEvent(
                    venue=intent.venue,
                    order_id=f"paper:{intent.intent_id}",
                    fill_id=f"fill:{intent.intent_id}",
                    instrument_id=intent.instrument_id,
                    side=intent.side,
                    quantity=intent.quantity,
                    price=fill_price,
                    fee=fee,
                    fee_asset=self.fee_asset,
                    occurred_at=occurred_at,
                    liquidity_role=LiquidityRole.UNKNOWN,
                )
            )
            filled_state, _ = self.lifecycle.apply_fill(
                acknowledged,
                fill_event=fill_events[-1],
            )
            order_states.append(filled_state)
        return tuple(order_states), tuple(fill_events)
