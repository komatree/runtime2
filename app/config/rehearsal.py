"""Restricted-live rehearsal configuration, validation, and launch config loading."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.runtime import RunnerMode


BINANCE_CREDENTIAL_ENV_VARS = ("BINANCE_API_KEY", "BINANCE_API_SECRET")


@dataclass(frozen=True)
class RuntimeRehearsalSettings:
    """Static inputs for a rehearsal or preflight invocation.

    Invariants:
    - `venue` stays phase-1 constrained to `binance`.
    - `allow_order_submission` must remain false for all current modes.
    - restricted-live requires explicit safety flags and rehearsal exchange mode.
    """

    mode: RunnerMode
    venue: str
    config_path: Path
    execution_data_path: Path
    context_data_path: Path
    reports_dir: Path
    logs_dir: Path
    exchange_mode: str
    command_name: str = "preflight"
    allow_order_submission: bool = False
    confirm_rehearsal_only: bool = False
    allow_restricted_live_rehearsal: bool = False
    confirm_no_order_submission: bool = False


@dataclass(frozen=True)
class RuntimePreflightResult:
    """Outcome of environment validation before any rehearsal entrypoint runs."""

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeRunSummary:
    """Structured operator-facing summary for a rehearsal invocation."""

    recorded_at: datetime
    mode: str
    venue: str
    exchange_mode: str
    config_path: str
    execution_data_path: str
    context_data_path: str
    reports_dir: str
    logs_dir: str
    preflight_ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: tuple[str, ...]
    order_submission_enabled: bool
    command_name: str


@dataclass(frozen=True)
class RehearsalLaunchConfig:
    """Config-driven runtime launch inputs loaded from TOML.

    This config is explicit on purpose. The launcher should not infer mode,
    instrument, or data-file locations from shell wrapper names alone.
    """

    mode: RunnerMode
    cycle_id: str
    reference_time: datetime
    execution_timeframe: str
    context_timeframe: str
    execution_klines_file: str
    context_klines_file: str
    instrument_id: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    cash_quote_asset: str
    initial_cash: Decimal
    bootstrap_from_account_snapshot: bool
    maker_fee_bps: Decimal
    taker_fee_bps: Decimal
    account_scope: str
    supports_market_orders: bool
    supports_post_only: bool
    breakout_threshold: Decimal
    include_regime: bool
    binance_endpoint_profile_name: str
    binance_rest_base_url: str
    binance_websocket_base_url: str


@dataclass(frozen=True)
class RuntimeLaunchSummary:
    """Operator-facing result of an actual launcher invocation."""

    recorded_at: datetime
    mode: str
    runner_name: str
    cycle_id: str
    instrument_id: str
    success: bool
    signal_count: int
    risk_decision_count: int
    execution_intent_count: int
    alerts: tuple[str, ...]
    output_path: str
    final_portfolio_state: dict[str, Any] | None = None


def validate_runtime_rehearsal(
    settings: RuntimeRehearsalSettings,
    *,
    environ: dict[str, str] | None = None,
) -> RuntimePreflightResult:
    """Validate mode-specific runtime conditions conservatively.

    The validator fails closed on missing required inputs and on any
    restricted-live safety violation.
    """

    env = dict(os.environ if environ is None else environ)
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    if settings.venue != "binance":
        errors.append("phase-1 rehearsal supports venue=binance only")
    else:
        checks.append("venue restricted to binance")

    if not settings.config_path.is_file():
        errors.append(f"config path missing: {settings.config_path}")
    else:
        checks.append("config path present")

    if not settings.execution_data_path.is_dir():
        errors.append(f"execution data path missing: {settings.execution_data_path}")
    else:
        checks.append("execution data path present")

    if not settings.context_data_path.is_dir():
        errors.append(f"context data path missing: {settings.context_data_path}")
    else:
        checks.append("context data path present")

    writable_checks = (
        ("reports", settings.reports_dir),
        ("logs", settings.logs_dir),
    )
    for label, path in writable_checks:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks.append(f"{label} path writable")
        except OSError as exc:
            errors.append(f"{label} path not writable: {path} ({exc})")

    credentials_present = all(env.get(var) for var in BINANCE_CREDENTIAL_ENV_VARS)
    if settings.mode is RunnerMode.RESTRICTED_LIVE:
        if not credentials_present:
            errors.append("restricted-live requires Binance credentials")
        else:
            checks.append("Binance credentials present")
    elif credentials_present:
        checks.append("optional Binance credentials present")
    else:
        warnings.append(f"optional Binance credentials missing: {', '.join(BINANCE_CREDENTIAL_ENV_VARS)}")

    expected_exchange_mode = {
        RunnerMode.REPORT_ONLY: "read_only",
        RunnerMode.PAPER: "paper",
        RunnerMode.RESTRICTED_LIVE: "restricted_live_rehearsal",
    }[settings.mode]
    if settings.exchange_mode != expected_exchange_mode:
        errors.append(
            f"{settings.mode.value} requires exchange_mode={expected_exchange_mode}, "
            f"got {settings.exchange_mode}"
        )
    else:
        checks.append(f"exchange mode locked to {expected_exchange_mode}")

    if settings.allow_order_submission:
        errors.append("order submission must remain disabled in rehearsal scripts")
    else:
        checks.append("order submission disabled")

    if settings.command_name != "preflight":
        if not settings.confirm_rehearsal_only:
            errors.append("run commands require --confirm-rehearsal-only")
        else:
            checks.append("rehearsal-only confirmation present")

    if settings.mode is RunnerMode.RESTRICTED_LIVE:
        if not settings.allow_restricted_live_rehearsal:
            errors.append("restricted-live requires --allow-restricted-live-rehearsal")
        else:
            checks.append("restricted-live safety enable flag present")
        if not settings.confirm_no_order_submission:
            errors.append("restricted-live requires --confirm-no-order-submission")
        else:
            checks.append("restricted-live no-order-submission confirmation present")

    return RuntimePreflightResult(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        checks=tuple(checks),
    )


def build_run_summary(
    settings: RuntimeRehearsalSettings,
    *,
    preflight: RuntimePreflightResult,
) -> RuntimeRunSummary:
    """Build a deterministic structured summary for operator review."""

    return RuntimeRunSummary(
        recorded_at=datetime.now(UTC),
        mode=settings.mode.value,
        venue=settings.venue,
        exchange_mode=settings.exchange_mode,
        config_path=str(settings.config_path),
        execution_data_path=str(settings.execution_data_path),
        context_data_path=str(settings.context_data_path),
        reports_dir=str(settings.reports_dir),
        logs_dir=str(settings.logs_dir),
        preflight_ok=preflight.ok,
        errors=preflight.errors,
        warnings=preflight.warnings,
        checks=preflight.checks,
        order_submission_enabled=settings.allow_order_submission,
        command_name=settings.command_name,
    )


def append_run_summary(summary: RuntimeRunSummary, *, output_dir: Path) -> Path:
    """Append the structured rehearsal summary as JSONL for auditability."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "rehearsal_run_summaries.jsonl"
    record = asdict(summary)
    record["recorded_at"] = summary.recorded_at.isoformat()
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")
    return output_path


def write_latest_run_summary_markdown(summary: RuntimeRunSummary, *, output_dir: Path) -> Path:
    """Write an operator-friendly latest rehearsal summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest_rehearsal_summary.md"
    checks = "\n".join(f"- {item}" for item in summary.checks) or "- none"
    warnings = "\n".join(f"- {item}" for item in summary.warnings) or "- none"
    errors = "\n".join(f"- {item}" for item in summary.errors) or "- none"
    output_path.write_text(
        "\n".join(
            [
                "# Rehearsal Summary",
                f"- command: {summary.command_name}",
                f"- mode: {summary.mode}",
                f"- venue: {summary.venue}",
                f"- exchange_mode: {summary.exchange_mode}",
                f"- preflight_ok: {summary.preflight_ok}",
                f"- config_path: {summary.config_path}",
                f"- execution_data_path: {summary.execution_data_path}",
                f"- context_data_path: {summary.context_data_path}",
                f"- reports_dir: {summary.reports_dir}",
                f"- logs_dir: {summary.logs_dir}",
                f"- order_submission_enabled: {summary.order_submission_enabled}",
                "",
                "## Checks",
                checks,
                "",
                "## Warnings",
                warnings,
                "",
                "## Errors",
                errors,
            ]
        ),
        encoding="utf-8",
    )
    return output_path


def load_rehearsal_launch_config(config_path: Path) -> RehearsalLaunchConfig:
    """Load the explicit runtime launch config from TOML."""

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    runtime = raw["runtime"]
    instrument = raw["instrument"]
    portfolio = raw["portfolio"]
    venue_profile = raw["venue_profile"]
    strategy = raw.get("strategy", {})
    binance = raw.get("binance", {})

    return RehearsalLaunchConfig(
        mode=RunnerMode(runtime["mode"]),
        cycle_id=str(runtime["cycle_id"]),
        reference_time=datetime.fromisoformat(str(runtime["reference_time"])),
        execution_timeframe=str(runtime["execution_timeframe"]),
        context_timeframe=str(runtime["context_timeframe"]),
        execution_klines_file=str(runtime["execution_klines_file"]),
        context_klines_file=str(runtime["context_klines_file"]),
        instrument_id=str(instrument["instrument_id"]),
        base_asset=str(instrument["base_asset"]),
        quote_asset=str(instrument["quote_asset"]),
        price_precision=int(instrument["price_precision"]),
        quantity_precision=int(instrument["quantity_precision"]),
        cash_quote_asset=str(portfolio.get("cash_quote_asset", instrument["quote_asset"])),
        initial_cash=Decimal(str(portfolio["initial_cash"])),
        bootstrap_from_account_snapshot=bool(portfolio.get("bootstrap_from_account_snapshot", False)),
        maker_fee_bps=Decimal(str(venue_profile["maker_fee_bps"])),
        taker_fee_bps=Decimal(str(venue_profile["taker_fee_bps"])),
        account_scope=str(venue_profile.get("account_scope", "spot")),
        supports_market_orders=bool(venue_profile.get("supports_market_orders", True)),
        supports_post_only=bool(venue_profile.get("supports_post_only", True)),
        breakout_threshold=Decimal(str(strategy.get("breakout_threshold", "0.02"))),
        include_regime=bool(strategy.get("include_regime", True)),
        binance_endpoint_profile_name=str(binance.get("endpoint_profile_name", "binance_spot_prod")),
        binance_rest_base_url=str(binance.get("rest_base_url", "https://api.binance.com")),
        binance_websocket_base_url=str(binance.get("websocket_base_url", "wss://stream.binance.com:9443")),
    )


def append_launch_summary(summary: RuntimeLaunchSummary, *, output_dir: Path) -> Path:
    """Write the latest machine-readable launch result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest_launch_summary.json"
    output_path.write_text(
        json.dumps(asdict(summary), default=_json_default, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return output_path


def write_latest_launch_summary_markdown(summary: RuntimeLaunchSummary, *, output_dir: Path) -> Path:
    """Write the latest operator-facing launch result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "latest_launch_summary.md"
    alerts = "\n".join(f"- {item}" for item in summary.alerts) or "- none"
    final_portfolio = (
        json.dumps(summary.final_portfolio_state, default=_json_default, sort_keys=True)
        if summary.final_portfolio_state is not None
        else "none"
    )
    output_path.write_text(
        "\n".join(
            [
                "# Launch Summary",
                f"- mode: {summary.mode}",
                f"- runner: {summary.runner_name}",
                f"- cycle_id: {summary.cycle_id}",
                f"- instrument_id: {summary.instrument_id}",
                f"- success: {summary.success}",
                f"- signal_count: {summary.signal_count}",
                f"- risk_decision_count: {summary.risk_decision_count}",
                f"- execution_intent_count: {summary.execution_intent_count}",
                f"- output_path: {summary.output_path}",
                f"- final_portfolio_state: {final_portfolio}",
                "",
                "## Alerts",
                alerts,
            ]
        ),
        encoding="utf-8",
    )
    return output_path


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
