from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "run_runtime2_testnet_event_exercise.py"
    spec = importlib.util.spec_from_file_location("run_runtime2_testnet_event_exercise", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_testnet_only_accepts_spot_testnet_config() -> None:
    module = _load_module()
    config = Path("configs/runtime2_restricted_live_testnet.toml")

    result = module._validate_testnet_only(config)

    assert result["endpoint_profile_name"] == "binance_spot_testnet"
    assert "testnet.binance.vision" in result["rest_base_url"]
    assert "testnet.binance.vision" in result["websocket_base_url"]


def test_build_evidence_summary_marks_operator_review_required(tmp_path: Path) -> None:
    module = _load_module()
    run_id = "exercise-test"
    signed_dir = tmp_path / "signed"
    soak_dir = tmp_path / "soak"
    signed_dir.mkdir()
    soak_dir.mkdir()
    (signed_dir / "signed_path_summary.json").write_text(
        '{"results":[{"name":"live_ws_api_user_data_subscription_on_spot_testnet","status":"verified on current Spot testnet"}]}',
        encoding="utf-8",
    )
    (soak_dir / "soak_summary.json").write_text(
        '{"stop_reason":"completed","aborted":false}',
        encoding="utf-8",
    )
    (soak_dir / "runtime_cycles.jsonl").write_text(
        '{"runtime_cycle_result":{"alerts":[],"reconciliation_events":[{"order_id":"1"}]}}\n',
        encoding="utf-8",
    )

    summary = module._build_evidence_summary(
        run_id=run_id,
        preflight_ok=True,
        signed_dir=signed_dir,
        soak_dir=soak_dir,
        soak_exit_code=0,
        signed_path_check_ran=True,
    )

    assert summary.signed_path_check_succeeded is True
    assert summary.soak_stop_reason == "completed"
    assert summary.heuristic_active_private_event_detected is True
    assert summary.operator_review_required is True


def test_build_soak_command_keeps_rehearsal_flags() -> None:
    module = _load_module()
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "--confirm-rehearsal-only",
            "--allow-restricted-live-rehearsal",
            "--confirm-no-order-submission",
        ]
    )

    command = module._build_soak_command(args, "sample-run")

    assert "--confirm-rehearsal-only" in command
    assert "--allow-restricted-live-rehearsal" in command
    assert "--confirm-no-order-submission" in command
    assert "sample-run" in command
