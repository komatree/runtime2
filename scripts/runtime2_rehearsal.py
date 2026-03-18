#!/usr/bin/env python3
"""Runtime2 rehearsal command helper."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import RehearsalLaunchConfig
from app.config import RuntimeRehearsalSettings
from app.config import RuntimeLaunchSummary
from app.config import append_launch_summary
from app.config import append_run_summary
from app.config import build_run_summary
from app.config import load_rehearsal_launch_config
from app.config import validate_runtime_rehearsal
from app.config import write_latest_launch_summary_markdown
from app.config import write_latest_run_summary_markdown
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceMarketDataClient
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import IndexSuiteFeatureService
from app.features.stablecoin import StablecoinFeatureService
from app.monitoring import FileRuntimeStatusGateway
from app.risk import ReportOnlyRiskEvaluator
from app.portfolio import build_portfolio_baseline_from_account_snapshot
from app.runtime import PaperRunner
from app.runtime import ReportOnlyRunner
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.runtime import RuntimeFeatureBuilder
from app.storage import JsonlPaperStatePersistenceGateway
from app.storage import JsonlReportPersistenceGateway
from app.strategies.breakout import BreakoutStrategy
from app.strategies.regime import RegimeStrategy
from app.strategies.router import StrategyRouter


LAUNCHER_FAILURE_EXIT_CODE = 2


@dataclass(frozen=True)
class PreparedRuntimeRehearsal:
    """Prepared launcher components for one config-driven rehearsal path."""

    launch_config: RehearsalLaunchConfig
    runtime_context: RuntimeContext
    instrument: Instrument
    portfolio_state: PortfolioState
    market_context: object


def build_parser() -> argparse.ArgumentParser:
    """Build the shared CLI parser for rehearsal commands."""

    parser = argparse.ArgumentParser(description="runtime2 rehearsal helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="validate environment only")
    preflight.add_argument("--mode", choices=[mode.value for mode in RunnerMode], required=True)
    _add_common_arguments(preflight)

    report_only = subparsers.add_parser("run-report-only", help="run report-only rehearsal preflight")
    _add_common_arguments(report_only, fixed_mode=RunnerMode.REPORT_ONLY)

    paper = subparsers.add_parser("run-paper", help="run paper rehearsal preflight")
    _add_common_arguments(paper, fixed_mode=RunnerMode.PAPER)

    restricted_live = subparsers.add_parser(
        "run-restricted-live",
        help="run restricted-live rehearsal preflight with safety confirmations",
    )
    _add_common_arguments(restricted_live, fixed_mode=RunnerMode.RESTRICTED_LIVE)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser, *, fixed_mode: RunnerMode | None = None) -> None:
    if fixed_mode is not None:
        parser.set_defaults(mode=fixed_mode.value)
    parser.add_argument("--venue", default="binance")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execution-data", required=True, type=Path)
    parser.add_argument("--context-data", required=True, type=Path)
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument("--logs-dir", required=True, type=Path)
    parser.add_argument("--exchange-mode", required=True)
    parser.add_argument(
        "--allow-order-submission",
        action="store_true",
        help="Unsafe flag that remains rejected by validation.",
    )
    parser.add_argument(
        "--confirm-rehearsal-only",
        action="store_true",
        help="Required for run commands to confirm this path must remain rehearsal-only.",
    )
    parser.add_argument(
        "--allow-restricted-live-rehearsal",
        action="store_true",
        help="Required only for restricted-live rehearsal.",
    )
    parser.add_argument(
        "--confirm-no-order-submission",
        action="store_true",
        help="Required only for restricted-live rehearsal.",
    )


def settings_from_args(args: argparse.Namespace) -> RuntimeRehearsalSettings:
    """Convert parsed CLI arguments into validated settings."""

    return RuntimeRehearsalSettings(
        mode=RunnerMode(args.mode),
        venue=args.venue,
        config_path=args.config,
        execution_data_path=args.execution_data,
        context_data_path=args.context_data,
        reports_dir=args.reports_dir,
        logs_dir=args.logs_dir,
        exchange_mode=args.exchange_mode,
        command_name=args.command,
        allow_order_submission=args.allow_order_submission,
        confirm_rehearsal_only=args.confirm_rehearsal_only,
        allow_restricted_live_rehearsal=args.allow_restricted_live_rehearsal,
        confirm_no_order_submission=args.confirm_no_order_submission,
    )


def _print_summary(summary_path: Path, summary) -> None:
    print(f"mode: {summary.mode}")
    print(f"preflight_ok: {summary.preflight_ok}")
    print(f"summary_path: {summary_path}")
    for check in summary.checks:
        print(f"check: {check}")
    for warning in summary.warnings:
        print(f"warning: {warning}")
    for error in summary.errors:
        print(f"error: {error}")


def _load_kline_rows(path: Path) -> tuple[tuple[object, ...], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"kline file must contain a JSON list: {path}")
    rows: list[tuple[object, ...]] = []
    for row in payload:
        if not isinstance(row, list):
            raise ValueError(f"kline row must be a JSON array: {path}")
        rows.append(tuple(row))
    return tuple(rows)


def _build_instrument(config: RehearsalLaunchConfig) -> Instrument:
    return Instrument(
        instrument_id=config.instrument_id,
        base_asset=config.base_asset,
        quote_asset=config.quote_asset,
        price_precision=config.price_precision,
        quantity_precision=config.quantity_precision,
    )


def _build_portfolio_state(config: RehearsalLaunchConfig) -> PortfolioState:
    return PortfolioState(
        as_of=config.reference_time,
        cash_by_asset={config.cash_quote_asset: config.initial_cash},
        position_qty_by_instrument={config.instrument_id: Decimal("0")},
        average_entry_price_by_instrument={config.instrument_id: Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def build_portfolio_state_from_account_snapshot(
    config: RehearsalLaunchConfig,
    snapshot,
) -> PortfolioState:
    """Return an explicit restricted-live bootstrap portfolio from a live account snapshot."""

    return build_portfolio_baseline_from_account_snapshot(
        snapshot=snapshot,
        instrument_id=config.instrument_id,
        base_asset=config.base_asset,
        quote_asset=config.quote_asset,
    )


def _build_venue_profile(config: RehearsalLaunchConfig) -> VenueProfile:
    return VenueProfile(
        venue="binance",
        account_scope=config.account_scope,
        maker_fee_bps=config.maker_fee_bps,
        taker_fee_bps=config.taker_fee_bps,
        supports_market_orders=config.supports_market_orders,
        supports_post_only=config.supports_post_only,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    )


def _build_strategy_router(config: RehearsalLaunchConfig) -> StrategyRouter:
    strategies = [BreakoutStrategy(breakout_threshold=config.breakout_threshold)]
    if config.include_regime:
        strategies.append(RegimeStrategy())
    return StrategyRouter(strategies=tuple(strategies))


def _build_runtime_context(
    settings: RuntimeRehearsalSettings,
    launch_config: RehearsalLaunchConfig,
) -> RuntimeContext:
    status_gateway = FileRuntimeStatusGateway(
        summary_output_path=settings.reports_dir / "runtime_cycle_summaries.jsonl",
        health_output_path=settings.reports_dir / "runtime_health.json",
        operator_report_path=settings.reports_dir / "runtime_status.md",
    )
    persistence_gateway = JsonlReportPersistenceGateway(
        output_path=settings.reports_dir / "runtime_cycles.jsonl",
        status_gateway=status_gateway,
        mode=settings.mode.value,
    )
    return RuntimeContext(
        mode=settings.mode,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
        ),
        strategy_evaluator=_build_strategy_router(launch_config),
        risk_evaluator=ReportOnlyRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence_gateway,
        venue_profile=_build_venue_profile(launch_config),
        execution_venue="binance",
    )


def _load_market_context(
    settings: RuntimeRehearsalSettings,
    launch_config: RehearsalLaunchConfig,
):
    market_data_client = BinanceMarketDataClient(
        config=BinanceAdapterConfig(
            rest_base_url=launch_config.binance_rest_base_url,
            websocket_base_url=launch_config.binance_websocket_base_url,
            api_key="configured" if settings.mode is RunnerMode.RESTRICTED_LIVE else "",
            api_secret="configured" if settings.mode is RunnerMode.RESTRICTED_LIVE else "",
            endpoint_profile_name=launch_config.binance_endpoint_profile_name,
        )
    )
    execution_rows = _load_kline_rows(settings.execution_data_path / launch_config.execution_klines_file)
    context_rows = _load_kline_rows(settings.context_data_path / launch_config.context_klines_file)
    return market_data_client.build_report_only_market_context(
        instrument_id=launch_config.instrument_id,
        execution_timeframe=launch_config.execution_timeframe,
        context_timeframe=launch_config.context_timeframe,
        execution_klines=execution_rows,
        context_klines=context_rows,
        reference_time=launch_config.reference_time,
    )


def _validate_launch_config_against_settings(
    settings: RuntimeRehearsalSettings,
    launch_config: RehearsalLaunchConfig,
) -> None:
    if launch_config.mode is not settings.mode:
        raise ValueError(
            f"config mode {launch_config.mode.value} does not match launch mode {settings.mode.value}"
        )


def prepare_runtime_rehearsal(settings: RuntimeRehearsalSettings) -> PreparedRuntimeRehearsal:
    """Load config and construct the runtime objects used by the launcher."""

    launch_config = load_rehearsal_launch_config(settings.config_path)
    _validate_launch_config_against_settings(settings, launch_config)
    return PreparedRuntimeRehearsal(
        launch_config=launch_config,
        runtime_context=_build_runtime_context(settings, launch_config),
        instrument=_build_instrument(launch_config),
        portfolio_state=_build_portfolio_state(launch_config),
        market_context=_load_market_context(settings, launch_config),
    )


def launch_runtime_rehearsal(settings: RuntimeRehearsalSettings) -> RuntimeLaunchSummary:
    """Load config, construct runtime context, and invoke the selected runner."""

    prepared = prepare_runtime_rehearsal(settings)
    launch_config = prepared.launch_config
    runtime_context = prepared.runtime_context
    instrument = prepared.instrument
    portfolio_state = prepared.portfolio_state
    market_context = prepared.market_context

    if settings.mode is RunnerMode.REPORT_ONLY:
        runner = ReportOnlyRunner(runtime_context)
        cycle_result = runner.run_cycle(
            cycle_id=launch_config.cycle_id,
            instrument=instrument,
            bar_slice=market_context.execution_bar_slice,
            context_bar_slice=market_context.context_bar_slice,
            portfolio_state=portfolio_state,
        )
        return RuntimeLaunchSummary(
            recorded_at=datetime.now(UTC),
            mode=settings.mode.value,
            runner_name="ReportOnlyRunner",
            cycle_id=cycle_result.cycle_id,
            instrument_id=instrument.instrument_id,
            success=cycle_result.success,
            signal_count=len(cycle_result.signals),
            risk_decision_count=len(cycle_result.risk_decisions),
            execution_intent_count=len(cycle_result.execution_intents),
            alerts=cycle_result.alerts,
            output_path=str(settings.reports_dir / "runtime_cycles.jsonl"),
        )

    if settings.mode is RunnerMode.PAPER:
        runner = PaperRunner(
            context=runtime_context,
            state_persistence_gateway=JsonlPaperStatePersistenceGateway(
                output_path=settings.reports_dir / "paper_state_transitions.jsonl",
                summary_output_path=settings.reports_dir / "paper_session_summaries.jsonl",
            ),
        )
        outcome = runner.run_cycle(
            cycle_id=launch_config.cycle_id,
            instrument=instrument,
            bar_slice=market_context.execution_bar_slice,
            context_bar_slice=market_context.context_bar_slice,
            portfolio_state=portfolio_state,
        )
        return RuntimeLaunchSummary(
            recorded_at=datetime.now(UTC),
            mode=settings.mode.value,
            runner_name="PaperRunner",
            cycle_id=outcome.cycle_result.cycle_id,
            instrument_id=instrument.instrument_id,
            success=outcome.cycle_result.success,
            signal_count=len(outcome.cycle_result.signals),
            risk_decision_count=len(outcome.cycle_result.risk_decisions),
            execution_intent_count=len(outcome.cycle_result.execution_intents),
            alerts=outcome.cycle_result.alerts,
            output_path=str(settings.reports_dir / "paper_state_transitions.jsonl"),
            final_portfolio_state=asdict(outcome.ending_portfolio_state),
        )

    runner = RestrictedLiveRunner(runtime_context)
    cycle_result = runner.run_cycle(
        cycle_id=launch_config.cycle_id,
        instrument=instrument,
        bar_slice=market_context.execution_bar_slice,
        context_bar_slice=market_context.context_bar_slice,
        portfolio_state=portfolio_state,
    )
    return RuntimeLaunchSummary(
        recorded_at=datetime.now(UTC),
        mode=settings.mode.value,
        runner_name="RestrictedLiveRunner",
        cycle_id=cycle_result.cycle_id,
        instrument_id=instrument.instrument_id,
        success=cycle_result.success,
        signal_count=len(cycle_result.signals),
        risk_decision_count=len(cycle_result.risk_decisions),
        execution_intent_count=len(cycle_result.execution_intents),
        alerts=cycle_result.alerts,
        output_path=str(settings.reports_dir / "runtime_cycles.jsonl"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = settings_from_args(args)
    preflight = validate_runtime_rehearsal(settings)
    summary = build_run_summary(settings, preflight=preflight)
    summary_path = append_run_summary(summary, output_dir=settings.reports_dir)
    markdown_path = write_latest_run_summary_markdown(summary, output_dir=settings.reports_dir)
    _print_summary(summary_path, summary)
    print(f"latest_summary_markdown: {markdown_path}")

    if not preflight.ok:
        return 1

    if args.command == "preflight":
        return 0

    try:
        launch_summary = launch_runtime_rehearsal(settings)
    except Exception as exc:
        print(f"launch_error: {exc}")
        return LAUNCHER_FAILURE_EXIT_CODE

    launch_json_path = append_launch_summary(launch_summary, output_dir=settings.reports_dir)
    launch_markdown_path = write_latest_launch_summary_markdown(launch_summary, output_dir=settings.reports_dir)
    print(f"launch_summary_json: {launch_json_path}")
    print(f"launch_summary_markdown: {launch_markdown_path}")
    print(f"runner_name: {launch_summary.runner_name}")
    print(f"cycle_id: {launch_summary.cycle_id}")
    print(f"launch_success: {launch_summary.success}")
    print("rehearsal launcher completed")
    print("note: unrestricted exchange order submission remains blocked")
    return 0 if launch_summary.success else LAUNCHER_FAILURE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
