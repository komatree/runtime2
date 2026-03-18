#!/usr/bin/env python3
"""Minimal testnet-only harness for the first active private-event exercise.

This script is intentionally narrow:
- testnet only
- no automated order submission
- reuses existing runtime2 preflight, signed-path verification, and soak tooling
- writes an operator-readable summary of what evidence was actually produced
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import RuntimeRehearsalSettings
from app.config import build_run_summary
from app.config import validate_runtime_rehearsal
from app.runtime import RunnerMode


IDLE_PRIVATE_ALERT = "no private payloads available for restricted-live mutation gate"
IDLE_MUTATION_ALERT = "restricted-live portfolio mutation gate observed no live updates"


@dataclass(frozen=True)
class ExerciseArtifacts:
    exercise_dir: Path
    signed_path_dir: Path
    soak_dir: Path
    plan_json_path: Path
    instructions_path: Path
    summary_json_path: Path
    summary_md_path: Path


@dataclass(frozen=True)
class ExerciseEvidenceSummary:
    run_id: str
    checked_at: str
    preflight_ok: bool
    signed_path_check_ran: bool
    signed_path_check_succeeded: bool
    soak_exit_code: int | None
    soak_summary_present: bool
    soak_stop_reason: str | None
    soak_aborted: bool | None
    runtime_cycles_present: bool
    total_cycle_records: int
    cycles_with_reconciliation_events: int
    cycles_without_idle_private_alert: int
    heuristic_active_private_event_detected: bool
    operator_review_required: bool
    detail: str


def _load_binance_config(config_path: Path) -> dict[str, str]:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    binance = payload["binance"]
    return {
        "endpoint_profile_name": str(binance["endpoint_profile_name"]),
        "rest_base_url": str(binance["rest_base_url"]),
        "websocket_base_url": str(binance["websocket_base_url"]),
    }


def _validate_testnet_only(config_path: Path) -> dict[str, str]:
    binance = _load_binance_config(config_path)
    if binance["endpoint_profile_name"] != "binance_spot_testnet":
        raise ValueError("event exercise harness is testnet-only and requires endpoint_profile_name=binance_spot_testnet")
    if "testnet.binance.vision" not in binance["rest_base_url"]:
        raise ValueError("event exercise harness requires Spot testnet REST host")
    if "testnet.binance.vision" not in binance["websocket_base_url"]:
        raise ValueError("event exercise harness requires Spot testnet websocket host")
    return binance


def _build_settings(args: argparse.Namespace, *, run_dir: Path, log_dir: Path) -> RuntimeRehearsalSettings:
    return RuntimeRehearsalSettings(
        mode=RunnerMode.RESTRICTED_LIVE,
        venue="binance",
        config_path=args.config,
        execution_data_path=args.execution_data,
        context_data_path=args.context_data,
        reports_dir=run_dir,
        logs_dir=log_dir,
        exchange_mode=args.exchange_mode,
        command_name="run-runtime2-testnet-event-exercise",
        confirm_rehearsal_only=args.confirm_rehearsal_only,
        allow_restricted_live_rehearsal=args.allow_restricted_live_rehearsal,
        confirm_no_order_submission=args.confirm_no_order_submission,
    )


def _build_signed_path_command(args: argparse.Namespace, signed_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "verify_binance_signed_paths_testnet.py"),
        "--config",
        str(args.config),
        "--allow-live-testnet",
        "--output-dir",
        str(signed_dir),
    ]


def _build_soak_command(args: argparse.Namespace, run_id: str) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "binance_restricted_live_soak.py"),
        "--config",
        str(args.config),
        "--execution-data",
        str(args.execution_data),
        "--context-data",
        str(args.context_data),
        "--reports-dir",
        str(args.reports_dir),
        "--logs-dir",
        str(args.logs_dir),
        "--exchange-mode",
        args.exchange_mode,
        "--run-id",
        run_id,
        "--duration-hours",
        str(args.duration_hours),
        "--cycles",
        str(args.cycles),
        "--poll-interval-seconds",
        str(args.poll_interval_seconds),
        "--output-subdir",
        args.output_subdir,
        "--max-blocked-mutations",
        str(args.max_blocked_mutations),
        "--confirm-rehearsal-only",
        "--allow-restricted-live-rehearsal",
        "--confirm-no-order-submission",
    ]


def _write_plan_and_instructions(
    *,
    artifacts: ExerciseArtifacts,
    args: argparse.Namespace,
    binance_config: dict[str, str],
    signed_command: list[str],
    soak_command: list[str],
) -> None:
    plan = {
        "run_id": args.run_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "config_path": str(args.config),
        "endpoint_profile_name": binance_config["endpoint_profile_name"],
        "exchange_mode": args.exchange_mode,
        "reports_dir": str(args.reports_dir),
        "logs_dir": str(args.logs_dir),
        "signed_path_command": signed_command,
        "soak_command": soak_command,
        "manual_sequence": [
            "create one small order intended to receive acknowledgement",
            "cancel one resting order intended to receive cancel acknowledgement",
            "create one order intended to fill fully if realistically achievable",
            "record approximate wall-clock time for each operator action",
        ],
        "artifact_targets": {
            "signed_path_dir": str(artifacts.signed_path_dir),
            "soak_dir": str(artifacts.soak_dir),
            "summary_json_path": str(artifacts.summary_json_path),
            "summary_md_path": str(artifacts.summary_md_path),
        },
    }
    artifacts.plan_json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    instructions = [
        "# runtime2 Testnet Event Exercise Harness Usage",
        "",
        f"- run_id: `{args.run_id}`",
        f"- config: `{args.config}`",
        f"- endpoint_profile_name: `{binance_config['endpoint_profile_name']}`",
        "",
        "## Manual Event Sequence",
        "",
        "1. Create one small order intended to generate a clear acknowledgement.",
        "2. Cancel one resting order intended to generate a cancel acknowledgement.",
        "3. Create one small order intended to fill fully if realistically achievable.",
        "4. Record approximate wall-clock time for each manual action in operator notes.",
        "",
        "## Signed-Path Precheck Command",
        "",
        "```bash",
        " ".join(signed_command),
        "```",
        "",
        "## Soak Command",
        "",
        "```bash",
        " ".join(soak_command),
        "```",
        "",
        "## Expected Review Paths",
        "",
        f"- signed path artifacts: `{artifacts.signed_path_dir}`",
        f"- soak artifacts: `{artifacts.soak_dir}`",
        f"- harness summary: `{artifacts.summary_json_path}` and `{artifacts.summary_md_path}`",
        "",
        "## Important Limits",
        "",
        "- this helper does not submit orders automatically",
        "- this helper does not prove active-event success automatically",
        "- operator review is still required after the run",
    ]
    artifacts.instructions_path.write_text("\n".join(instructions) + "\n", encoding="utf-8")


def _load_json_if_exists(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_cycle_evidence(runtime_cycles_path: Path) -> tuple[int, int, int]:
    if not runtime_cycles_path.exists():
        return (0, 0, 0)
    total = 0
    reconciliation_cycles = 0
    without_idle_private_alert = 0
    for line in runtime_cycles_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        payload = json.loads(line)
        runtime_cycle = payload.get("runtime_cycle_result", {})
        if runtime_cycle.get("reconciliation_events"):
            reconciliation_cycles += 1
        alerts = tuple(runtime_cycle.get("alerts", ()))
        if IDLE_PRIVATE_ALERT not in alerts and IDLE_MUTATION_ALERT not in alerts:
            without_idle_private_alert += 1
    return (total, reconciliation_cycles, without_idle_private_alert)


def _build_evidence_summary(
    *,
    run_id: str,
    preflight_ok: bool,
    signed_dir: Path,
    soak_dir: Path,
    soak_exit_code: int | None,
    signed_path_check_ran: bool,
) -> ExerciseEvidenceSummary:
    signed_summary = _load_json_if_exists(signed_dir / "signed_path_summary.json")
    soak_summary = _load_json_if_exists(soak_dir / "soak_summary.json")
    total_cycles, reconciliation_cycles, non_idle_cycles = _collect_cycle_evidence(soak_dir / "runtime_cycles.jsonl")
    signed_ok = False
    if signed_summary is not None:
        results = signed_summary.get("results", [])
        signed_ok = any(
            result.get("name") == "live_ws_api_user_data_subscription_on_spot_testnet"
            and result.get("status") == "verified on current Spot testnet"
            for result in results
        )
    heuristic_active = reconciliation_cycles > 0 or non_idle_cycles > 0
    detail = (
        "operator review required; harness can confirm preflight, signed-path precheck, soak completion, "
        "and simple heuristic signs of non-idle cycles, but it cannot prove event correctness without manual artifact review"
    )
    return ExerciseEvidenceSummary(
        run_id=run_id,
        checked_at=datetime.now(UTC).isoformat(),
        preflight_ok=preflight_ok,
        signed_path_check_ran=signed_path_check_ran,
        signed_path_check_succeeded=signed_ok,
        soak_exit_code=soak_exit_code,
        soak_summary_present=soak_summary is not None,
        soak_stop_reason=(str(soak_summary.get("stop_reason")) if soak_summary is not None else None),
        soak_aborted=(bool(soak_summary.get("aborted")) if soak_summary is not None else None),
        runtime_cycles_present=(soak_dir / "runtime_cycles.jsonl").exists(),
        total_cycle_records=total_cycles,
        cycles_with_reconciliation_events=reconciliation_cycles,
        cycles_without_idle_private_alert=non_idle_cycles,
        heuristic_active_private_event_detected=heuristic_active,
        operator_review_required=True,
        detail=detail,
    )


def _render_summary_markdown(summary: ExerciseEvidenceSummary, artifacts: ExerciseArtifacts) -> str:
    return "\n".join(
        [
            "# runtime2 Testnet Event Exercise Summary",
            "",
            f"- run_id: `{summary.run_id}`",
            f"- checked_at: `{summary.checked_at}`",
            f"- preflight_ok: `{summary.preflight_ok}`",
            f"- signed_path_check_ran: `{summary.signed_path_check_ran}`",
            f"- signed_path_check_succeeded: `{summary.signed_path_check_succeeded}`",
            f"- soak_exit_code: `{summary.soak_exit_code}`",
            f"- soak_summary_present: `{summary.soak_summary_present}`",
            f"- soak_stop_reason: `{summary.soak_stop_reason}`",
            f"- soak_aborted: `{summary.soak_aborted}`",
            f"- runtime_cycles_present: `{summary.runtime_cycles_present}`",
            f"- total_cycle_records: `{summary.total_cycle_records}`",
            f"- cycles_with_reconciliation_events: `{summary.cycles_with_reconciliation_events}`",
            f"- cycles_without_idle_private_alert: `{summary.cycles_without_idle_private_alert}`",
            f"- heuristic_active_private_event_detected: `{summary.heuristic_active_private_event_detected}`",
            f"- operator_review_required: `{summary.operator_review_required}`",
            "",
            "## Evidence Paths",
            "",
            f"- signed path dir: `{artifacts.signed_path_dir}`",
            f"- soak dir: `{artifacts.soak_dir}`",
            "",
            "## Interpretation",
            "",
            summary.detail,
        ]
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="run the first runtime2 active private-event testnet exercise")
    parser.add_argument("--config", type=Path, default=Path("configs/runtime2_restricted_live_testnet.toml"))
    parser.add_argument("--execution-data", type=Path, default=Path("data/binance"))
    parser.add_argument("--context-data", type=Path, default=Path("data/binance"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--exchange-mode", default="restricted_live_rehearsal")
    parser.add_argument("--run-id", default=f"binance-testnet-active-private-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--duration-hours", type=int, default=1)
    parser.add_argument("--cycles", type=int, default=40)
    parser.add_argument("--poll-interval-seconds", type=float, default=30.0)
    parser.add_argument("--output-subdir", default="soak_sessions")
    parser.add_argument("--max-blocked-mutations", type=int, default=3)
    parser.add_argument("--skip-signed-path-check", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--confirm-rehearsal-only", action="store_true")
    parser.add_argument("--allow-restricted-live-rehearsal", action="store_true")
    parser.add_argument("--confirm-no-order-submission", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.exchange_mode != "restricted_live_rehearsal":
        raise SystemExit("event exercise harness requires --exchange-mode restricted_live_rehearsal")
    if not os.environ.get("BINANCE_API_KEY") or not os.environ.get("BINANCE_API_SECRET"):
        raise SystemExit("BINANCE_API_KEY and BINANCE_API_SECRET are required")

    binance_config = _validate_testnet_only(args.config)
    soak_dir = args.reports_dir / args.output_subdir / args.run_id
    log_dir = args.logs_dir / args.output_subdir / args.run_id
    exercise_dir = args.reports_dir / "event_exercises" / args.run_id
    exercise_dir.mkdir(parents=True, exist_ok=True)
    artifacts = ExerciseArtifacts(
        exercise_dir=exercise_dir,
        signed_path_dir=exercise_dir / "signed_path_verification",
        soak_dir=soak_dir,
        plan_json_path=exercise_dir / "exercise_plan.json",
        instructions_path=exercise_dir / "exercise_instructions.md",
        summary_json_path=exercise_dir / "exercise_summary.json",
        summary_md_path=exercise_dir / "exercise_summary.md",
    )

    settings = _build_settings(args, run_dir=soak_dir, log_dir=log_dir)
    preflight = validate_runtime_rehearsal(settings, environ=dict(os.environ))
    run_summary = build_run_summary(settings, preflight=preflight)
    if not preflight.ok:
        artifacts.summary_json_path.write_text(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "preflight_ok": False,
                    "errors": run_summary.errors,
                    "checks": run_summary.checks,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        raise SystemExit(1)

    signed_command = _build_signed_path_command(args, artifacts.signed_path_dir)
    soak_command = _build_soak_command(args, args.run_id)
    _write_plan_and_instructions(
        artifacts=artifacts,
        args=args,
        binance_config=binance_config,
        signed_command=signed_command,
        soak_command=soak_command,
    )

    print(f"exercise_instructions: {artifacts.instructions_path}")
    print("manual_event_sequence:")
    print("- create one small order intended to acknowledge")
    print("- cancel one resting order")
    print("- create one order intended to fill fully if realistically achievable")
    print("- record approximate wall-clock time for each action")

    if args.prepare_only:
        summary = ExerciseEvidenceSummary(
            run_id=args.run_id,
            checked_at=datetime.now(UTC).isoformat(),
            preflight_ok=True,
            signed_path_check_ran=not args.skip_signed_path_check,
            signed_path_check_succeeded=False,
            soak_exit_code=None,
            soak_summary_present=False,
            soak_stop_reason=None,
            soak_aborted=None,
            runtime_cycles_present=False,
            total_cycle_records=0,
            cycles_with_reconciliation_events=0,
            cycles_without_idle_private_alert=0,
            heuristic_active_private_event_detected=False,
            operator_review_required=True,
            detail="prepare-only mode wrote the plan and instructions but did not run signed-path verification or soak collection",
        )
        artifacts.summary_json_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
        artifacts.summary_md_path.write_text(_render_summary_markdown(summary, artifacts), encoding="utf-8")
        print(f"exercise_summary_json: {artifacts.summary_json_path}")
        print(f"exercise_summary_md: {artifacts.summary_md_path}")
        return 0

    signed_path_ran = False
    if not args.skip_signed_path_check:
        signed_path_ran = True
        signed_completed = subprocess.run(signed_command, cwd=ROOT, check=False)
        if signed_completed.returncode != 0:
            summary = ExerciseEvidenceSummary(
                run_id=args.run_id,
                checked_at=datetime.now(UTC).isoformat(),
                preflight_ok=True,
                signed_path_check_ran=True,
                signed_path_check_succeeded=False,
                soak_exit_code=None,
                soak_summary_present=False,
                soak_stop_reason=None,
                soak_aborted=None,
                runtime_cycles_present=False,
                total_cycle_records=0,
                cycles_with_reconciliation_events=0,
                cycles_without_idle_private_alert=0,
                heuristic_active_private_event_detected=False,
                operator_review_required=True,
                detail="signed-path precheck failed; soak was not started",
            )
            artifacts.summary_json_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
            artifacts.summary_md_path.write_text(_render_summary_markdown(summary, artifacts), encoding="utf-8")
            return 2

    soak_completed = subprocess.run(soak_command, cwd=ROOT, check=False)
    summary = _build_evidence_summary(
        run_id=args.run_id,
        preflight_ok=True,
        signed_dir=artifacts.signed_path_dir,
        soak_dir=artifacts.soak_dir,
        soak_exit_code=soak_completed.returncode,
        signed_path_check_ran=signed_path_ran,
    )
    artifacts.summary_json_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    artifacts.summary_md_path.write_text(_render_summary_markdown(summary, artifacts), encoding="utf-8")
    print(f"exercise_summary_json: {artifacts.summary_json_path}")
    print(f"exercise_summary_md: {artifacts.summary_md_path}")
    return 0 if soak_completed.returncode == 0 else soak_completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
