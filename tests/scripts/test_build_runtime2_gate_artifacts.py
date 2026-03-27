from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "build_runtime2_gate_artifacts.py"
    spec = importlib.util.spec_from_file_location("build_runtime2_gate_artifacts", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _seed_common_run_artifacts(reports_dir: Path, run_id: str) -> None:
    _write_json(
        reports_dir / "soak_sessions" / run_id / "soak_summary.json",
        {
            "stop_reason": "completed",
            "aborted": False,
            "blocked_mutation_count": 0,
            "completed_cycles": 741,
            "final_exchange_health_state": "healthy",
            "reconnect_count": 234,
            "heartbeat_overdue_events": 233,
            "reconciliation_recovery_attempts": 7,
            "reconciliation_recovery_success_rate": 1.0,
        },
    )
    _write_json(
        reports_dir / "soak_sessions" / run_id / "finalization_debug.json",
        {
            "phase": "artifact_writer.persist",
            "status": "completed",
            "stop_reason": "completed",
            "aborted": False,
        },
    )
    _write_jsonl(
        reports_dir / "soak_sessions" / run_id / "reconciliation_events.jsonl",
        [
            {
                "cycle_id": "restricted-live-soak-bootstrap-testnet-0403",
                "convergence_state": "converged_terminal",
                "manual_attention": False,
                "recovery_trigger_reason": "unknown_execution",
            }
        ],
    )
    _write_jsonl(
        reports_dir / "soak_sessions" / run_id / "reconnect_events.jsonl",
        [
            {
                "cycle_id": "restricted-live-soak-bootstrap-testnet-0741",
                "reason": "heartbeat overdue",
                "reconnect_count": 234,
            }
        ],
    )
    _write_jsonl(
        reports_dir / "event_exercises" / f"{run_id}-scheduler" / "scheduler_events.jsonl",
        [
            {
                "event": "scheduler_start",
                "windows": [
                    {"action_run_id": f"{run_id}-a1"},
                    {"action_run_id": f"{run_id}-a2"},
                    {"action_run_id": f"{run_id}-a3"},
                ],
            },
            {"event": "window_done", "run_id": f"{run_id}-a1"},
            {"event": "window_done", "run_id": f"{run_id}-a2"},
            {"event": "window_done", "run_id": f"{run_id}-a3"},
            {"event": "scheduler_complete"},
        ],
    )


def test_build_gate_artifacts_classifies_pass_with_caution(tmp_path: Path) -> None:
    module = _load_module()
    run_id = "binance-bounded-r6-8h"
    reports_dir = tmp_path / "reports"
    _seed_common_run_artifacts(reports_dir, run_id)

    for window in ("a1", "a2", "a3"):
        _write_json(
            reports_dir / "event_exercises" / f"{run_id}-{window}" / "action_driver" / "action_driver_result.json",
            {
                "run_id": f"{run_id}-{window}",
                "window_outcome": "PARTIAL_SUCCESS_NONBLOCKING",
                "failure_reasons": [
                    "place_resting_create_order: binance error -1013: Filter failure: PERCENT_PRICE_BY_SIDE"
                ],
            },
        )

    gate_dir = module.build_gate_artifacts(run_id=run_id, reports_dir=reports_dir)

    manifest = json.loads((gate_dir / "gate_manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "PASS WITH CAUTION"
    assert manifest["failure_class"] is None
    assert manifest["known_cautions"] == ["PERCENT_PRICE_BY_SIDE", "reconnect_heartbeat_churn"]
    assert manifest["summary"]["scheduler_complete"] is True
    assert manifest["summary"]["manual_attention_count"] == 0

    scorecard = (gate_dir / "gate_scorecard.md").read_text(encoding="utf-8")
    assert "reconnect_count: `234`" in scorecard
    assert "Failure class: `none`" in scorecard


def test_build_gate_artifacts_classifies_fail_on_manual_attention(tmp_path: Path) -> None:
    module = _load_module()
    run_id = "binance-bounded-r7-8h"
    reports_dir = tmp_path / "reports"
    _seed_common_run_artifacts(reports_dir, run_id)
    _write_jsonl(
        reports_dir / "soak_sessions" / run_id / "reconciliation_events.jsonl",
        [
            {
                "cycle_id": "restricted-live-soak-bootstrap-testnet-0431",
                "convergence_state": "unreconciled_manual_attention",
                "manual_attention": True,
                "recovery_trigger_reason": "unknown_execution",
            }
        ],
    )

    for window in ("a1", "a2", "a3"):
        _write_json(
            reports_dir / "event_exercises" / f"{run_id}-{window}" / "action_driver" / "action_driver_result.json",
            {
                "run_id": f"{run_id}-{window}",
                "window_outcome": "SUCCESS",
                "failure_reasons": [],
            },
        )

    gate_dir = module.build_gate_artifacts(run_id=run_id, reports_dir=reports_dir)

    manifest = json.loads((gate_dir / "gate_manifest.json").read_text(encoding="utf-8"))
    assert manifest["verdict"] == "FAIL"
    assert manifest["failure_class"] == "reconciliation"
    assert manifest["summary"]["manual_attention_count"] == 1

    decision = (gate_dir / "operator_decision.md").read_text(encoding="utf-8")
    assert "Review reconciliation/manual-attention evidence before another bounded run." in decision
