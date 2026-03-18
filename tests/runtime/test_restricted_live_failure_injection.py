from __future__ import annotations

import json
from pathlib import Path

from app.monitoring.restricted_live_failure_injection import build_default_failure_injection_scenarios
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionArtifactWriter
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionReportingService
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionRunner


def test_failure_injection_campaign_persists_all_default_scenarios(tmp_path: Path) -> None:
    runner = RestrictedLiveFailureInjectionRunner(output_root=tmp_path / "failure_injection")
    reporting = RestrictedLiveFailureInjectionReportingService()
    scenarios = build_default_failure_injection_scenarios()

    scenario_ids = []
    scenario_results = {}
    for scenario in scenarios:
        run = runner.run_scenario(scenario=scenario)
        scenario_ids.append(scenario.scenario_id)
        scenario_results[scenario.scenario_id] = run.summary.scenario_passed
        artifact_paths = RestrictedLiveFailureInjectionArtifactWriter(
            output_dir=tmp_path / "failure_injection" / scenario.scenario_id,
        ).persist(
            run=run,
            markdown=reporting.render_markdown(run=run),
        )

        assert artifact_paths.summary_json_path.exists()
        assert artifact_paths.summary_markdown_path.exists()
        assert artifact_paths.cycle_records_path.exists()

    assert tuple(scenario_ids) == (
        "private_stream_disconnect",
        "listen_key_expiration",
        "websocket_reconnect_storms",
        "delayed_private_events",
        "missing_order_events",
        "duplicated_fill_events",
    )
    assert scenario_results["private_stream_disconnect"] is True
    assert scenario_results["listen_key_expiration"] is True
    assert scenario_results["websocket_reconnect_storms"] is True
    assert scenario_results["delayed_private_events"] is True
    assert scenario_results["missing_order_events"] is True
    assert scenario_results["duplicated_fill_events"] is True


def test_failure_injection_missing_order_events_escalates_with_operator_visible_artifacts(
    tmp_path: Path,
) -> None:
    scenario = next(
        candidate
        for candidate in build_default_failure_injection_scenarios()
        if candidate.scenario_id == "missing_order_events"
    )
    runner = RestrictedLiveFailureInjectionRunner(output_root=tmp_path / "failure_injection")
    run = runner.run_scenario(scenario=scenario)
    artifact_paths = RestrictedLiveFailureInjectionArtifactWriter(
        output_dir=tmp_path / "failure_injection" / scenario.scenario_id,
    ).persist(
        run=run,
        markdown=RestrictedLiveFailureInjectionReportingService().render_markdown(run=run),
    )

    payload = json.loads(artifact_paths.summary_json_path.read_text(encoding="utf-8"))
    cycle_rows = [
        json.loads(line)
        for line in artifact_paths.cycle_records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert payload["scenario_passed"] is True
    assert payload["manual_attention_observed"] is True
    assert payload["blocked_mutation_count"] == 1
    assert "missing_private_updates" in payload["recovery_trigger_reasons"]
    assert cycle_rows[0]["exchange_health_state"] == "fatal"
    assert cycle_rows[0]["convergence_state"] == "unreconciled_manual_attention"


def test_failure_injection_duplicate_fill_safely_ignores_duplicate_ids(tmp_path: Path) -> None:
    scenario = next(
        candidate
        for candidate in build_default_failure_injection_scenarios()
        if candidate.scenario_id == "duplicated_fill_events"
    )
    runner = RestrictedLiveFailureInjectionRunner(output_root=tmp_path / "failure_injection")
    run = runner.run_scenario(scenario=scenario)

    assert run.summary.scenario_passed is True
    assert run.summary.applied_mutation_count == 1
    assert run.summary.ignored_duplicate_fill_count == 1
    assert run.summary.final_exchange_health_state == "healthy"
    assert run.cycle_records[0].ignored_fill_ids == ("9501:19501",)


def test_failure_injection_listen_key_expiration_blocks_until_later_private_confirmation(
    tmp_path: Path,
) -> None:
    scenario = next(
        candidate
        for candidate in build_default_failure_injection_scenarios()
        if candidate.scenario_id == "listen_key_expiration"
    )
    runner = RestrictedLiveFailureInjectionRunner(output_root=tmp_path / "failure_injection")
    run = runner.run_scenario(scenario=scenario)

    assert run.summary.scenario_passed is True
    assert run.summary.recovery_trigger_reasons == ("missing_private_updates",)
    assert run.cycle_records[0].mutation_applied is False
    assert run.cycle_records[1].mutation_applied is True
    assert run.cycle_records[0].exchange_health_state == "fatal"
    assert any(
        "until canonical private confirmation for order: 9201" in reason
        for reason in run.cycle_records[0].blocked_reasons
    )
