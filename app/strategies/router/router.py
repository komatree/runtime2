"""Strategy router for coordinating pure strategy outputs.

Assumptions:
- Routing happens after features are assembled and before risk evaluation.
- The router remains exchange-agnostic and only coordinates canonical signals.

Non-goals:
- Execution planning
- Venue-specific prioritization
- Stateful portfolio mutation
"""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts import DecisionContext
from app.contracts import SignalDecision

from app.strategies.base import Strategy
from app.strategies.base import StrategyResult


@dataclass(frozen=True)
class StrategyRouter:
    """Combines outputs from multiple strategies without exchange knowledge."""

    strategies: tuple[Strategy, ...]
    include_flat_signals: bool = True

    def evaluate(self, context: DecisionContext) -> StrategyResult:
        """Evaluate configured strategies and return ordered canonical signals."""

        collected: list[SignalDecision] = []
        for strategy in self.strategies:
            collected.extend(strategy.evaluate(context))

        if not self.include_flat_signals:
            collected = [signal for signal in collected if signal.side.value != "flat"]

        return tuple(
            sorted(
                collected,
                key=lambda signal: (
                    signal.as_of,
                    signal.strategy_name,
                    signal.instrument_id,
                ),
            )
        )
