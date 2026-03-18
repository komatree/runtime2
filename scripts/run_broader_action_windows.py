#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class WindowSpec:
    name: str
    offset_minutes: int
    mode: str  # "fill" or "create_cancel"


@dataclass(frozen=True)
class RuntimeSession:
    runtime_run_id: str
    started_at: datetime
    session_file: Path


SUCCESS = "SUCCESS"
PARTIAL_SUCCESS_NONBLOCKING = "PARTIAL_SUCCESS_NONBLOCKING"
FATAL_FAILURE = "FATAL_FAILURE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run broader rehearsal action windows automatically at scheduled offsets."
    )
    parser.add_argument(
        "--runtime-run-id",
        help="Authoritative runtime run id used to locate reports/soak_sessions/<run_id>/runtime_session.json.",
    )
    parser.add_argument(
        "--runtime-session-file",
        type=Path,
        help="Optional explicit path to runtime_session.json. Overrides the default derived path.",
    )
    parser.add_argument(
        "--runtime-start-iso",
        help="Fallback/debug-only ISO-8601 runtime start time. Not the normal operator path.",
    )
    parser.add_argument(
        "--run-stem",
        help="Fallback/debug-only run stem used when runtime-run-id is unavailable.",
    )
    parser.add_argument(
        "--config",
        default="configs/runtime2_restricted_live_testnet.toml",
        help="Config path for the action driver.",
    )
    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="Trading symbol for the action driver.",
    )
    parser.add_argument(
        "--qty",
        default="0.01",
        help="Quantity passed to the action driver.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter to use for child runs.",
    )
    parser.add_argument(
        "--driver-script",
        default="scripts/run_testnet_event_action_driver.py",
        help="Path to the action driver script.",
    )
    parser.add_argument(
        "--offset-minutes",
        nargs=3,
        type=int,
        default=[20, 140, 260],
        help="Three offsets in minutes for a1/a2/a3. Default: 20 140 260",
    )
    parser.add_argument(
        "--modes",
        nargs=3,
        default=["fill", "fill", "fill"],
        choices=["fill", "create_cancel"],
        help="Modes for a1/a2/a3. Default: fill fill fill",
    )
    parser.add_argument(
        "--late-policy",
        choices=["abort", "run-now", "skip"],
        default="abort",
        help="What to do if a window is already late when reached. Default stays fail-closed: abort.",
    )
    parser.add_argument(
        "--late-grace-seconds",
        type=int,
        default=20,
        help="Grace window before late-policy applies. Default: 20 seconds.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Base reports directory. Used to locate runtime metadata and event exercise outputs.",
    )
    return parser.parse_args()


def parse_iso(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        raise ValueError("timestamp must include timezone offset")
    return dt


def write_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_result_artifact(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_windows(args: argparse.Namespace) -> List[WindowSpec]:
    names = ["a1", "a2", "a3"]
    return [
        WindowSpec(name=name, offset_minutes=offset, mode=mode)
        for name, offset, mode in zip(names, args.offset_minutes, args.modes)
    ]


def _require_fresh_dir(path: Path, *, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"{label} already exists and is not empty: {path}")


def _load_runtime_session(args: argparse.Namespace) -> RuntimeSession:
    if args.runtime_session_file is not None:
        session_file = args.runtime_session_file
    elif args.runtime_run_id is not None:
        session_file = args.reports_dir / "soak_sessions" / args.runtime_run_id / "runtime_session.json"
    elif args.runtime_start_iso is not None:
        started_at = parse_iso(args.runtime_start_iso)
        run_stem = args.run_stem or "broader-rehearsal-debug"
        return RuntimeSession(
            runtime_run_id=run_stem,
            started_at=started_at,
            session_file=Path("<runtime-start-iso-fallback>"),
        )
    else:
        raise ValueError("provide --runtime-run-id or --runtime-session-file; --runtime-start-iso is fallback/debug only")

    if not session_file.exists():
        raise FileNotFoundError(f"runtime session metadata not found: {session_file}")
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    runtime_run_id = str(payload["runtime_run_id"])
    started_at = parse_iso(str(payload["started_at"]))
    if args.runtime_run_id is not None and runtime_run_id != args.runtime_run_id:
        raise ValueError(
            f"runtime session metadata mismatch: expected run id {args.runtime_run_id}, got {runtime_run_id}"
        )
    return RuntimeSession(
        runtime_run_id=runtime_run_id,
        started_at=started_at,
        session_file=session_file,
    )


def _action_run_id(runtime_run_id: str, window: WindowSpec) -> str:
    return f"{runtime_run_id}-{window.name}"


def _scheduler_run_id(runtime_run_id: str) -> str:
    return f"{runtime_run_id}-scheduler"


def _reports_event_dir(args: argparse.Namespace) -> Path:
    return args.reports_dir / "event_exercises"


def run_window(
    *,
    args: argparse.Namespace,
    runtime_session: RuntimeSession,
    window: WindowSpec,
    scheduler_log: Path,
) -> int:
    target_time = runtime_session.started_at + timedelta(minutes=window.offset_minutes)
    action_run_id = _action_run_id(runtime_session.runtime_run_id, window)
    action_dir = _reports_event_dir(args) / action_run_id / "action_driver"
    stdout_log = action_dir / "scheduler_stdout.log"
    stderr_log = action_dir / "scheduler_stderr.log"
    result_path = action_dir / "action_driver_result.json"

    while True:
        now = datetime.now(runtime_session.started_at.tzinfo)
        delta = (target_time - now).total_seconds()
        if delta <= 0:
            break
        time.sleep(min(delta, 5.0))

    actual_now = datetime.now(runtime_session.started_at.tzinfo)
    lateness = (actual_now - target_time).total_seconds()
    if lateness > args.late_grace_seconds:
        if args.late_policy == "abort":
            row = {
                "event": "window_aborted_late",
                "window": window.name,
                "scheduled_time": target_time.isoformat(),
                "actual_time": actual_now.isoformat(),
                "lateness_seconds": lateness,
                "policy": args.late_policy,
            }
            write_jsonl(scheduler_log, row)
            return 2
        if args.late_policy == "skip":
            row = {
                "event": "window_skipped_late",
                "window": window.name,
                "scheduled_time": target_time.isoformat(),
                "actual_time": actual_now.isoformat(),
                "lateness_seconds": lateness,
                "policy": args.late_policy,
            }
            write_jsonl(scheduler_log, row)
            return 0

    _require_fresh_dir(action_dir, label=f"action output directory for {action_run_id}")

    cmd = [
        args.python_bin,
        args.driver_script,
        "--run-id",
        action_run_id,
        "--config",
        args.config,
        "--symbol",
        args.symbol,
        "--qty",
        args.qty,
        "--reports-dir",
        str(args.reports_dir),
    ]
    if window.mode == "fill":
        cmd.append("--enable-fill-attempt")

    write_jsonl(
        scheduler_log,
        {
            "event": "window_start",
            "window": window.name,
            "mode": window.mode,
            "run_id": action_run_id,
            "scheduled_time": target_time.isoformat(),
            "launch_time": actual_now.isoformat(),
            "lateness_seconds": max(lateness, 0.0),
            "cmd": cmd,
        },
    )

    action_dir.mkdir(parents=True, exist_ok=True)
    with stdout_log.open("w", encoding="utf-8") as out_handle, stderr_log.open("w", encoding="utf-8") as err_handle:
        proc = subprocess.run(cmd, stdout=out_handle, stderr=err_handle, env=os.environ.copy(), text=True)

    summary_path = action_dir / "action_driver_summary.md"
    result_payload = _load_result_artifact(result_path)
    window_outcome = (
        str(result_payload.get("window_outcome"))
        if isinstance(result_payload, dict) and result_payload.get("window_outcome") is not None
        else FATAL_FAILURE
    )
    write_jsonl(
        scheduler_log,
        {
            "event": "window_done",
            "window": window.name,
            "mode": window.mode,
            "run_id": action_run_id,
            "window_outcome": window_outcome,
            "exit_code": proc.returncode,
            "result_artifact_found": result_payload is not None,
            "summary_exists": summary_path.exists(),
            "finished_at": datetime.now(runtime_session.started_at.tzinfo).isoformat(),
        },
    )
    if result_payload is None:
        return 2
    if window_outcome in {SUCCESS, PARTIAL_SUCCESS_NONBLOCKING}:
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    original_argv = sys.argv
    if argv is not None:
        sys.argv = [original_argv[0], *argv]
    try:
        args = parse_args()
    finally:
        if argv is not None:
            sys.argv = original_argv
    windows = build_windows(args)
    runtime_session = _load_runtime_session(args)

    scheduler_run_id = _scheduler_run_id(runtime_session.runtime_run_id)
    scheduler_dir = _reports_event_dir(args) / scheduler_run_id
    _require_fresh_dir(scheduler_dir, label=f"scheduler output directory for {scheduler_run_id}")
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    scheduler_log = scheduler_dir / "scheduler_events.jsonl"
    scheduler_manifest = scheduler_dir / "scheduler_manifest.json"

    action_run_ids = {
        window.name: _action_run_id(runtime_session.runtime_run_id, window) for window in windows
    }
    scheduler_started_at = datetime.now(runtime_session.started_at.tzinfo)
    scheduler_manifest.write_text(
        json.dumps(
            {
                "runtime_run_id": runtime_session.runtime_run_id,
                "runtime_started_at": runtime_session.started_at.isoformat(),
                "runtime_session_file": str(runtime_session.session_file),
                "scheduler_started_at": scheduler_started_at.isoformat(),
                "scheduler_run_id": scheduler_run_id,
                "action_run_ids": action_run_ids,
                "offsets": {window.name: window.offset_minutes for window in windows},
                "modes": {window.name: window.mode for window in windows},
                "config_path": args.config,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    write_jsonl(
        scheduler_log,
        {
            "event": "scheduler_start",
            "runtime_run_id": runtime_session.runtime_run_id,
            "runtime_started_at": runtime_session.started_at.isoformat(),
            "runtime_session_file": str(runtime_session.session_file),
            "python_bin": args.python_bin,
            "driver_script": args.driver_script,
            "config": args.config,
            "symbol": args.symbol,
            "qty": args.qty,
            "windows": [
                {
                    "name": window.name,
                    "offset_minutes": window.offset_minutes,
                    "mode": window.mode,
                    "planned_time": (runtime_session.started_at + timedelta(minutes=window.offset_minutes)).isoformat(),
                    "action_run_id": action_run_ids[window.name],
                }
                for window in windows
            ],
            "started_at": scheduler_started_at.isoformat(),
        },
    )

    for window in windows:
        code = run_window(
            args=args,
            runtime_session=runtime_session,
            window=window,
            scheduler_log=scheduler_log,
        )
        if code != 0:
            return code

    write_jsonl(
        scheduler_log,
        {
            "event": "scheduler_complete",
            "completed_at": datetime.now(runtime_session.started_at.tzinfo).isoformat(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
