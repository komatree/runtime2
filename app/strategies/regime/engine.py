"""Placeholder regime strategy.

Assumptions:
- Regime context is derived upstream from feature snapshots and optional index or
  stablecoin context.
- The strategy returns contextual state only and does not express direct trade
  intent in phase 1.

Non-goals:
- Market timing or directional trade generation
- Data acquisition or external service calls
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import DecisionContext
from app.contracts import SignalDecision
from app.contracts import SignalSide

from app.strategies.base import StrategyResult


@dataclass(frozen=True)
class RegimeStrategy:
    """Context-only regime classifier placeholder."""

    name: str = "regime"

    def evaluate(self, context: DecisionContext) -> StrategyResult:
        """Emit one flat contextual signal carrying regime state in rationale."""

        index_value = context.features.feature_values.get("index_suite.value")
        stablecoin_depegged = context.features.feature_values.get("stablecoin.is_depegged", Decimal("0"))

        if stablecoin_depegged == Decimal("1"):
            regime_state = "risk_off_stablecoin_stress"
        elif index_value is not None and index_value >= Decimal("50"):
            regime_state = "risk_on"
        elif index_value is not None:
            regime_state = "risk_off"
        else:
            regime_state = "neutral_unknown"

        return (
            SignalDecision(
                strategy_name=self.name,
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=SignalSide.FLAT,
                confidence=Decimal("1"),
                rationale=f"regime_state={regime_state}",
            ),
        )
