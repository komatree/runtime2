from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WINDOW_NAMES = ("a1", "a2", "a3")


@dataclass(frozen=True)
class GatePaths:
    run_id: str
    reports_dir: Path
    runtime_dir: Path
    scheduler_dir: Path
    gate_dir: Path


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _discover_action_run_ids(scheduler_events: list[dict[str, Any]], run_id: str) -> list[str]:
    for event in scheduler_events:
        windows = event.get("windows")
        if isinstance(windows, list) and windows:
            run_ids = [
                str(window.get("action_run_id"))
                for window in windows
                if isinstance(window, dict) and window.get("action_run_id")
            ]
            if run_ids:
                return run_ids
    return [f"{run_id}-{name}" for name in WINDOW_NAMES]


def _run_type(run_id: str) -> str:
    lowered = run_id.lower()
    if "envcheck" in lowered or "env-check" in lowered:
        return "env_check"
    return "bounded"


def _paths(run_id: str, reports_dir: Path) -> GatePaths:
    return GatePaths(
        run_id=run_id,
        reports_dir=reports_dir,
        runtime_dir=reports_dir / "soak_sessions" / run_id,
        scheduler_dir=reports_dir / "event_exercises" / f"{run_id}-scheduler",
        gate_dir=reports_dir / "gates" / run_id,
    )


def _collect_gate_inputs(paths: GatePaths) -> dict[str, Any]:
    soak_summary_path = paths.runtime_dir / "soak_summary.json"
    finalization_debug_path = paths.runtime_dir / "finalization_debug.json"
    reconciliation_events_path = paths.runtime_dir / "reconciliation_events.jsonl"
    reconnect_events_path = paths.runtime_dir / "reconnect_events.jsonl"
    scheduler_events_path = paths.scheduler_dir / "scheduler_events.jsonl"

    scheduler_events = _load_jsonl(scheduler_events_path)
    action_run_ids = _discover_action_run_ids(scheduler_events, paths.run_id)
    action_result_paths = [
        paths.reports_dir / "event_exercises" / action_run_id / "action_driver" / "action_driver_result.json"
        for action_run_id in action_run_ids
    ]
    action_results = {path: _load_json(path) for path in action_result_paths}

    return {
        "soak_summary_path": soak_summary_path,
        "finalization_debug_path": finalization_debug_path,
        "reconciliation_events_path": reconciliation_events_path,
        "reconnect_events_path": reconnect_events_path,
        "scheduler_events_path": scheduler_events_path,
        "soak_summary": _load_json(soak_summary_path),
        "finalization_debug": _load_json(finalization_debug_path),
        "reconciliation_events": _load_jsonl(reconciliation_events_path),
        "reconnect_events": _load_jsonl(reconnect_events_path),
        "scheduler_events": scheduler_events,
        "action_run_ids": action_run_ids,
        "action_results": action_results,
    }


def _detect_known_cautions(
    soak_summary: dict[str, Any] | None,
    reconnect_events: list[dict[str, Any]],
    action_results: dict[Path, dict[str, Any] | None],
) -> list[str]:
    cautions: list[str] = []
    if soak_summary and (
        int(soak_summary.get("reconnect_count", 0)) > 0
        or int(soak_summary.get("heartbeat_overdue_events", 0)) > 0
    ):
        cautions.append("reconnect_heartbeat_churn")
    elif any(event.get("reason") == "heartbeat overdue" for event in reconnect_events):
        cautions.append("reconnect_heartbeat_churn")

    for result in action_results.values():
        if not result:
            continue
        outcome = str(result.get("window_outcome", ""))
        reasons = result.get("failure_reasons", [])
        if any("PERCENT_PRICE_BY_SIDE" in str(reason) for reason in reasons) or outcome == "PARTIAL_SUCCESS_NONBLOCKING":
            cautions.append("PERCENT_PRICE_BY_SIDE")
            break

    return sorted(set(cautions))


def _missing_evidence(
    paths: GatePaths,
    gate_inputs: dict[str, Any],
) -> list[str]:
    required_paths = [
        gate_inputs["soak_summary_path"],
        gate_inputs["finalization_debug_path"],
        gate_inputs["reconciliation_events_path"],
        gate_inputs["reconnect_events_path"],
        gate_inputs["scheduler_events_path"],
        *gate_inputs["action_results"].keys(),
    ]
    return sorted(
        _relative(path, paths.reports_dir.parent)
        for path in required_paths
        if not path.exists()
    )


def _manual_attention_count(reconciliation_events: list[dict[str, Any]]) -> int:
    return sum(1 for event in reconciliation_events if bool(event.get("manual_attention")))


def _scheduler_complete(scheduler_events: list[dict[str, Any]], action_run_ids: list[str]) -> bool:
    complete = any(event.get("event") == "scheduler_complete" for event in scheduler_events)
    window_done = {
        str(event.get("run_id"))
        for event in scheduler_events
        if event.get("event") == "window_done" and event.get("run_id")
    }
    return complete and all(run_id in window_done for run_id in action_run_ids)


def _failure_class(
    missing_evidence: list[str],
    soak_summary: dict[str, Any] | None,
    finalization_debug: dict[str, Any] | None,
    scheduler_complete: bool,
    manual_attention_count: int,
) -> str | None:
    if missing_evidence:
        return "artifact_gap"
    if finalization_debug and str(finalization_debug.get("status")) != "completed":
        return "finalization"
    if not scheduler_complete:
        return "scheduler"
    if manual_attention_count > 0:
        return "reconciliation"
    if soak_summary and (
        str(soak_summary.get("stop_reason")) != "completed"
        or bool(soak_summary.get("aborted"))
        or int(soak_summary.get("blocked_mutation_count", 0)) != 0
    ):
        return "runtime"
    return None


def _verdict(
    run_type: str,
    failure_class: str | None,
    cautions: list[str],
) -> str:
    if failure_class is not None:
        return "ENV-CHECK FAIL" if run_type == "env_check" else "FAIL"
    if cautions:
        return "ENV-CHECK PASS WITH CAUTION" if run_type == "env_check" else "PASS WITH CAUTION"
    return "ENV-CHECK PASS" if run_type == "env_check" else "PASS"


def _build_manifest(paths: GatePaths, gate_inputs: dict[str, Any]) -> dict[str, Any]:
    soak_summary = gate_inputs["soak_summary"]
    finalization_debug = gate_inputs["finalization_debug"]
    reconciliation_events = gate_inputs["reconciliation_events"]
    reconnect_events = gate_inputs["reconnect_events"]
    scheduler_events = gate_inputs["scheduler_events"]
    action_results = gate_inputs["action_results"]
    action_run_ids = gate_inputs["action_run_ids"]

    cautions = _detect_known_cautions(soak_summary, reconnect_events, action_results)
    missing = _missing_evidence(paths, gate_inputs)
    scheduler_complete = _scheduler_complete(scheduler_events, action_run_ids)
    manual_attention_count = _manual_attention_count(reconciliation_events)
    failure_class = _failure_class(
        missing,
        soak_summary,
        finalization_debug,
        scheduler_complete,
        manual_attention_count,
    )
    run_type = _run_type(paths.run_id)
    verdict = _verdict(run_type, failure_class, cautions)

    summary = {
        "stop_reason": soak_summary.get("stop_reason") if soak_summary else None,
        "aborted": soak_summary.get("aborted") if soak_summary else None,
        "blocked_mutation_count": soak_summary.get("blocked_mutation_count") if soak_summary else None,
        "completed_cycles": soak_summary.get("completed_cycles") if soak_summary else None,
        "final_exchange_health_state": soak_summary.get("final_exchange_health_state") if soak_summary else None,
        "reconnect_count": soak_summary.get("reconnect_count") if soak_summary else None,
        "heartbeat_overdue_events": soak_summary.get("heartbeat_overdue_events") if soak_summary else None,
        "reconciliation_recovery_attempts": soak_summary.get("reconciliation_recovery_attempts") if soak_summary else None,
        "reconciliation_recovery_success_rate": soak_summary.get("reconciliation_recovery_success_rate") if soak_summary else None,
        "finalization_phase": finalization_debug.get("phase") if finalization_debug else None,
        "finalization_status": finalization_debug.get("status") if finalization_debug else None,
        "scheduler_complete": scheduler_complete,
        "manual_attention_count": manual_attention_count,
        "action_outcomes": {
            path.parent.parent.name: (
                result.get("window_outcome") if result else None
            )
            for path, result in action_results.items()
        },
    }

    return {
        "run_id": paths.run_id,
        "run_type": run_type,
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "failure_class": failure_class,
        "known_cautions": cautions,
        "missing_evidence": missing,
        "evidence": {
            "runtime": [
                _relative(gate_inputs["soak_summary_path"], paths.reports_dir.parent),
                _relative(gate_inputs["finalization_debug_path"], paths.reports_dir.parent),
                _relative(gate_inputs["reconciliation_events_path"], paths.reports_dir.parent),
                _relative(gate_inputs["reconnect_events_path"], paths.reports_dir.parent),
            ],
            "scheduler": [
                _relative(gate_inputs["scheduler_events_path"], paths.reports_dir.parent),
            ],
            "actions": [
                _relative(path, paths.reports_dir.parent)
                for path in action_results.keys()
            ],
        },
        "summary": summary,
    }


def _render_scorecard(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    cautions = manifest["known_cautions"]
    caution_text = ", ".join(cautions) if cautions else "none"
    missing = manifest["missing_evidence"]
    missing_text = "\n".join(f"- `{path}`" for path in missing) if missing else "- none"
    action_lines = "\n".join(
        f"- `{run_id}`: `{outcome}`"
        for run_id, outcome in sorted(summary["action_outcomes"].items())
    )
    return "\n".join(
        [
            f"# runtime2 Gate Scorecard: {manifest['run_id']}",
            "",
            f"- Verdict: `{manifest['verdict']}`",
            f"- Run type: `{manifest['run_type']}`",
            f"- Failure class: `{manifest['failure_class'] or 'none'}`",
            f"- Known cautions: `{caution_text}`",
            "",
            "## Core Checks",
            f"- Clean stop: `stop_reason={summary['stop_reason']}` / `aborted={summary['aborted']}`",
            f"- Blocked mutation count: `{summary['blocked_mutation_count']}`",
            f"- Finalization: `phase={summary['finalization_phase']}` / `status={summary['finalization_status']}`",
            f"- Scheduler complete: `{summary['scheduler_complete']}`",
            f"- Manual attention count: `{summary['manual_attention_count']}`",
            "",
            "## Reconnect / Recovery",
            f"- reconnect_count: `{summary['reconnect_count']}`",
            f"- heartbeat_overdue_events: `{summary['heartbeat_overdue_events']}`",
            f"- reconciliation_recovery_attempts: `{summary['reconciliation_recovery_attempts']}`",
            f"- reconciliation_recovery_success_rate: `{summary['reconciliation_recovery_success_rate']}`",
            "",
            "## Action Windows",
            action_lines,
            "",
            "## Missing Evidence",
            missing_text,
            "",
        ]
    )


def _render_operator_decision(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    cautions = manifest["known_cautions"]
    next_action: str
    if manifest["failure_class"] == "artifact_gap":
        next_action = "Inspect the interrupted or incomplete artifact family before any rerun. Use a fresh run id."
    elif manifest["failure_class"] == "finalization":
        next_action = "Review `finalization_debug.json` and fix finalization before another bounded run."
    elif manifest["failure_class"] == "scheduler":
        next_action = "Review scheduler continuity and missing window artifacts before another bounded run."
    elif manifest["failure_class"] == "reconciliation":
        next_action = "Review reconciliation/manual-attention evidence before another bounded run."
    elif manifest["failure_class"] == "runtime":
        next_action = "Review runtime stop reason and exchange-health evidence before another bounded run."
    elif "reconnect_heartbeat_churn" in cautions:
        next_action = "Proceed only with bounded-stage caution handling. Compare reconnect metrics against the retained baseline."
    elif "PERCENT_PRICE_BY_SIDE" in cautions:
        next_action = "Proceed only with bounded-stage caution handling. Review action-driver prevalidation for exchange-rule drift."
    else:
        next_action = "This run is a clean bounded-stage candidate. Continue with the next approved validation step."

    caution_text = ", ".join(cautions) if cautions else "none"
    return "\n".join(
        [
            f"# Operator Decision: {manifest['run_id']}",
            "",
            f"- Verdict: `{manifest['verdict']}`",
            f"- Failure class: `{manifest['failure_class'] or 'none'}`",
            f"- Known cautions: `{caution_text}`",
            "",
            "## Key Evidence",
            f"- stop_reason: `{summary['stop_reason']}`",
            f"- aborted: `{summary['aborted']}`",
            f"- blocked_mutation_count: `{summary['blocked_mutation_count']}`",
            f"- finalization_status: `{summary['finalization_status']}`",
            f"- scheduler_complete: `{summary['scheduler_complete']}`",
            f"- manual_attention_count: `{summary['manual_attention_count']}`",
            "",
            "## Next Action",
            next_action,
            "",
            "## Operator Notes",
            "- Add any run-specific note here if a manual review decision differs from the generated verdict.",
            "",
        ]
    )


def build_gate_artifacts(run_id: str, reports_dir: Path) -> Path:
    paths = _paths(run_id, reports_dir)
    gate_inputs = _collect_gate_inputs(paths)
    manifest = _build_manifest(paths, gate_inputs)

    paths.gate_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = paths.gate_dir / "gate_manifest.json"
    scorecard_path = paths.gate_dir / "gate_scorecard.md"
    decision_path = paths.gate_dir / "operator_decision.md"

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scorecard_path.write_text(_render_scorecard(manifest), encoding="utf-8")
    decision_path.write_text(_render_operator_decision(manifest), encoding="utf-8")
    return paths.gate_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the minimal bounded-stage gate artifacts for a runtime2 run.")
    parser.add_argument("run_id", help="Runtime run id, for example binance-bounded-r6-8h")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Reports root directory. Defaults to ./reports",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    build_gate_artifacts(run_id=args.run_id, reports_dir=args.reports_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
