"""Config-driven rehearsal launcher coverage."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import RuntimeRehearsalSettings
from app.config import load_rehearsal_launch_config
from app.runtime import RunnerMode
from scripts.runtime2_rehearsal import LAUNCHER_FAILURE_EXIT_CODE
from scripts.runtime2_rehearsal import launch_runtime_rehearsal
from scripts.runtime2_rehearsal import main


def _write_launch_config(path: Path, *, mode: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[runtime]",
                f'mode = "{mode}"',
                'cycle_id = "launch-001"',
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
                "bootstrap_from_account_snapshot = true",
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


def test_load_rehearsal_launch_config_parses_explicit_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime2.toml"
    _write_launch_config(config_path, mode="report_only")

    loaded = load_rehearsal_launch_config(config_path)

    assert loaded.mode is RunnerMode.REPORT_ONLY
    assert loaded.instrument_id == "BTC-USDT"
    assert loaded.execution_klines_file == "execution_klines.json"
    assert loaded.bootstrap_from_account_snapshot is True


def test_launcher_mode_routing_report_only(tmp_path: Path) -> None:
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
        command_name="run-report-only",
        confirm_rehearsal_only=True,
    )

    summary = launch_runtime_rehearsal(settings)

    assert summary.runner_name == "ReportOnlyRunner"
    assert summary.success is True
    assert summary.execution_intent_count == 1
    assert (paths["reports_dir"] / "runtime_cycles.jsonl").is_file()


def test_launcher_mode_routing_paper(tmp_path: Path) -> None:
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
        command_name="run-paper",
        confirm_rehearsal_only=True,
    )

    summary = launch_runtime_rehearsal(settings)

    assert summary.runner_name == "PaperRunner"
    assert summary.success is True
    assert summary.final_portfolio_state is not None
    assert (paths["reports_dir"] / "paper_state_transitions.jsonl").is_file()


def test_launcher_mode_routing_restricted_live(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path, mode="restricted_live")
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.RESTRICTED_LIVE,
        venue="binance",
        config_path=paths["config_path"],
        execution_data_path=paths["execution_data"],
        context_data_path=paths["context_data"],
        reports_dir=paths["reports_dir"],
        logs_dir=paths["logs_dir"],
        exchange_mode="restricted_live_rehearsal",
        command_name="run-restricted-live",
        confirm_rehearsal_only=True,
        allow_restricted_live_rehearsal=True,
        confirm_no_order_submission=True,
    )

    summary = launch_runtime_rehearsal(settings)

    assert summary.runner_name == "RestrictedLiveRunner"
    assert summary.success is True
    assert summary.execution_intent_count == 1


def test_shell_wrappers_remain_thin_python_launcher_wrappers() -> None:
    wrappers = {
        "scripts/run_report_only.sh": "run-report-only",
        "scripts/run_paper.sh": "run-paper",
        "scripts/run_restricted_live.sh": "run-restricted-live",
    }

    for script_path, expected_subcommand in wrappers.items():
        payload = Path(script_path).read_text(encoding="utf-8")
        assert 'runtime2_rehearsal.py"' in payload
        assert expected_subcommand in payload


def test_restricted_live_launch_fails_closed_on_config_mode_mismatch(tmp_path: Path, monkeypatch) -> None:
    paths = _prepare_paths(tmp_path, mode="paper")
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_API_SECRET", "secret")

    exit_code = main(
        [
            "run-restricted-live",
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
            "--confirm-rehearsal-only",
            "--allow-restricted-live-rehearsal",
            "--confirm-no-order-submission",
        ]
    )

    assert exit_code == LAUNCHER_FAILURE_EXIT_CODE
