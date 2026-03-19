"""Execution-intent builder for report-only mode."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import ExecutionIntent
from app.contracts import OrderSide
from app.contracts import OrderType
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalSide
from app.contracts import TimeInForce


@dataclass(frozen=True)
class ReportOnlyExecutionIntentBuilder:
    """Builds auditable execution intents without any exchange submission."""

    default_venue: str = "binance"

    def build(
        self,
        *,
        risk_decisions: tuple[RiskDecision, ...],
        venue: str,
        submitted_at,
    ) -> tuple[ExecutionIntent, ...]:
        """Build non-submitted intents from allowed or adjusted trade decisions."""

        intents: list[ExecutionIntent] = []
        for decision in risk_decisions:
            if decision.status not in {RiskDecisionStatus.ALLOW, RiskDecisionStatus.ADJUST}:
                continue
            if decision.signal.side is SignalSide.FLAT:
                continue
            quantity = decision.approved_quantity
            if quantity is None:
                quantity = decision.approved_notional or decision.signal.target_notional or Decimal("1")
            intents.append(
                ExecutionIntent(
                    intent_id=f"{decision.signal.strategy_name}:{decision.signal.instrument_id}:{submitted_at.isoformat()}",
                    venue=venue or self.default_venue,
                    instrument_id=decision.signal.instrument_id,
                    side=OrderSide.BUY if decision.signal.side is SignalSide.BUY else OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    time_in_force=TimeInForce.IOC,
                    quantity=quantity,
                    submitted_at=submitted_at,
                    source_strategy=decision.signal.strategy_name,
                    rationale="report-only generated intent; not submitted",
                )
            )
        return tuple(intents)
