"""Runtime observability builders and persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import RuntimeCycleResult

from .models import RuntimeCycleSummary
from .models import RuntimeDegradationFlag
from .models import RuntimeHealthSnapshot
from .models import ExchangeHealthSnapshot


def _status_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class RuntimeObservabilityService:
    """Builds cycle summaries and health snapshots from canonical runtime state."""

    mode: str

    def build_cycle_summary(
        self,
        *,
        cycle_result: RuntimeCycleResult,
        features: FeatureSnapshot,
        context: DecisionContext,
        persisted_at: datetime,
        exchange_health: ExchangeHealthSnapshot | None = None,
    ) -> RuntimeCycleSummary:
        """Return a compact per-cycle summary for operators and debugging."""

        degradation_flags: list[RuntimeDegradationFlag] = []
        if context.index_snapshot is None:
            degradation_flags.append(RuntimeDegradationFlag.INDEX_SUITE_MISSING)
        if context.stablecoin_snapshot is None:
            degradation_flags.append(RuntimeDegradationFlag.STABLECOIN_MISSING)
        if not features.is_complete or not cycle_result.success:
            degradation_flags.append(RuntimeDegradationFlag.EXCHANGE_DATA_DEGRADED)

        return RuntimeCycleSummary(
            cycle_id=cycle_result.cycle_id,
            mode=self.mode,
            instrument_id=context.instrument.instrument_id,
            timeframe=context.features.timeframe,
            cycle_completed_at=cycle_result.completed_at,
            bar_close_time=context.latest_candle.close_time,
            feature_snapshot_time=features.as_of,
            signal_count=len(cycle_result.signals),
            risk_decision_count=len(cycle_result.risk_decisions),
            execution_intent_count=len(cycle_result.execution_intents),
            persistence_succeeded_at=persisted_at,
            degradation_flags=tuple(degradation_flags),
            exchange_health_state=exchange_health.overall_state if exchange_health is not None else None,
            alerts=cycle_result.alerts,
        )

    def build_health_snapshot(
        self,
        *,
        summary: RuntimeCycleSummary,
        exchange_health: ExchangeHealthSnapshot | None = None,
    ) -> RuntimeHealthSnapshot:
        """Return an operator-friendly latest health snapshot."""

        return RuntimeHealthSnapshot(
            generated_at=summary.persistence_succeeded_at,
            mode=summary.mode,
            last_closed_bar_processed_at=summary.bar_close_time,
            last_successful_feature_snapshot_at=summary.feature_snapshot_time,
            last_strategy_evaluation_at=summary.cycle_completed_at,
            last_persistence_success_at=summary.persistence_succeeded_at,
            degradation_flags=summary.degradation_flags,
            latest_cycle_id=summary.cycle_id,
            latest_instrument_id=summary.instrument_id,
            exchange_health=exchange_health,
            latest_alerts=summary.alerts,
        )

    def render_operator_report(self, *, summary: RuntimeCycleSummary, health: RuntimeHealthSnapshot) -> str:
        """Render a short markdown report for operators."""

        flags = ", ".join(flag.value for flag in health.degradation_flags) or "none"
        alerts = ", ".join(health.latest_alerts) or "none"
        lines = [
            "# Runtime Status",
            f"- mode: {health.mode}",
            f"- latest_cycle_id: {health.latest_cycle_id}",
            f"- latest_instrument_id: {health.latest_instrument_id}",
            f"- last_closed_bar_processed_at: {health.last_closed_bar_processed_at.isoformat() if health.last_closed_bar_processed_at else 'none'}",
            f"- last_successful_feature_snapshot_at: {health.last_successful_feature_snapshot_at.isoformat() if health.last_successful_feature_snapshot_at else 'none'}",
            f"- last_strategy_evaluation_at: {health.last_strategy_evaluation_at.isoformat() if health.last_strategy_evaluation_at else 'none'}",
            f"- last_persistence_success_at: {health.last_persistence_success_at.isoformat() if health.last_persistence_success_at else 'none'}",
            f"- degradation_flags: {flags}",
            f"- alerts: {alerts}",
            f"- signal_count: {summary.signal_count}",
            f"- risk_decision_count: {summary.risk_decision_count}",
            f"- execution_intent_count: {summary.execution_intent_count}",
        ]
        if health.exchange_health is not None:
            exchange_alerts = ", ".join(health.exchange_health.alerts) or "none"
            lines.extend(
                [
                    "## Exchange Health",
                    f"- overall_state: {health.exchange_health.overall_state.value}",
                    f"- private_stream: {health.exchange_health.private_stream.state.value} ({health.exchange_health.private_stream.detail})",
                    f"- reconciliation: {health.exchange_health.reconciliation.state.value} ({health.exchange_health.reconciliation.detail})",
                    f"- clock_sync: {health.exchange_health.clock_sync.state.value} ({health.exchange_health.clock_sync.detail})",
                    f"- status_query: {health.exchange_health.status_query.state.value} ({health.exchange_health.status_query.detail})",
                    f"- exchange_alerts: {exchange_alerts}",
                ]
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class FileRuntimeStatusGateway:
    """Persists cycle summaries, latest health, and operator markdown reports."""

    summary_output_path: Path
    health_output_path: Path
    operator_report_path: Path

    def persist(self, *, summary: RuntimeCycleSummary, health: RuntimeHealthSnapshot, operator_report: str) -> None:
        """Write append-only summaries and latest-status artifacts."""

        self.summary_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.health_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.operator_report_path.parent.mkdir(parents=True, exist_ok=True)

        with self.summary_output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(summary), default=_status_json_default, sort_keys=True))
            handle.write("\n")
        self.health_output_path.write_text(
            json.dumps(asdict(health), default=_status_json_default, sort_keys=True),
            encoding="utf-8",
        )
        self.operator_report_path.write_text(operator_report, encoding="utf-8")
