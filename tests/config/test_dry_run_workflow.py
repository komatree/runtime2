"""Dry-run rehearsal workflow coverage."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import RuntimeRehearsalSettings
from app.runtime import RunnerMode
from scripts.dry_run_runtime2 import EXIT_PREFLIGHT_FAILED
from scripts.dry_run_runtime2 import EXIT_SESSION_FAILED
from scripts.dry_run_runtime2 import EXIT_SUCCESS
from scripts.dry_run_runtime2 import main
from scripts.dry_run_runtime2 import run_dry_run_session


def _write_launch_config(path: Path, *, mode: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[runtime]",
                f'mode = "{mode}"',
                'cycle_id = "dry-run-001"',
                'reference_time = "2025-01-02T01:00:00+00:00"',
                'execution_timeframe = "4h"',
                'context_timeframe = "1d"',
                'execution_klines_file = "execution_klines.json"',
                'context_klines_file = "context_klines.json"',
                "",
                "[instrument]",
                'instrument_id = "BTC-USDT"',
                'base_asset = "BTC"',
                'quote_asset = "USDT"',
                "price_precision = 2",
                "quantity_precision = 6",
                "",
                "[portfolio]",
                'cash_quote_asset = "USDT"',
                'initial_cash = "10000"',
                "",
                "[venue_profile]",
                'account_scope = "spot"',
                'maker_fee_bps = "7"',
                'taker_fee_bps = "10"',
                "supports_market_orders = true",
                "supports_post_only = true",
                "",
                "[strategy]",
                'breakout_threshold = "0.02"',
                "include_regime = true",
                "",
                "[binance]",
                'rest_base_url = "https://api.binance.com"',
                'websocket_base_url = "wss://stream.binance.com:9443"',
            ]
        ),
        encoding="utf-8",
    )


def _write_kline_files(execution_dir: Path, context_dir: Path) -> None:
    execution_dir.mkdir(parents=True)
    context_dir.mkdir(parents=True)
    (execution_dir / "execution_klines.json").write_text(
        json.dumps(
            [
                [1735689600000, "100", "103", "99", "101", "10", 1735703999000, "1000", 100],
                [1735704000000, "101", "106", "100", "104", "11", 1735718399000, "1200", 110],
            ]
        ),
        encoding="utf-8",
    )
    (context_dir / "context_klines.json").write_text(
        json.dumps(
            [
                [1735603200000, "95", "105", "90", "100", "100", 1735689599000, "9000", 900],
                [1735689600000, "100", "110", "98", "108", "120", 1735775999000, "10000", 950],
            ]
        ),
        encoding="utf-8",
    )


def _prepare_paths(tmp_path: Path, *, mode: str) -> dict[str, Path]:
    config_path = tmp_path / "runtime2.toml"
    execution_data = tmp_path / "data" / "execution"
    context_data = tmp_path / "data" / "context"
    reports_dir = tmp_path / "reports"
    logs_dir = tmp_path / "logs"
    _write_launch_config(config_path, mode=mode)
    _write_kline_files(execution_data, context_data)
    return {
        "config_path": config_path,
        "execution_data": execution_data,
        "context_data": context_data,
        "reports_dir": reports_dir,
        "logs_dir": logs_dir,
    }


def test_report_only_dry_run_uses_launcher_and_writes_run_directory(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path, mode="report_only")
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.REPORT_ONLY,
        venue="binance",
        config_path=paths["config_path"],
        execution_data_path=paths["execution_data"],
        context_data_path=paths["context_data"],
        reports_dir=paths["reports_dir"],
        logs_dir=paths["logs_dir"],
        exchange_mode="read_only",
        command_name="dry-run",
        confirm_rehearsal_only=True,
    )

    result = run_dry_run_session(settings, run_id="report-only-dry-run")

    assert result.ok is True
    assert result.exit_code == EXIT_SUCCESS
    assert result.preflight_ok is True
    assert result.launch_ok is True
    assert result.launch_summary is not None
    assert result.launch_summary["runner_name"] == "ReportOnlyRunner"
    assert result.launch_summary["cycle_id"] == "dry-run-001"
    expected_files = (
        "rehearsal_run_summaries.jsonl",
        "latest_rehearsal_summary.md",
        "latest_launch_summary.json",
        "latest_launch_summary.md",
        "runtime_cycles.jsonl",
        "runtime_cycle_summaries.jsonl",
        "runtime_health.json",
        "runtime_status.md",
        "run_summary.json",
        "run_summary.md",
        "input_manifest.json",
    )
    for file_name in expected_files:
        assert (result.run_dir / file_name).is_file()
    assert result.logs_dir.is_dir()


def test_paper_dry_run_persists_launcher_outputs_and_paper_artifacts(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path, mode="paper")
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.PAPER,
        venue="binance",
        config_path=paths["config_path"],
        execution_data_path=paths["execution_data"],
        context_data_path=paths["context_data"],
        reports_dir=paths["reports_dir"],
        logs_dir=paths["logs_dir"],
        exchange_mode="paper",
        command_name="dry-run",
        confirm_rehearsal_only=True,
    )

    result = run_dry_run_session(settings, run_id="paper-dry-run")

    assert result.ok is True
    assert result.exit_code == EXIT_SUCCESS
    assert result.launch_summary is not None
    assert result.launch_summary["runner_name"] == "PaperRunner"
    assert result.launch_summary["final_portfolio_state"] is not None
    assert (result.run_dir / "paper_state_transitions.jsonl").is_file()


def test_dry_run_preflight_failure_writes_failure_summary(tmp_path: Path) -> None:
    missing_config = tmp_path / "missing.toml"
    execution_data = tmp_path / "data" / "execution"
    context_data = tmp_path / "data" / "context"
    execution_data.mkdir(parents=True)
    context_data.mkdir(parents=True)
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.REPORT_ONLY,
        venue="binance",
        config_path=missing_config,
        execution_data_path=execution_data,
        context_data_path=context_data,
        reports_dir=tmp_path / "reports",
        logs_dir=tmp_path / "logs",
        exchange_mode="read_only",
        command_name="dry-run",
        confirm_rehearsal_only=True,
    )

    result = run_dry_run_session(settings, run_id="failed-preflight-dry-run")

    assert result.ok is False
    assert result.exit_code == EXIT_PREFLIGHT_FAILED
    payload = json.loads((result.run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert payload["failure_reason"] == "preflight_failed"
    assert payload["launch_summary"] is None


def test_dry_run_launch_failure_reports_launcher_error(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path, mode="paper")
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.REPORT_ONLY,
        venue="binance",
        config_path=paths["config_path"],
        execution_data_path=paths["execution_data"],
        context_data_path=paths["context_data"],
        reports_dir=paths["reports_dir"],
        logs_dir=paths["logs_dir"],
        exchange_mode="read_only",
        command_name="dry-run",
        confirm_rehearsal_only=True,
    )

    result = run_dry_run_session(settings, run_id="failed-launch-dry-run")

    assert result.ok is False
    assert result.exit_code == EXIT_SESSION_FAILED
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("launch_exception:")
    assert result.launch_summary is None


def test_dry_run_main_supports_restricted_live_only_with_explicit_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _prepare_paths(tmp_path, mode="restricted_live")
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret")

    exit_code = main(
        [
            "--mode",
            "restricted_live",
            "--config",
            str(paths["config_path"]),
            "--execution-data",
            str(paths["execution_data"]),
            "--context-data",
            str(paths["context_data"]),
            "--reports-dir",
            str(paths["reports_dir"]),
            "--logs-dir",
            str(paths["logs_dir"]),
            "--exchange-mode",
            "restricted_live_rehearsal",
            "--run-id",
            "restricted-live-dry-run",
            "--confirm-rehearsal-only",
            "--allow-restricted-live-rehearsal",
            "--confirm-no-order-submission",
        ]
    )

    assert exit_code == EXIT_SUCCESS
    summary_path = (
        paths["reports_dir"]
        / "dry_runs"
        / "restricted-live-dry-run"
        / "run_summary.json"
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["launch_summary"]["runner_name"] == "RestrictedLiveRunner"
