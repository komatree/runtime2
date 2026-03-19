"""Shared strategy interfaces.

Strategies operate on canonical `DecisionContext` values and emit canonical
`SignalDecision` outputs only. They do not fetch market data, call exchanges, or
perform persistence. The goal is pure decision logic with explicit inputs.
"""

from __future__ import annotations

from typing import Protocol

from app.contracts import DecisionContext
from app.contracts import SignalDecision

StrategyResult = tuple[SignalDecision, ...]


class Strategy(Protocol):
    """Protocol for pure strategy engines.

    Assumptions:
    - All market inputs are already normalized into `DecisionContext`.
    - Feature ownership sits upstream in the feature layer.

    Non-goals:
    - Data fetching
    - Exchange interaction
    - Order placement or persistence
    """

    name: str

    def evaluate(self, context: DecisionContext) -> StrategyResult:
        """Evaluate one decision context and return zero or more signals."""
