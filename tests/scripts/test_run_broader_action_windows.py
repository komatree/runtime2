from __future__ import annotations

import importlib.util
import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import textwrap
import sys

import pytest


def _load_scheduler_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "run_broader_action_windows.py"
    spec = importlib.util.spec_from_file_location("run_broader_action_windows", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_soak_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "binance_restricted_live_soak.py"
    spec = importlib.util.spec_from_file_location("binance_restricted_live_soak", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_runtime_session_from_runtime_run_id(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r7"
    session_path = tmp_path / "reports" / "soak_sessions" / runtime_run_id / "runtime_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_run_id,
                "started_at": "2026-03-17T22:15:00+09:00",
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        runtime_run_id=runtime_run_id,
        runtime_session_file=None,
        runtime_start_iso=None,
        run_stem=None,
        reports_dir=tmp_path / "reports",
    )

    session = module._load_runtime_session(args)

    assert session.runtime_run_id == runtime_run_id
    assert session.started_at.isoformat() == "2026-03-17T22:15:00+09:00"
    assert session.session_file == session_path


def test_scheduler_ids_derive_from_runtime_run_id() -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r4"
    window = module.WindowSpec(name="a2", offset_minutes=140, mode="fill")

    assert module._action_run_id(runtime_run_id, window) == "binance-testnet-broader-rehearsal-r4-a2"
    assert module._scheduler_run_id(runtime_run_id) == "binance-testnet-broader-rehearsal-r4-scheduler"


def test_main_aborts_if_scheduler_dir_already_exists(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r8"
    session_path = tmp_path / "reports" / "soak_sessions" / runtime_run_id / "runtime_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_run_id,
                "started_at": "2026-03-17T22:15:00+09:00",
            }
        ),
        encoding="utf-8",
    )
    scheduler_dir = tmp_path / "reports" / "event_exercises" / f"{runtime_run_id}-scheduler"
    scheduler_dir.mkdir(parents=True)
    (scheduler_dir / "old.jsonl").write_text("stale\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        module.main(
            [
                "--runtime-run-id",
                runtime_run_id,
                "--reports-dir",
                str(tmp_path / "reports"),
            ]
        )


def test_main_writes_scheduler_manifest_from_runtime_metadata(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r9"
    session_path = tmp_path / "reports" / "soak_sessions" / runtime_run_id / "runtime_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_run_id,
                "started_at": "2026-03-17T22:15:00+09:00",
            }
        ),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--runtime-run-id",
            runtime_run_id,
            "--reports-dir",
            str(tmp_path / "reports"),
            "--late-policy",
            "skip",
            "--offset-minutes",
            "0",
            "1",
            "2",
        ]
    )

    assert exit_code == 0
    manifest_path = tmp_path / "reports" / "event_exercises" / f"{runtime_run_id}-scheduler" / "scheduler_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["runtime_run_id"] == runtime_run_id
    assert payload["runtime_started_at"] == "2026-03-17T22:15:00+09:00"
    assert payload["scheduler_run_id"] == f"{runtime_run_id}-scheduler"
    assert payload["action_run_ids"] == {
        "a1": f"{runtime_run_id}-a1",
        "a2": f"{runtime_run_id}-a2",
        "a3": f"{runtime_run_id}-a3",
    }


def test_write_runtime_session_metadata(tmp_path: Path) -> None:
    module = _load_soak_module()
    path = tmp_path / "runtime_session.json"
    started_at = datetime(2026, 3, 17, 22, 15, tzinfo=UTC)

    module._write_runtime_session_metadata(
        path=path,
        run_id="binance-testnet-broader-rehearsal-r10",
        exchange_mode="restricted_live_rehearsal",
        started_at=started_at,
        config_path=Path("configs/runtime2_restricted_live_testnet.toml"),
        reports_dir=Path("reports/soak_sessions/binance-testnet-broader-rehearsal-r10"),
        logs_dir=Path("logs/soak_sessions/binance-testnet-broader-rehearsal-r10"),
        instrument_id="BTC-USDT",
        output_subdir="soak_sessions",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runtime_run_id"] == "binance-testnet-broader-rehearsal-r10"
    assert payload["exchange_mode"] == "restricted_live_rehearsal"
    assert payload["instrument_id"] == "BTC-USDT"
    assert payload["output_subdir"] == "soak_sessions"
    assert payload["session_state"] == "started"


def _write_stub_driver(path: Path, *, outcome: str) -> None:
    mandatory_success = outcome == "SUCCESS"
    path.write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env python3
            import json
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            run_id = args[args.index("--run-id") + 1]
            reports_dir = Path(args[args.index("--reports-dir") + 1])
            action_dir = reports_dir / "event_exercises" / run_id / "action_driver"
            action_dir.mkdir(parents=True, exist_ok=True)
            (action_dir / "action_driver_summary.md").write_text("# stub\\n", encoding="utf-8")
            (action_dir / "action_driver_result.json").write_text(
                json.dumps(
                    {{
                        "run_id": run_id,
                        "window_outcome": "{outcome}",
                        "mandatory_success": {mandatory_success},
                        "fill_attempt_enabled": True,
                        "successful_actions": 1,
                        "failed_actions": 0,
                        "failure_reasons": [],
                        "create_leg_success": {mandatory_success},
                        "cancel_leg_success": {mandatory_success},
                        "fill_leg_success": True,
                    }},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            sys.exit(1 if "{outcome}" == "FATAL_FAILURE" else 0)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_runtime_session(tmp_path: Path, runtime_run_id: str) -> None:
    session_path = tmp_path / "reports" / "soak_sessions" / runtime_run_id / "runtime_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_run_id,
                "started_at": "2026-03-17T22:15:00+09:00",
            }
        ),
        encoding="utf-8",
    )


def test_scheduler_continues_on_partial_success_nonblocking(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r11"
    _write_runtime_session(tmp_path, runtime_run_id)
    driver_script = tmp_path / "stub_driver_partial.py"
    _write_stub_driver(driver_script, outcome="PARTIAL_SUCCESS_NONBLOCKING")

    exit_code = module.main(
        [
            "--runtime-run-id",
            runtime_run_id,
            "--reports-dir",
            str(tmp_path / "reports"),
            "--python-bin",
            sys.executable,
            "--driver-script",
            str(driver_script),
            "--offset-minutes",
            "0",
            "0",
            "0",
            "--late-policy",
            "run-now",
        ]
    )

    assert exit_code == 0
    scheduler_log = tmp_path / "reports" / "event_exercises" / f"{runtime_run_id}-scheduler" / "scheduler_events.jsonl"
    rows = [json.loads(line) for line in scheduler_log.read_text(encoding="utf-8").splitlines()]
    done_rows = [row for row in rows if row["event"] == "window_done"]
    assert [row["window"] for row in done_rows] == ["a1", "a2", "a3"]
    assert all(row["window_outcome"] == "PARTIAL_SUCCESS_NONBLOCKING" for row in done_rows)
    assert all(row["result_artifact_found"] is True for row in done_rows)


def test_scheduler_aborts_on_fatal_failure(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r12"
    _write_runtime_session(tmp_path, runtime_run_id)
    driver_script = tmp_path / "stub_driver_fatal.py"
    _write_stub_driver(driver_script, outcome="FATAL_FAILURE")

    exit_code = module.main(
        [
            "--runtime-run-id",
            runtime_run_id,
            "--reports-dir",
            str(tmp_path / "reports"),
            "--python-bin",
            sys.executable,
            "--driver-script",
            str(driver_script),
            "--offset-minutes",
            "0",
            "0",
            "0",
            "--late-policy",
            "run-now",
        ]
    )

    assert exit_code == 2
    scheduler_log = tmp_path / "reports" / "event_exercises" / f"{runtime_run_id}-scheduler" / "scheduler_events.jsonl"
    rows = [json.loads(line) for line in scheduler_log.read_text(encoding="utf-8").splitlines()]
    done_rows = [row for row in rows if row["event"] == "window_done"]
    assert [row["window"] for row in done_rows] == ["a1"]
    assert done_rows[0]["window_outcome"] == "FATAL_FAILURE"


def test_scheduler_late_abort_behavior_remains_fail_closed(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    runtime_run_id = "binance-testnet-broader-rehearsal-r13"
    session_path = tmp_path / "reports" / "soak_sessions" / runtime_run_id / "runtime_session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_run_id,
                "started_at": "2026-03-17T22:15:00+09:00",
            }
        ),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--runtime-run-id",
            runtime_run_id,
            "--reports-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 2
    scheduler_log = tmp_path / "reports" / "event_exercises" / f"{runtime_run_id}-scheduler" / "scheduler_events.jsonl"
    rows = [json.loads(line) for line in scheduler_log.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "window_aborted_late"
