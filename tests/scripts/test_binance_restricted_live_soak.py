from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


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


def test_write_finalization_debug_marker_records_phase_and_status(tmp_path: Path) -> None:
    module = _load_soak_module()

    path = module._write_finalization_debug_marker(
        run_dir=tmp_path,
        phase="artifact_writer.persist",
        status="started",
        extra={"completed_cycles": 12},
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path == tmp_path / module.FINALIZATION_DEBUG_FILENAME
    assert payload["phase"] == "artifact_writer.persist"
    assert payload["status"] == "started"
    assert payload["completed_cycles"] == 12
    assert "recorded_at" in payload


def test_write_finalization_debug_marker_records_exception_details(tmp_path: Path) -> None:
    module = _load_soak_module()

    try:
        raise RuntimeError("persist exploded")
    except RuntimeError as exc:
        path = module._write_finalization_debug_marker(
            run_dir=tmp_path,
            phase="artifact_writer.persist",
            status="failed",
            exception=exc,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["phase"] == "artifact_writer.persist"
    assert payload["status"] == "failed"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception_message"] == "persist exploded"
    assert "RuntimeError: persist exploded" in payload["traceback"]
