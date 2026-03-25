#!/usr/bin/env python3
"""Long-running restricted-live Binance soak workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import RuntimeRehearsalSettings
from app.config import append_run_summary
from app.config import build_run_summary
from app.config import validate_runtime_rehearsal
from app.config import write_latest_run_summary_markdown
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceClockSync
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateUserDataTransport
from app.exchanges.binance import BinanceReconciliationService
from app.exchanges.binance import BinanceRequestWeightTracker
from app.exchanges.binance import BinanceRestrictedLivePayloadSource
from app.exchanges.binance import BinanceRestrictedLivePortfolioGate
from app.exchanges.binance import BinanceSignedRestAccountSnapshotBootstrap
from app.exchanges.binance import BinanceSignedRestOrderStatusTransport
from app.exchanges.binance import BinanceSymbolMapping
from app.monitoring import BinanceExchangeHealthService
from app.monitoring import RecordingRestrictedLiveGate
from app.monitoring import RestrictedLiveSoakArtifactWriter
from app.monitoring import RestrictedLiveSoakExchangeHealthProvider
from app.monitoring import RestrictedLiveSoakReportingService
from app.monitoring import RestrictedLiveSoakRunner
from app.monitoring import RestrictedLiveSoakStopCriteria
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from scripts.runtime2_rehearsal import build_portfolio_state_from_account_snapshot
from scripts.runtime2_rehearsal import prepare_runtime_rehearsal


SOAK_ABORT_EXIT_CODE = 2
FINALIZATION_DEBUG_FILENAME = "finalization_debug.json"


def _venue_symbol(instrument_id: str) -> str:
    return instrument_id.replace("-", "")


def _write_runtime_session_metadata(
    *,
    path: Path,
    run_id: str,
    exchange_mode: str,
    started_at: datetime,
    config_path: Path,
    reports_dir: Path,
    logs_dir: Path,
    instrument_id: str,
    output_subdir: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "runtime_run_id": run_id,
                "exchange_mode": exchange_mode,
                "started_at": started_at.isoformat(),
                "config_path": str(config_path),
                "reports_dir": str(reports_dir),
                "logs_dir": str(logs_dir),
                "instrument_id": instrument_id,
                "output_subdir": output_subdir,
                "session_state": "started",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _finalization_debug_path(run_dir: Path) -> Path:
    return run_dir / FINALIZATION_DEBUG_FILENAME


def _write_finalization_debug_marker(
    *,
    run_dir: Path,
    phase: str,
    status: str,
    exception: BaseException | None = None,
    extra: dict[str, object] | None = None,
) -> Path:
    path = _finalization_debug_path(run_dir)
    payload: dict[str, object] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "phase": phase,
        "status": status,
    }
    if extra:
        payload.update(extra)
    if exception is not None:
        payload["exception_type"] = type(exception).__name__
        payload["exception_message"] = str(exception)
        payload["traceback"] = "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _report_finalization_exception(*, phase: str, debug_path: Path, exception: BaseException) -> None:
    print(
        (
            "restricted-live soak finalization failure: "
            f"phase={phase} debug_marker={debug_path}"
        ),
        file=sys.stderr,
    )
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="restricted-live Binance soak runner")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execution-data", required=True, type=Path)
    parser.add_argument("--context-data", required=True, type=Path)
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument("--logs-dir", required=True, type=Path)
    parser.add_argument("--exchange-mode", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--duration-hours", type=int)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.0)
    parser.add_argument("--output-subdir", default="restricted_live_soaks")
    parser.add_argument("--max-blocked-mutations", type=int, default=3)
    parser.add_argument("--confirm-rehearsal-only", action="store_true")
    parser.add_argument("--allow-restricted-live-rehearsal", action="store_true")
    parser.add_argument("--confirm-no-order-submission", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = args.reports_dir / args.output_subdir / args.run_id
    log_dir = args.logs_dir / args.output_subdir / args.run_id
    started_at = datetime.now(UTC).astimezone()
    settings = RuntimeRehearsalSettings(
        mode=RunnerMode.RESTRICTED_LIVE,
        venue="binance",
        config_path=args.config,
        execution_data_path=args.execution_data,
        context_data_path=args.context_data,
        reports_dir=run_dir,
        logs_dir=log_dir,
        exchange_mode=args.exchange_mode,
        command_name="run-restricted-live-soak",
        confirm_rehearsal_only=args.confirm_rehearsal_only,
        allow_restricted_live_rehearsal=args.allow_restricted_live_rehearsal,
        confirm_no_order_submission=args.confirm_no_order_submission,
    )
    preflight = validate_runtime_rehearsal(settings, environ=dict(os.environ))
    summary = build_run_summary(settings, preflight=preflight)
    append_run_summary(summary, output_dir=run_dir)
    write_latest_run_summary_markdown(summary, output_dir=run_dir)
    if not preflight.ok:
        return 1

    prepared = prepare_runtime_rehearsal(settings)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_session_metadata(
        path=run_dir / "runtime_session.json",
        run_id=args.run_id,
        exchange_mode=args.exchange_mode,
        started_at=started_at,
        config_path=args.config,
        reports_dir=run_dir,
        logs_dir=log_dir,
        instrument_id=prepared.launch_config.instrument_id,
        output_subdir=args.output_subdir,
    )
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    adapter_config = BinanceAdapterConfig(
        rest_base_url=prepared.launch_config.binance_rest_base_url,
        websocket_base_url=prepared.launch_config.binance_websocket_base_url,
        api_key=api_key,
        api_secret=api_secret,
        endpoint_profile_name=prepared.launch_config.binance_endpoint_profile_name,
    )
    private_stream_client = BinancePrivateStreamClient(config=adapter_config)
    payload_source = BinanceRestrictedLivePayloadSource(
        client=private_stream_client,
        transport=BinancePrivateUserDataTransport(
            rest_base_url=adapter_config.rest_base_url,
            websocket_base_url=adapter_config.websocket_base_url,
            api_key=adapter_config.api_key,
            api_secret=adapter_config.api_secret,
            request_weight_tracker=BinanceRequestWeightTracker(
                max_weight=adapter_config.request_weight_limit_per_minute,
            ),
            endpoint_profile_name=adapter_config.endpoint_profile_name,
        ),
    )
    gate = RecordingRestrictedLiveGate(
        BinanceRestrictedLivePortfolioGate(
            payload_source=payload_source,
            private_stream_client=private_stream_client,
            private_payload_translator=BinancePrivatePayloadTranslator(
                symbol_mappings=(
                    BinanceSymbolMapping(
                        instrument_id=prepared.launch_config.instrument_id,
                        venue_symbol=_venue_symbol(prepared.launch_config.instrument_id),
                    ),
                ),
            ),
            reconciliation_service=BinanceReconciliationService(),
            order_client=BinanceOrderClient(
                config=adapter_config,
                clock_sync=BinanceClockSync(adapter_config),
            ),
    lookup_transport=BinanceSignedRestOrderStatusTransport(
                config=adapter_config,
                venue_symbol=_venue_symbol(prepared.launch_config.instrument_id),
                time_provider=lambda: int(payload_source.time_provider().timestamp() * 1000),
                request_weight_tracker=BinanceRequestWeightTracker(
                    max_weight=adapter_config.request_weight_limit_per_minute,
                ),
            ),
            private_session=payload_source.current_session,
        )
    )
    portfolio_state = prepared.portfolio_state
    if prepared.launch_config.bootstrap_from_account_snapshot:
        snapshot = BinanceSignedRestAccountSnapshotBootstrap(
            config=adapter_config,
            time_provider=lambda: int(payload_source.time_provider().timestamp() * 1000),
        ).fetch_snapshot()
        portfolio_state = build_portfolio_state_from_account_snapshot(
            prepared.launch_config,
            snapshot,
        )
        (run_dir / "bootstrap_portfolio_alignment.json").write_text(
            json.dumps(
                {
                    "bootstrap_from_account_snapshot": True,
                    "source_event_type": snapshot.source_event_type,
                    "snapshot_as_of": snapshot.as_of.isoformat(),
                    "balances": [
                        {
                            "asset": balance.asset,
                            "free": str(balance.free),
                            "locked": str(balance.locked),
                        }
                        for balance in snapshot.balances
                    ],
                    "derived_portfolio_state": {
                        "as_of": portfolio_state.as_of.isoformat(),
                        "cash_by_asset": {
                            asset: str(value) for asset, value in portfolio_state.cash_by_asset.items()
                        },
                        "position_qty_by_instrument": {
                            instrument_id: str(value)
                            for instrument_id, value in portfolio_state.position_qty_by_instrument.items()
                        },
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    exchange_health_provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )
    soak_context = replace(
        prepared.runtime_context,
        live_portfolio_mutation_gate=gate,
        exchange_health_provider=exchange_health_provider,
    )
    _write_finalization_debug_marker(
        run_dir=run_dir,
        phase="soak_runner.run",
        status="started",
    )
    try:
        run = RestrictedLiveSoakRunner(
            runner=RestrictedLiveRunner(soak_context),
            recording_gate=gate,
            exchange_health_provider=exchange_health_provider,
            payload_source=payload_source,
        ).run(
            criteria=RestrictedLiveSoakStopCriteria(
                max_cycles=args.cycles,
                max_duration=(
                    timedelta(hours=args.duration_hours)
                    if args.duration_hours is not None
                    else None
                ),
                poll_interval_seconds=args.poll_interval_seconds,
                max_blocked_mutations=args.max_blocked_mutations,
            ),
            cycle_id_prefix=prepared.launch_config.cycle_id,
            instrument=prepared.instrument,
            bar_slice=prepared.market_context.execution_bar_slice,
            context_bar_slice=prepared.market_context.context_bar_slice,
            portfolio_state=portfolio_state,
        )
    except Exception as exc:
        debug_path = _write_finalization_debug_marker(
            run_dir=run_dir,
            phase="soak_runner.run",
            status="failed",
            exception=exc,
        )
        _report_finalization_exception(
            phase="soak_runner.run",
            debug_path=debug_path,
            exception=exc,
        )
        return 1

    _write_finalization_debug_marker(
        run_dir=run_dir,
        phase="render_markdown",
        status="started",
        extra={
            "completed_cycles": run.summary.completed_cycles,
            "stop_reason": run.summary.stop_reason,
            "aborted": run.summary.aborted,
        },
    )
    try:
        markdown = RestrictedLiveSoakReportingService().render_markdown(run=run)
    except Exception as exc:
        debug_path = _write_finalization_debug_marker(
            run_dir=run_dir,
            phase="render_markdown",
            status="failed",
            exception=exc,
            extra={
                "completed_cycles": run.summary.completed_cycles,
                "stop_reason": run.summary.stop_reason,
                "aborted": run.summary.aborted,
            },
        )
        _report_finalization_exception(
            phase="render_markdown",
            debug_path=debug_path,
            exception=exc,
        )
        return 1

    writer = RestrictedLiveSoakArtifactWriter(output_dir=run_dir)
    _write_finalization_debug_marker(
        run_dir=run_dir,
        phase="artifact_writer.persist",
        status="started",
        extra={
            "completed_cycles": run.summary.completed_cycles,
            "stop_reason": run.summary.stop_reason,
            "aborted": run.summary.aborted,
        },
    )
    try:
        artifact_paths = writer.persist(
            run=run,
            markdown=markdown,
        )
    except Exception as exc:
        debug_path = _write_finalization_debug_marker(
            run_dir=run_dir,
            phase="artifact_writer.persist",
            status="failed",
            exception=exc,
            extra={
                "completed_cycles": run.summary.completed_cycles,
                "stop_reason": run.summary.stop_reason,
                "aborted": run.summary.aborted,
            },
        )
        _report_finalization_exception(
            phase="artifact_writer.persist",
            debug_path=debug_path,
            exception=exc,
        )
        return 1

    debug_path = _write_finalization_debug_marker(
        run_dir=run_dir,
        phase="artifact_writer.persist",
        status="completed",
        extra={
            "completed_cycles": run.summary.completed_cycles,
            "stop_reason": run.summary.stop_reason,
            "aborted": run.summary.aborted,
            "summary_json_path": str(artifact_paths.summary_json_path),
            "summary_markdown_path": str(artifact_paths.summary_markdown_path),
        },
    )
    print(f"soak_summary_json: {artifact_paths.summary_json_path}")
    print(f"soak_summary_markdown: {artifact_paths.summary_markdown_path}")
    print(f"health_transitions_jsonl: {artifact_paths.health_transitions_path}")
    print(f"reconnect_events_jsonl: {artifact_paths.reconnect_events_path}")
    print(f"listen_key_refresh_jsonl: {artifact_paths.listen_key_refresh_path}")
    print(f"reconciliation_events_jsonl: {artifact_paths.reconciliation_events_path}")
    print(f"finalization_debug_json: {debug_path}")
    print(f"stop_reason: {run.summary.stop_reason}")
    print(f"completed_cycles: {run.summary.completed_cycles}")
    return 0 if not run.summary.aborted else SOAK_ABORT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
