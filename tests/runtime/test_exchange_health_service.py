from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path

from app.contracts import ReconciliationEvent
from app.contracts import ReconciliationState
from app.exchanges.binance import BinanceClockStatus
from app.exchanges.binance import BinancePrivateStreamHealth
from app.exchanges.binance import BinancePrivateStreamState
from app.exchanges.binance import BinanceStatusQueryHealth
from app.exchanges.binance import BinanceStatusQueryState
from app.exchanges.binance import BinanceOrderReconciliationResult
from app.exchanges.binance import BinanceReconciliationCoordinator
from app.monitoring import BinanceExchangeHealthService
from app.monitoring import ExchangeHealthState
from app.monitoring import FileRuntimeStatusGateway
from app.monitoring import RuntimeObservabilityService
from app.monitoring import current_or_unknown_exchange_health
from app.storage import BinanceReconciliationCursorSnapshot


def test_degraded_state_aggregation() -> None:
    snapshot = BinanceExchangeHealthService().build_snapshot(
        private_stream_health=BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.DEGRADED,
            reconnect_attempts=2,
            is_authoritative=False,
            alerts=("private-stream gap detected",),
        ),
        reconciliation_workflow=_pending_workflow(),
        clock_status=_healthy_clock(),
        status_query_health=(
            BinanceStatusQueryHealth(
                lookup_field="exchange_order_id",
                lookup_value="order-1",
                state=BinanceStatusQueryState.FAILED,
                checked_at=_dt(),
                transport="signed_rest_order_lookup",
                alert="lookup timeout",
            ),
        ),
        cursor_snapshot=BinanceReconciliationCursorSnapshot(
            schema_version="binance_reconciliation_state.v1",
            updated_at=_dt(),
            private_stream_cursor="cursor-1",
            gap_active=True,
            unresolved_order_ids=("order-1",),
            manual_attention_order_ids=(),
            last_recovery_trigger_reason="private_stream_gap",
            last_recovery_automatic=True,
            last_convergence_state="pending",
            last_manual_attention_at=None,
            persisted_attempts=(),
        ),
        generated_at=_dt(),
    )

    assert snapshot.overall_state is ExchangeHealthState.DEGRADED
    assert snapshot.private_stream.state is ExchangeHealthState.DEGRADED
    assert snapshot.reconciliation.state is ExchangeHealthState.DEGRADED
    assert snapshot.status_query.state is ExchangeHealthState.DEGRADED


def test_health_transitions_render_fatal_when_clock_and_manual_attention_present() -> None:
    degraded = BinanceExchangeHealthService().build_snapshot(
        private_stream_health=BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.STREAMING,
            reconnect_attempts=0,
            is_authoritative=True,
        ),
        reconciliation_workflow=_pending_workflow(),
        clock_status=_healthy_clock(),
        generated_at=_dt(),
    )
    fatal = BinanceExchangeHealthService().build_snapshot(
        private_stream_health=BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.TERMINATED,
            reconnect_attempts=1,
            is_authoritative=False,
            alerts=("private stream terminated",),
        ),
        reconciliation_workflow=_manual_attention_workflow(),
        clock_status=BinanceClockStatus(
            offset_ms=1500,
            round_trip_ms=250,
            is_within_tolerance=False,
            checked_at=_dt(),
            server_time_ms=1773360000000,
            local_time_ms=1773360001500,
            is_uncertain=True,
            alert="clock recalibration failed",
        ),
        generated_at=_dt(),
    )

    assert degraded.overall_state is ExchangeHealthState.DEGRADED
    assert fatal.overall_state is ExchangeHealthState.FATAL


def test_operator_facing_summary_rendering_and_runtime_status_persistence(tmp_path: Path) -> None:
    exchange_health = BinanceExchangeHealthService().build_snapshot(
        private_stream_health=BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.STREAMING,
            reconnect_attempts=0,
            is_authoritative=True,
        ),
        reconciliation_workflow=_healthy_workflow(),
        clock_status=_healthy_clock(),
        status_query_health=(
            BinanceStatusQueryHealth(
                lookup_field="exchange_order_id",
                lookup_value="order-2",
                state=BinanceStatusQueryState.SUCCESS,
                checked_at=_dt(),
                transport="signed_rest_order_lookup",
            ),
        ),
        generated_at=_dt(),
    )
    summary = _summary_with_exchange_health(tmp_path=tmp_path, exchange_health=exchange_health)
    report = RuntimeObservabilityService(mode="restricted_live").render_operator_report(
        summary=summary["summary"],
        health=summary["health"],
    )

    assert "## Exchange Health" in report
    assert "- overall_state: healthy" in report
    assert "- private_stream: healthy (private stream connected and authoritative)" in report

    payload = json.loads(summary["health_path"].read_text(encoding="utf-8"))
    assert payload["exchange_health"]["overall_state"] == "healthy"
    assert payload["exchange_health"]["private_stream"]["state"] == "healthy"


def test_unknown_exchange_health_snapshot_is_used_when_provider_absent_for_binance() -> None:
    snapshot = current_or_unknown_exchange_health(venue="binance", provider=None)

    assert snapshot is not None
    assert snapshot.overall_state is ExchangeHealthState.UNKNOWN
    assert snapshot.private_stream.state is ExchangeHealthState.UNKNOWN
    assert snapshot.reconciliation.state is ExchangeHealthState.UNKNOWN
    assert snapshot.clock_sync.state is ExchangeHealthState.UNKNOWN
    assert snapshot.status_query.state is ExchangeHealthState.UNKNOWN


def test_operator_summary_renders_degraded_and_fatal_component_details(tmp_path: Path) -> None:
    snapshot = BinanceExchangeHealthService().build_snapshot(
        private_stream_health=BinancePrivateStreamHealth(
            state=BinancePrivateStreamState.DEGRADED,
            reconnect_attempts=3,
            is_authoritative=False,
            alerts=("private-stream gap detected",),
        ),
        reconciliation_workflow=_manual_attention_workflow(),
        clock_status=BinanceClockStatus(
            offset_ms=1500,
            round_trip_ms=250,
            is_within_tolerance=False,
            checked_at=_dt(),
            server_time_ms=1773360000000,
            local_time_ms=1773360001500,
            is_uncertain=True,
            alert="clock recalibration failed",
        ),
        status_query_health=(
            BinanceStatusQueryHealth(
                lookup_field="exchange_order_id",
                lookup_value="order-3",
                state=BinanceStatusQueryState.FAILED,
                checked_at=_dt(),
                transport="signed_rest_order_lookup",
                alert="lookup timeout",
            ),
        ),
        generated_at=_dt(),
    )
    summary = _summary_with_exchange_health(tmp_path=tmp_path, exchange_health=snapshot)
    report = RuntimeObservabilityService(mode="restricted_live").render_operator_report(
        summary=summary["summary"],
        health=summary["health"],
    )

    assert "- private_stream: degraded (private stream degraded)" in report
    assert "- reconciliation: fatal (manual attention required)" in report
    assert "- clock_sync: fatal (clock sync uncertain or out of tolerance)" in report
    assert "- status_query: degraded (latest signed status query failed)" in report


def _summary_with_exchange_health(*, tmp_path: Path, exchange_health):
    observability = RuntimeObservabilityService(mode="restricted_live")
    summary = observability.build_cycle_summary(
        cycle_result=_cycle_result(),
        features=_feature_snapshot(),
        context=_decision_context(),
        persisted_at=_dt(),
        exchange_health=exchange_health,
    )
    health = observability.build_health_snapshot(summary=summary, exchange_health=exchange_health)
    health_path = tmp_path / "status" / "health.json"
    FileRuntimeStatusGateway(
        summary_output_path=tmp_path / "status" / "cycle_summaries.jsonl",
        health_output_path=health_path,
        operator_report_path=tmp_path / "status" / "runtime_status.md",
    ).persist(
        summary=summary,
        health=health,
        operator_report=observability.render_operator_report(summary=summary, health=health),
    )
    return {"summary": summary, "health": health, "health_path": health_path}


def _pending_workflow():
    return BinanceReconciliationCoordinator().coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-1",),
            unknown_execution_ids=(),
            alerts=(),
        ),
        occurred_at=_dt(),
    )


def _manual_attention_workflow():
    return BinanceReconciliationCoordinator(max_recovery_attempts=1).coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-2",),
            unknown_execution_ids=(),
            alerts=(),
        ),
        lookup_results=(
            __import__("app.exchanges.binance", fromlist=["BinanceOrderLookupResult"]).BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value="order-2",
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="manual attention required",
                attempt_number=1,
            ),
        ),
        occurred_at=_dt(),
    )


def _healthy_workflow():
    return BinanceReconciliationCoordinator().coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=("order-2",),
            missing_order_ids=(),
            unknown_execution_ids=(),
            alerts=(),
        ),
        occurred_at=_dt(),
    )


def _healthy_clock() -> BinanceClockStatus:
    return BinanceClockStatus(
        offset_ms=20,
        round_trip_ms=40,
        is_within_tolerance=True,
        checked_at=_dt(),
        server_time_ms=1773360000000,
        local_time_ms=1773360000020,
        is_uncertain=False,
    )


def _dt() -> datetime:
    return datetime(2026, 3, 14, 0, 0, tzinfo=UTC)


def _feature_snapshot():
    from decimal import Decimal

    from app.contracts import FeatureSnapshot

    return FeatureSnapshot(
        instrument_id="BTC-USDT",
        timeframe="1m",
        as_of=_dt(),
        feature_values={"candle.close_return_1": Decimal("0.01")},
        source_bar_count=2,
        is_complete=True,
    )


def _decision_context():
    from decimal import Decimal

    from app.contracts import BarSlice
    from app.contracts import Candle
    from app.contracts import DecisionContext
    from app.contracts import Instrument
    from app.contracts import PortfolioState

    candle = Candle(
        instrument_id="BTC-USDT",
        timeframe="1m",
        open_time=datetime(2026, 3, 13, 23, 59, tzinfo=UTC),
        close_time=_dt(),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1"),
    )
    return DecisionContext(
        cycle_id="health-001",
        as_of=_dt(),
        instrument=Instrument(
            instrument_id="BTC-USDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_precision=2,
            quantity_precision=6,
        ),
        latest_candle=candle,
        bar_slice=BarSlice(
            instrument_id="BTC-USDT",
            timeframe="1m",
            end_time=candle.close_time,
            candles=(candle,),
        ),
        features=_feature_snapshot(),
        portfolio_state=PortfolioState(
            as_of=_dt(),
            cash_by_asset={"USDT": Decimal("1000")},
            position_qty_by_instrument={"BTC-USDT": Decimal("0")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
    )


def _cycle_result():
    from app.contracts import RuntimeCycleResult

    return RuntimeCycleResult(
        cycle_id="health-001",
        started_at=_dt(),
        completed_at=_dt(),
        processed_instruments=("BTC-USDT",),
        signals=(),
        risk_decisions=(),
        execution_intents=(),
        reconciliation_events=(
            ReconciliationEvent(
                venue="binance",
                order_id="order-2",
                reconciliation_state=ReconciliationState.RECOVERED_TERMINAL_STATE,
                occurred_at=_dt(),
                detail="ok",
            ),
        ),
        alerts=(),
        success=True,
    )
