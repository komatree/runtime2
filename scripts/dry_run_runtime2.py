#!/usr/bin/env python3
"""Automated dry-run rehearsal workflow for runtime2."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import RehearsalLaunchConfig
from app.config import RuntimeLaunchSummary
from app.config import RuntimeRehearsalSettings
from app.config import RuntimeRunSummary
from app.config import append_launch_summary
from app.config import append_run_summary
from app.config import build_run_summary
from app.config import load_rehearsal_launch_config
from app.config import validate_runtime_rehearsal
from app.config import write_latest_launch_summary_markdown
from app.config import write_latest_run_summary_markdown
from app.runtime import RunnerMode
from scripts.runtime2_rehearsal import LAUNCHER_FAILURE_EXIT_CODE
from scripts.runtime2_rehearsal import launch_runtime_rehearsal


EXIT_SUCCESS = 0
EXIT_PREFLIGHT_FAILED = 1
EXIT_SESSION_FAILED = LAUNCHER_FAILURE_EXIT_CODE


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(frozen=True)
class DryRunSessionArtifacts:
    """Run-specific artifact paths for one dry-run session."""

    run_dir: Path
    logs_dir: Path
    input_manifest_path: Path
    run_summary_json_path: Path
    run_summary_markdown_path: Path
    rehearsal_summary_jsonl_path: Path
    rehearsal_summary_markdown_path: Path
    launch_summary_json_path: Path
    launch_summary_markdown_path: Path
    runtime_cycles_path: Path
    runtime_cycle_summaries_path: Path
    runtime_health_path: Path
    runtime_status_path: Path
    paper_transition_path: Path
    paper_session_summary_path: Path


@dataclass(frozen=True)
class DryRunSessionResult:
    """Structured dry-run result for operators and automation."""

    ok: bool
    exit_code: int
    mode: str
    run_id: str
    run_dir: Path
    logs_dir: Path
    preflight_ok: bool
    launch_ok: bool
    failure_reason: str | None
    alerts: tuple[str, ...]
    preflight_summary: dict[str, Any]
    launch_summary: dict[str, Any] | None
    artifact_paths: dict[str, str]


def build_parser() -> argparse.ArgumentParser:
    """Build the dry-run CLI parser."""

    parser = argparse.ArgumentParser(description="runtime2 dry-run rehearsal workflow")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in RunnerMode),
        required=True,
    )
    parser.add_argument("--venue", default="binance")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execution-data", required=True, type=Path)
    parser.add_argument("--context-data", required=True, type=Path)
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument("--logs-dir", required=True, type=Path)
    parser.add_argument("--exchange-mode", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--confirm-rehearsal-only",
        action="store_true",
        help="Required safety confirmation for all dry-run launches.",
    )
    parser.add_argument(
        "--allow-restricted-live-rehearsal",
        action="store_true",
        help="Required only when --mode restricted_live is selected.",
    )
    parser.add_argument(
        "--confirm-no-order-submission",
        action="store_true",
        help="Required only when --mode restricted_live is selected.",
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> RuntimeRehearsalSettings:
    """Convert parsed dry-run arguments into rehearsal settings."""

    return RuntimeRehearsalSettings(
        mode=RunnerMode(args.mode),
        venue=args.venue,
        config_path=args.config,
        execution_data_path=args.execution_data,
        context_data_path=args.context_data,
        reports_dir=args.reports_dir,
        logs_dir=args.logs_dir,
        exchange_mode=args.exchange_mode,
        command_name="dry-run",
        confirm_rehearsal_only=args.confirm_rehearsal_only,
        allow_restricted_live_rehearsal=args.allow_restricted_live_rehearsal,
        confirm_no_order_submission=args.confirm_no_order_submission,
    )


def _build_artifacts(*, settings: RuntimeRehearsalSettings, run_id: str) -> DryRunSessionArtifacts:
    run_dir = settings.reports_dir / "dry_runs" / run_id
    logs_dir = settings.logs_dir / "dry_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return DryRunSessionArtifacts(
        run_dir=run_dir,
        logs_dir=logs_dir,
        input_manifest_path=run_dir / "input_manifest.json",
        run_summary_json_path=run_dir / "run_summary.json",
        run_summary_markdown_path=run_dir / "run_summary.md",
        rehearsal_summary_jsonl_path=run_dir / "rehearsal_run_summaries.jsonl",
        rehearsal_summary_markdown_path=run_dir / "latest_rehearsal_summary.md",
        launch_summary_json_path=run_dir / "latest_launch_summary.json",
        launch_summary_markdown_path=run_dir / "latest_launch_summary.md",
        runtime_cycles_path=run_dir / "runtime_cycles.jsonl",
        runtime_cycle_summaries_path=run_dir / "runtime_cycle_summaries.jsonl",
        runtime_health_path=run_dir / "runtime_health.json",
        runtime_status_path=run_dir / "runtime_status.md",
        paper_transition_path=run_dir / "paper_state_transitions.jsonl",
        paper_session_summary_path=run_dir / "paper_session_summaries.jsonl",
    )


def _build_run_settings(
    settings: RuntimeRehearsalSettings,
    artifacts: DryRunSessionArtifacts,
) -> RuntimeRehearsalSettings:
    return replace(
        settings,
        reports_dir=artifacts.run_dir,
        logs_dir=artifacts.logs_dir,
    )


def _write_input_manifest(
    *,
    settings: RuntimeRehearsalSettings,
    run_settings: RuntimeRehearsalSettings,
    artifacts: DryRunSessionArtifacts,
    launch_config: RehearsalLaunchConfig | None,
) -> None:
    payload = {
        "schema_version": "dry_run_input_manifest.v2",
        "requested_mode": settings.mode.value,
        "command_name": settings.command_name,
        "config_path": str(settings.config_path),
        "execution_data_path": str(settings.execution_data_path),
        "context_data_path": str(settings.context_data_path),
        "base_reports_dir": str(settings.reports_dir),
        "base_logs_dir": str(settings.logs_dir),
        "run_reports_dir": str(run_settings.reports_dir),
        "run_logs_dir": str(run_settings.logs_dir),
        "exchange_mode": settings.exchange_mode,
        "launch_config": asdict(launch_config) if launch_config is not None else None,
    }
    artifacts.input_manifest_path.write_text(
        json.dumps(payload, default=_json_default, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _render_markdown_summary(result: DryRunSessionResult) -> str:
    launch_summary = result.launch_summary or {}
    return "\n".join(
        [
            "# Dry-Run Session Summary",
            f"- run_id: {result.run_id}",
            f"- mode: {result.mode}",
            f"- status: {'success' if result.ok else 'failed'}",
            f"- exit_code: {result.exit_code}",
            f"- preflight_ok: {result.preflight_ok}",
            f"- launch_ok: {result.launch_ok}",
            f"- failure_reason: {result.failure_reason or 'none'}",
            f"- alerts: {', '.join(result.alerts) or 'none'}",
            f"- run_dir: {result.run_dir}",
            f"- logs_dir: {result.logs_dir}",
            "",
            "## Launch Summary",
            f"- runner_name: {launch_summary.get('runner_name', 'none')}",
            f"- cycle_id: {launch_summary.get('cycle_id', 'none')}",
            f"- instrument_id: {launch_summary.get('instrument_id', 'none')}",
            f"- signal_count: {launch_summary.get('signal_count', 'none')}",
            f"- risk_decision_count: {launch_summary.get('risk_decision_count', 'none')}",
            f"- execution_intent_count: {launch_summary.get('execution_intent_count', 'none')}",
            f"- output_path: {launch_summary.get('output_path', 'none')}",
        ]
    )


def _write_session_result(result: DryRunSessionResult, artifacts: DryRunSessionArtifacts) -> None:
    payload = asdict(result)
    payload["run_dir"] = str(result.run_dir)
    payload["logs_dir"] = str(result.logs_dir)
    artifacts.run_summary_json_path.write_text(
        json.dumps(payload, default=_json_default, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    artifacts.run_summary_markdown_path.write_text(
        _render_markdown_summary(result),
        encoding="utf-8",
    )


def _artifact_paths(artifacts: DryRunSessionArtifacts) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in asdict(artifacts).items()
    }


def _result_from_failure(
    *,
    settings: RuntimeRehearsalSettings,
    run_id: str,
    artifacts: DryRunSessionArtifacts,
    summary: RuntimeRunSummary,
    exit_code: int,
    failure_reason: str,
    alerts: tuple[str, ...],
) -> DryRunSessionResult:
    return DryRunSessionResult(
        ok=False,
        exit_code=exit_code,
        mode=settings.mode.value,
        run_id=run_id,
        run_dir=artifacts.run_dir,
        logs_dir=artifacts.logs_dir,
        preflight_ok=summary.preflight_ok,
        launch_ok=False,
        failure_reason=failure_reason,
        alerts=alerts,
        preflight_summary=asdict(summary),
        launch_summary=None,
        artifact_paths=_artifact_paths(artifacts),
    )


def run_dry_run_session(settings: RuntimeRehearsalSettings, *, run_id: str | None = None) -> DryRunSessionResult:
    """Run one dry-run session via the authoritative launcher path."""

    resolved_run_id = run_id or f"{settings.mode.value}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    artifacts = _build_artifacts(settings=settings, run_id=resolved_run_id)
    run_settings = _build_run_settings(settings, artifacts)

    launch_config: RehearsalLaunchConfig | None = None
    if run_settings.config_path.is_file():
        try:
            launch_config = load_rehearsal_launch_config(run_settings.config_path)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            launch_config = None
    _write_input_manifest(
        settings=settings,
        run_settings=run_settings,
        artifacts=artifacts,
        launch_config=launch_config,
    )

    preflight = validate_runtime_rehearsal(run_settings)
    run_summary = build_run_summary(run_settings, preflight=preflight)
    append_run_summary(run_summary, output_dir=run_settings.reports_dir)
    write_latest_run_summary_markdown(run_summary, output_dir=run_settings.reports_dir)

    if not preflight.ok:
        result = _result_from_failure(
            settings=run_settings,
            run_id=resolved_run_id,
            artifacts=artifacts,
            summary=run_summary,
            exit_code=EXIT_PREFLIGHT_FAILED,
            failure_reason="preflight_failed",
            alerts=preflight.errors,
        )
        _write_session_result(result, artifacts)
        return result

    try:
        launch_summary = launch_runtime_rehearsal(run_settings)
        append_launch_summary(launch_summary, output_dir=run_settings.reports_dir)
        write_latest_launch_summary_markdown(launch_summary, output_dir=run_settings.reports_dir)
    except Exception as exc:
        result = _result_from_failure(
            settings=run_settings,
            run_id=resolved_run_id,
            artifacts=artifacts,
            summary=run_summary,
            exit_code=EXIT_SESSION_FAILED,
            failure_reason=f"launch_exception:{exc}",
            alerts=(str(exc),),
        )
        _write_session_result(result, artifacts)
        return result

    result = DryRunSessionResult(
        ok=launch_summary.success,
        exit_code=EXIT_SUCCESS if launch_summary.success else EXIT_SESSION_FAILED,
        mode=run_settings.mode.value,
        run_id=resolved_run_id,
        run_dir=artifacts.run_dir,
        logs_dir=artifacts.logs_dir,
        preflight_ok=True,
        launch_ok=launch_summary.success,
        failure_reason=None if launch_summary.success else "launch_unsuccessful",
        alerts=launch_summary.alerts,
        preflight_summary=asdict(run_summary),
        launch_summary=asdict(launch_summary),
        artifact_paths=_artifact_paths(artifacts),
    )
    _write_session_result(result, artifacts)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_dry_run_session(settings_from_args(args), run_id=args.run_id)
    print(f"run_id: {result.run_id}")
    print(f"status: {'success' if result.ok else 'failed'}")
    print(f"run_dir: {result.run_dir}")
    print(f"logs_dir: {result.logs_dir}")
    print(f"preflight_ok: {result.preflight_ok}")
    print(f"launch_ok: {result.launch_ok}")
    if result.launch_summary is not None:
        print(f"runner_name: {result.launch_summary['runner_name']}")
        print(f"cycle_id: {result.launch_summary['cycle_id']}")
        print(f"launch_output_path: {result.launch_summary['output_path']}")
    if result.failure_reason:
        print(f"failure_reason: {result.failure_reason}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
