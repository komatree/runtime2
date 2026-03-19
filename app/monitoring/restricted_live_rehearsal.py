"""Restricted-live rehearsal scenario summaries and artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.contracts import RuntimeCycleResult
from app.portfolio import LivePortfolioMutationOutcome


def _artifact_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class RestrictedLiveScenarioSummary:
    """Operator-facing summary for one restricted-live rehearsal scenario."""

    scenario_name: str
    expected_mutation_applied: bool
    cycle_id: str
    cycle_success: bool
    mutation_attempted: bool
    mutation_applied: bool
    scenario_passed: bool
    blocked_reasons: tuple[str, ...]
    reconciliation_states: tuple[str, ...]
    restart_count: int
    interruption_reason: str | None
    restored_unresolved_order_ids: tuple[str, ...]
    restored_gap_active: bool
    execution_intent_count: int
    alert_count: int
    recorded_at: datetime


@dataclass(frozen=True)
class RestrictedLiveScenarioReportingService:
    """Builds explainable scenario summaries for restricted-live rehearsal verification."""

    def build_summary(
        self,
        *,
        scenario_name: str,
        expected_mutation_applied: bool,
        cycle_result: RuntimeCycleResult,
        mutation_outcome: LivePortfolioMutationOutcome,
        recorded_at: datetime,
        restart_count: int = 0,
        interruption_reason: str | None = None,
        restored_unresolved_order_ids: tuple[str, ...] = (),
        restored_gap_active: bool = False,
    ) -> RestrictedLiveScenarioSummary:
        blocked_reasons = tuple(
            alert
            for alert in mutation_outcome.alerts
            if "blocked" in alert or "mismatch" in alert or "malformed" in alert
        )
        return RestrictedLiveScenarioSummary(
            scenario_name=scenario_name,
            expected_mutation_applied=expected_mutation_applied,
            cycle_id=cycle_result.cycle_id,
            cycle_success=cycle_result.success,
            mutation_attempted=mutation_outcome.mutation_attempted,
            mutation_applied=mutation_outcome.mutation_applied,
            scenario_passed=mutation_outcome.mutation_applied is expected_mutation_applied,
            blocked_reasons=blocked_reasons,
            reconciliation_states=tuple(
                event.reconciliation_state.value for event in cycle_result.reconciliation_events
            ),
            restart_count=restart_count,
            interruption_reason=interruption_reason,
            restored_unresolved_order_ids=restored_unresolved_order_ids,
            restored_gap_active=restored_gap_active,
            execution_intent_count=len(cycle_result.execution_intents),
            alert_count=len(cycle_result.alerts),
            recorded_at=recorded_at,
        )

    def render_markdown(self, *, summary: RestrictedLiveScenarioSummary) -> str:
        """Render a short operator-facing markdown summary."""

        blocked = ", ".join(summary.blocked_reasons) or "none"
        states = ", ".join(summary.reconciliation_states) or "none"
        restored = ", ".join(summary.restored_unresolved_order_ids) or "none"
        return "\n".join(
            [
                "# Restricted-Live Rehearsal Scenario",
                f"- scenario_name: {summary.scenario_name}",
                f"- cycle_id: {summary.cycle_id}",
                f"- expected_mutation_applied: {str(summary.expected_mutation_applied).lower()}",
                f"- mutation_applied: {str(summary.mutation_applied).lower()}",
                f"- cycle_success: {str(summary.cycle_success).lower()}",
                f"- scenario_passed: {str(summary.scenario_passed).lower()}",
                f"- restart_count: {summary.restart_count}",
                f"- interruption_reason: {summary.interruption_reason or 'none'}",
                f"- restored_unresolved_order_ids: {restored}",
                f"- restored_gap_active: {str(summary.restored_gap_active).lower()}",
                f"- reconciliation_states: {states}",
                f"- blocked_reasons: {blocked}",
                f"- execution_intent_count: {summary.execution_intent_count}",
                f"- alert_count: {summary.alert_count}",
            ]
        )


@dataclass(frozen=True)
class RestrictedLiveScenarioArtifactWriter:
    """Persists machine-readable and markdown scenario artifacts."""

    output_dir: Path

    def persist(self, *, summary: RestrictedLiveScenarioSummary, markdown: str) -> tuple[Path, Path]:
        """Write scenario summary artifacts into the configured output directory."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / "scenario_summary.json"
        markdown_path = self.output_dir / "scenario_summary.md"
        json_path.write_text(json.dumps(asdict(summary), default=_artifact_json_default, sort_keys=True), encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")
        return json_path, markdown_path
