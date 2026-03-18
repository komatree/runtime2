"""Runtime observability tests."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RuntimeCycleResult
from app.monitoring import current_or_unknown_exchange_health
from app.monitoring import FileRuntimeStatusGateway
from app.monitoring import RuntimeDegradationFlag
from app.monitoring import RuntimeObservabilityService
from app.storage import JsonlReportPersistenceGateway


def test_health_summary_generation(tmp_path: Path) -> None:
    context = _decision_context(include_index=True, include_stablecoin=True)
    cycle = _cycle_result(success=True, alerts=())
    features = context.features
    observability = RuntimeObservabilityService(mode="report_only")

    summary = observability.build_cycle_summary(
        cycle_result=cycle,
        features=features,
        context=context,
        persisted_at=cycle.completed_at,
    )
    health = observability.build_health_snapshot(summary=summary)
    report = observability.render_operator_report(summary=summary, health=health)

    assert summary.bar_close_time == context.latest_candle.close_time
    assert health.last_persistence_success_at == cycle.completed_at
    assert "- degradation_flags: none" in report


def test_degraded_mode_reporting(tmp_path: Path) -> None:
    summary_path = tmp_path / "status" / "cycle_summaries.jsonl"
    health_path = tmp_path / "status" / "health.json"
    report_path = tmp_path / "status" / "operator_report.md"
    gateway = JsonlReportPersistenceGateway(
        output_path=tmp_path / "reports" / "runtime_report.jsonl",
        status_gateway=FileRuntimeStatusGateway(
            summary_output_path=summary_path,
            health_output_path=health_path,
            operator_report_path=report_path,
        ),
    )
    context = _decision_context(include_index=False, include_stablecoin=False)
    cycle = _cycle_result(success=True, alerts=("report-only cycle produced no executable intents",))

    gateway.persist_cycle(cycle, features=context.features, context=context)

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8").splitlines()[-1])
    health_payload = json.loads(health_path.read_text(encoding="utf-8"))
    operator_report = report_path.read_text(encoding="utf-8")

    assert RuntimeDegradationFlag.INDEX_SUITE_MISSING.value in summary_payload["degradation_flags"]
    assert RuntimeDegradationFlag.STABLECOIN_MISSING.value in health_payload["degradation_flags"]
    assert "index_suite_missing" in operator_report
    assert "stablecoin_missing" in operator_report


def test_unknown_exchange_health_is_rendered_when_provider_absent_for_binance_path(tmp_path: Path) -> None:
    summary_path = tmp_path / "status" / "cycle_summaries.jsonl"
    health_path = tmp_path / "status" / "health.json"
    report_path = tmp_path / "status" / "operator_report.md"
    gateway = JsonlReportPersistenceGateway(
        output_path=tmp_path / "reports" / "runtime_report.jsonl",
        status_gateway=FileRuntimeStatusGateway(
            summary_output_path=summary_path,
            health_output_path=health_path,
            operator_report_path=report_path,
        ),
    )
    context = _decision_context(include_index=False, include_stablecoin=False)
    cycle = _cycle_result(success=True, alerts=("ok",))
    exchange_health = current_or_unknown_exchange_health(venue="binance", provider=None)

    gateway.persist_cycle(
        cycle,
        features=context.features,
        context=context,
        exchange_health=exchange_health,
    )

    health_payload = json.loads(health_path.read_text(encoding="utf-8"))
    operator_report = report_path.read_text(encoding="utf-8")

    assert health_payload["exchange_health"]["overall_state"] == "unknown"
    assert "## Exchange Health" in operator_report
    assert "- private_stream: unknown (private stream health unavailable)" in operator_report
    assert "- status_query: unknown (no status-query attempts recorded)" in operator_report


def _decision_context(*, include_index: bool, include_stablecoin: bool) -> DecisionContext:
    instrument = Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )
    candle = Candle(
        instrument_id="BTC-USDT",
        timeframe="1m",
        open_time=_dt(0, 1),
        close_time=_dt(0, 2),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
    )
    bar_slice = BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(0, 2),
        candles=(candle,),
    )
    features = FeatureSnapshot(
        instrument_id="BTC-USDT",
        timeframe="1m",
        as_of=_dt(0, 2),
        feature_values={"candle.close_return_1": Decimal("0.005")},
        source_bar_count=1,
        is_complete=True,
    )
    portfolio = PortfolioState(
        as_of=_dt(0, 2),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )
    return DecisionContext(
        cycle_id="obs-001",
        as_of=_dt(0, 2),
        instrument=instrument,
        latest_candle=candle,
        bar_slice=bar_slice,
        features=features,
        portfolio_state=portfolio,
        index_snapshot=object() if include_index else None,
        stablecoin_snapshot=object() if include_stablecoin else None,
    )


def _cycle_result(*, success: bool, alerts: tuple[str, ...]) -> RuntimeCycleResult:
    return RuntimeCycleResult(
        cycle_id="obs-001",
        started_at=_dt(0, 2),
        completed_at=_dt(0, 3),
        processed_instruments=("BTC-USDT",),
        signals=(),
        risk_decisions=(),
        execution_intents=(),
        alerts=alerts,
        success=success,
    )


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
