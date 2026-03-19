"""Mode-aware input quality and freshness policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.contracts import BarSlice
from app.contracts import DataQualityState
from app.contracts import DecisionContext

from .runtime_context import RunnerMode
from .runtime_context import RuntimeContext


@dataclass(frozen=True)
class DataQualityEvaluation:
    """Quality evaluation outcome for one runtime cycle."""

    states: tuple[DataQualityState, ...]
    details: tuple[str, ...]
    should_fail_closed: bool


@dataclass(frozen=True)
class RuntimeDataQualityGate:
    """Evaluates execution/context/snapshot freshness outside strategy logic."""

    max_context_lag: timedelta = timedelta(days=2)

    def evaluate(
        self,
        *,
        mode: RunnerMode,
        runtime_context: RuntimeContext,
        decision_context: DecisionContext,
        context_bar_slice: BarSlice | None = None,
    ) -> DataQualityEvaluation:
        """Return explicit degraded states and mode-specific fail/continue policy."""

        states: list[DataQualityState] = []
        details: list[str] = []

        if not decision_context.latest_candle.is_closed:
            states.append(DataQualityState.INCOMPLETE_BAR)
            details.append("execution candle is not closed")

        if context_bar_slice is not None:
            context_latest = context_bar_slice.candles[-1]
            if not context_latest.is_closed:
                states.append(DataQualityState.INCOMPLETE_BAR)
                details.append("context candle is not closed")
            elif decision_context.as_of - context_latest.close_time > self.max_context_lag:
                states.append(DataQualityState.STALE_DATA)
                details.append("context candle slice is older than allowed lag")

        if decision_context.index_snapshot_status == "missing":
            states.append(DataQualityState.MISSING_DATA)
            details.append("index suite snapshot missing")
        elif decision_context.index_snapshot_status == "stale":
            states.append(DataQualityState.STALE_DATA)
            details.append("index suite snapshot stale")
        elif decision_context.index_snapshot_status == "version_mismatch":
            states.append(DataQualityState.VERSION_MISMATCH)
            details.append("index suite snapshot version mismatch")

        if decision_context.stablecoin_snapshot_status == "missing":
            states.append(DataQualityState.MISSING_DATA)
            details.append("stablecoin snapshot missing")
        elif decision_context.stablecoin_snapshot_status == "stale":
            states.append(DataQualityState.STALE_DATA)
            details.append("stablecoin snapshot stale")

        if runtime_context.time_sync_ok is False:
            states.append(DataQualityState.TIME_SYNC_UNCERTAIN)
            details.append(runtime_context.time_sync_detail or "server time reference is uncertain")

        deduped_states = tuple(dict.fromkeys(states))
        should_fail_closed = self._should_fail_closed(mode=mode, states=deduped_states)
        return DataQualityEvaluation(
            states=deduped_states,
            details=tuple(details),
            should_fail_closed=should_fail_closed,
        )

    def _should_fail_closed(
        self,
        *,
        mode: RunnerMode,
        states: tuple[DataQualityState, ...],
    ) -> bool:
        if mode is not RunnerMode.RESTRICTED_LIVE:
            return DataQualityState.INCOMPLETE_BAR in states
        return bool(states)
