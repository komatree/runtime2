from __future__ import annotations

import json
from pathlib import Path

from app.monitoring.reconciliation_disruption import build_default_reconciliation_disruption_scenarios
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionArtifactWriter
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionReportingService
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionRunner


def test_reconciliation_disruption_campaign_persists_all_default_scenarios(tmp_path: Path) -> None:
    runner = ReconciliationDisruptionRunner(output_root=tmp_path / "reconciliation_disruption")
    reporting = ReconciliationDisruptionReportingService()

    scenario_ids = []
    for scenario in build_default_reconciliation_disruption_scenarios():
        run = runner.run_scenario(scenario=scenario)
        scenario_ids.append(scenario.scenario_id)
        paths = ReconciliationDisruptionArtifactWriter(
            output_dir=tmp_path / "reconciliation_disruption" / scenario.scenario_id,
        ).persist(
            run=run,
            markdown=reporting.render_markdown(run=run),
        )

        assert run.summary.scenario_passed is True
        assert paths.summary_json_path.exists()
        assert paths.summary_markdown_path.exists()
        assert paths.workflow_records_path.exists()
        assert paths.workflow_log_path.exists()
        assert paths.reconciliation_state_path.exists()

    assert tuple(scenario_ids) == (
        "private_event_loss",
        "delayed_status_query",
        "duplicated_execution_reports",
        "partial_fill_reorder",
    )


def test_private_event_loss_converges_and_persists_recovery_attempts(tmp_path: Path) -> None:
    scenario = next(
        candidate
        for candidate in build_default_reconciliation_disruption_scenarios()
        if candidate.scenario_id == "private_event_loss"
    )
    runner = ReconciliationDisruptionRunner(output_root=tmp_path / "reconciliation_disruption")
    run = runner.run_scenario(scenario=scenario)
    paths = ReconciliationDisruptionArtifactWriter(
        output_dir=tmp_path / "reconciliation_disruption" / scenario.scenario_id,
    ).persist(
        run=run,
        markdown=ReconciliationDisruptionReportingService().render_markdown(run=run),
    )

    summary = json.loads(paths.summary_json_path.read_text(encoding="utf-8"))
    workflow_rows = [
        json.loads(line)
        for line in paths.workflow_records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    workflow_log_rows = [
        json.loads(line)
        for line in paths.workflow_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert summary["scenario_passed"] is True
    assert summary["trigger_reasons"] == ["private_stream_gap"]
    assert summary["final_convergence_state"] == "converged_terminal"
    assert summary["persisted_attempt_count"] == 1
    assert workflow_rows[0]["recovery_attempt_count"] == 1
    assert workflow_rows[0]["status_query_states"] == ["success"]
    assert workflow_log_rows[0]["recovery_attempt_count"] == 1


def test_delayed_status_query_resumes_and_converges_deterministically(tmp_path: Path) -> None:
    scenario = next(
        candidate
        for candidate in build_default_reconciliation_disruption_scenarios()
        if candidate.scenario_id == "delayed_status_query"
    )
    runner = ReconciliationDisruptionRunner(output_root=tmp_path / "reconciliation_disruption")
    run = runner.run_scenario(scenario=scenario)
    paths = ReconciliationDisruptionArtifactWriter(
        output_dir=tmp_path / "reconciliation_disruption" / scenario.scenario_id,
    ).persist(
        run=run,
        markdown=ReconciliationDisruptionReportingService().render_markdown(run=run),
    )

    state_payload = json.loads(paths.reconciliation_state_path.read_text(encoding="utf-8"))
    workflow_rows = [
        json.loads(line)
        for line in paths.workflow_records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert run.summary.scenario_passed is True
    assert run.summary.total_recovery_attempts == 4
    assert workflow_rows[0]["convergence_state"] == "pending"
    assert workflow_rows[1]["convergence_state"] == "converged_terminal"
    assert state_payload["last_convergence_state"] == "converged_terminal"
    assert state_payload["unresolved_order_ids"] == []


def test_duplicate_and_reordered_private_events_remain_deterministic_without_escalation(
    tmp_path: Path,
) -> None:
    runner = ReconciliationDisruptionRunner(output_root=tmp_path / "reconciliation_disruption")
    duplicate = next(
        candidate
        for candidate in build_default_reconciliation_disruption_scenarios()
        if candidate.scenario_id == "duplicated_execution_reports"
    )
    reorder = next(
        candidate
        for candidate in build_default_reconciliation_disruption_scenarios()
        if candidate.scenario_id == "partial_fill_reorder"
    )

    duplicate_run = runner.run_scenario(scenario=duplicate)
    reorder_run = runner.run_scenario(scenario=reorder)

    assert duplicate_run.summary.scenario_passed is True
    assert duplicate_run.summary.total_recovery_attempts == 0
    assert duplicate_run.summary.manual_attention_observed is False
    assert reorder_run.summary.scenario_passed is True
    assert reorder_run.summary.total_recovery_attempts == 0
    assert reorder_run.summary.manual_attention_observed is False
