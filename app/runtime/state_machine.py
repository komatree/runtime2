"""Explicit runtime stage tracking for one cycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuntimeStage(str, Enum):
    """Ordered stages for a single runtime decision cycle."""

    BAR_CLOSE_TRIGGER = "bar_close_trigger"
    NORMALIZED_SLICE = "normalized_slice"
    FEATURE_SNAPSHOT = "feature_snapshot"
    STRATEGY_EVALUATION = "strategy_evaluation"
    RISK_EVALUATION = "risk_evaluation"
    EXECUTION_INTENT = "execution_intent"
    PERSISTENCE_REPORTING = "persistence_reporting"
    EXCHANGE_RECONCILIATION = "exchange_reconciliation"


@dataclass
class RuntimeStateMachine:
    """Tracks stage progression and failure points for a runtime cycle."""

    current_stage: RuntimeStage = RuntimeStage.BAR_CLOSE_TRIGGER
    completed_stages: tuple[RuntimeStage, ...] = ()
    failure_stage: RuntimeStage | None = None

    def advance(self, stage: RuntimeStage) -> None:
        """Advance to the supplied stage and mark it as completed."""

        self.current_stage = stage
        self.completed_stages = (*self.completed_stages, stage)

    def fail(self, stage: RuntimeStage) -> None:
        """Record the stage at which the cycle failed."""

        self.current_stage = stage
        self.failure_stage = stage
