"""Rehearsal validation coverage for runtime2 scripts and safety gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import RuntimeRehearsalSettings
from app.config import append_run_summary
from app.config import build_run_summary
from app.config import validate_runtime_rehearsal
from app.config import write_latest_run_summary_markdown
from app.runtime import RunnerMode
from scripts.runtime2_rehearsal import build_parser
from scripts.runtime2_rehearsal import main
from scripts.runtime2_rehearsal import settings_from_args


def _prepare_paths(tmp_path: Path) -> dict[str, Path]:
    config_path = tmp_path / "runtime2.toml"
    execution_data = tmp_path / "data" / "execution"
    context_data = tmp_path / "data" / "context"
    reports_dir = tmp_path / "reports"
    logs_dir = tmp_path / "logs"
    config_path.write_text("mode = 'stub'\n", encoding="utf-8")
    execution_data.mkdir(parents=True)
    context_data.mkdir(parents=True)
    return {
        "config_path": config_path,
        "execution_data": execution_data,
        "context_data": context_data,
        "reports_dir": reports_dir,
        "logs_dir": logs_dir,
    }


def test_config_validation_report_only_allows_missing_optional_credentials(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.REPORT_ONLY,
        venue="binance",
        config_path=paths["config_path"],
        execution_data_path=paths["execution_data"],
        context_data_path=paths["context_data"],
        reports_dir=paths["reports_dir"],
        logs_dir=paths["logs_dir"],
        exchange_mode="read_only",
    )

    result = validate_runtime_rehearsal(settings, environ={})

    assert result.ok is True
    assert "optional Binance credentials missing: BINANCE_API_KEY, BINANCE_API_SECRET" in result.warnings


def test_script_argument_sanity_for_report_only_subcommand(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
    parser = build_parser()

    args = parser.parse_args(
        [
            "run-report-only",
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
            "read_only",
            "--confirm-rehearsal-only",
        ]
    )

    settings = settings_from_args(args)

    assert settings.mode is RunnerMode.REPORT_ONLY
    assert settings.exchange_mode == "read_only"
    assert settings.allow_order_submission is False
    assert settings.confirm_rehearsal_only is True


def test_run_commands_require_rehearsal_only_confirmation(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
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
    )

    result = validate_runtime_rehearsal(settings, environ={})

    assert result.ok is False
    assert "run commands require --confirm-rehearsal-only" in result.errors


def test_restricted_live_safety_flags_fail_closed_when_missing(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
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
    )

    result = validate_runtime_rehearsal(
        settings,
        environ={"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"},
    )

    assert result.ok is False
    assert "restricted-live requires --allow-restricted-live-rehearsal" in result.errors
    assert "restricted-live requires --confirm-no-order-submission" in result.errors


def test_restricted_live_summary_is_persisted_when_preflight_passes(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
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

    result = validate_runtime_rehearsal(
        settings,
        environ={"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"},
    )
    summary = build_run_summary(settings, preflight=result)
    output_path = append_run_summary(summary, output_dir=paths["reports_dir"])

    assert result.ok is True
    line = output_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["mode"] == "restricted_live"
    assert payload["preflight_ok"] is True
    assert payload["order_submission_enabled"] is False
    markdown_path = write_latest_run_summary_markdown(summary, output_dir=paths["reports_dir"])
    assert markdown_path.read_text(encoding="utf-8").startswith("# Rehearsal Summary")


def test_restricted_live_rejects_order_submission_flag(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)
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
        allow_order_submission=True,
        allow_restricted_live_rehearsal=True,
        confirm_no_order_submission=True,
    )

    result = validate_runtime_rehearsal(
        settings,
        environ={"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"},
    )

    assert result.ok is False
    assert "order submission must remain disabled in rehearsal scripts" in result.errors


def test_restricted_live_main_fails_closed_without_required_flags(tmp_path: Path) -> None:
    paths = _prepare_paths(tmp_path)

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
        ]
    )

    assert exit_code == 1
