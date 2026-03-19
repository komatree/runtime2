"""Placeholder breakout strategy.

Assumptions:
- The feature layer already computed candle-derived fields such as breakout score
  or close returns.
- The strategy only inspects canonical context and emits venue-neutral signals.

Non-goals:
- Dynamic sizing logic beyond a placeholder target quantity
- Exchange-aware behavior
- Legacy runtime parity
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import DecisionContext
from app.contracts import SignalDecision
from app.contracts import SignalSide

from app.strategies.base import StrategyResult


@dataclass(frozen=True)
class BreakoutStrategy:
    """Minimal breakout placeholder for the first strategy vertical slice."""

    name: str = "breakout"
    breakout_threshold: Decimal = Decimal("0.02")
    min_confidence: Decimal = Decimal("0.60")
    placeholder_quantity: Decimal = Decimal("1")

    def evaluate(self, context: DecisionContext) -> StrategyResult:
        """Emit a single breakout signal only when placeholder trigger is met."""

        close_return = context.features.feature_values.get("candle.close_return_1", Decimal("0"))
        breakout_score = context.features.feature_values.get("breakout.score", Decimal("0"))
        if close_return < self.breakout_threshold and breakout_score < self.min_confidence:
            return ()

        confidence = max(close_return, breakout_score)
        return (
            SignalDecision(
                strategy_name=self.name,
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=SignalSide.BUY,
                confidence=min(confidence, Decimal("1")),
                rationale="placeholder breakout trigger met",
                target_quantity=self.placeholder_quantity,
            ),
        )
