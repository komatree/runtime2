"""Replay harness and backtest-runtime parity tests.

TODO:
- Add larger replay datasets after historical fixtures are curated under `data/`.
- Add parity drift bucketing once richer risk policies and execution planning exist.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import IndexSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import StablecoinSnapshot
from app.execution import ReportOnlyExecutionIntentBuilder
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import IndexSuiteFeatureService
from app.features.stablecoin import StablecoinFeatureService
from app.risk import ReportOnlyRiskEvaluator
from app.runtime import ReferenceBacktestEvaluator
from app.runtime import ReplayCycleInput
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.runtime import RuntimeFeatureBuilder
from app.runtime import RuntimeReplayHarness
from app.storage import JsonlParityComparisonGateway
from app.storage import JsonlReportPersistenceGateway
from app.strategies.breakout import BreakoutStrategy
from app.strategies.regime import RegimeStrategy
from app.strategies.router import StrategyRouter


def test_deterministic_replay(tmp_path: Path) -> None:
    inputs = (_cycle_input("parity-001", latest_close="103"),)
    first = _build_harness(tmp_path / "run1").replay(inputs)
    second = _build_harness(tmp_path / "run2").replay(inputs)

    assert _record_view(first) == _record_view(second)


def test_parity_no_action_scenario(tmp_path: Path) -> None:
    session = _build_harness(tmp_path).replay((_cycle_input("parity-002", latest_close="100.5"),))

    assert len(session.parity_records) == 2
    assert all(record.matches for record in session.parity_records)
    assert all(record.runtime_output["actionable"] is False for record in session.parity_records)
    assert all(record.runtime_output["signal_sides"] == () for record in session.parity_records)


def test_parity_action_scenario(tmp_path: Path) -> None:
    session = _build_harness(tmp_path).replay(
        (
            _cycle_input(
                "parity-003",
                latest_close="103",
                include_index=True,
                include_stablecoin=True,
            ),
        )
    )

    assert len(session.parity_records) == 2
    assert all(record.matches for record in session.parity_records)
    assert all(record.runtime_output["actionable"] is True for record in session.parity_records)
    assert all(record.key_context["has_index_snapshot"] is True for record in session.parity_records)
    assert all(record.key_context["has_stablecoin_snapshot"] is True for record in session.parity_records)


def test_parity_mismatch_reporting(tmp_path: Path) -> None:
    output_path = tmp_path / "parity" / "parity.jsonl"
    harness = _build_harness(
        tmp_path,
        reference_breakout_threshold=Decimal("0.50"),
        parity_output_path=output_path,
    )
    session = harness.replay((_cycle_input("parity-004", latest_close="103"),))

    assert any(record.matches is False for record in session.parity_records)
    assert any("signal_sides" in record.mismatches or "actionable" in record.mismatches for record in session.parity_records)

    lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert any(line["mismatches"] for line in lines)


def _build_harness(
    tmp_path: Path,
    *,
    runtime_breakout_threshold: Decimal = Decimal("0.02"),
    reference_breakout_threshold: Decimal | None = None,
    parity_output_path: Path | None = None,
) -> RuntimeReplayHarness:
    report_context = _runtime_context(
        tmp_path / "report",
        mode=RunnerMode.REPORT_ONLY,
        breakout_threshold=runtime_breakout_threshold,
    )
    paper_context = _runtime_context(
        tmp_path / "paper",
        mode=RunnerMode.PAPER,
        breakout_threshold=runtime_breakout_threshold,
    )
    reference_context = _runtime_context(
        tmp_path / "reference",
        mode=RunnerMode.REPORT_ONLY,
        breakout_threshold=reference_breakout_threshold or runtime_breakout_threshold,
    )
    return RuntimeReplayHarness(
        report_only_context=report_context,
        paper_context=paper_context,
        reference_evaluator=ReferenceBacktestEvaluator(reference_context),
        parity_gateway=JsonlParityComparisonGateway(
            output_path=parity_output_path or (tmp_path / "parity" / "parity.jsonl")
        ),
    )


def _runtime_context(tmp_path: Path, *, mode: RunnerMode, breakout_threshold: Decimal) -> RuntimeContext:
    return RuntimeContext(
        mode=mode,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
        ),
        strategy_evaluator=StrategyRouter(
            strategies=(
                BreakoutStrategy(breakout_threshold=breakout_threshold),
                RegimeStrategy(),
            ),
            include_flat_signals=False,
        ),
        risk_evaluator=ReportOnlyRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=JsonlReportPersistenceGateway(tmp_path / "reports" / "runtime_report.jsonl"),
        execution_venue="binance" if mode is not RunnerMode.REPORT_ONLY else "unassigned_venue",
    )


def _cycle_input(
    cycle_id: str,
    *,
    latest_close: str,
    include_index: bool = False,
    include_stablecoin: bool = False,
) -> ReplayCycleInput:
    return ReplayCycleInput(
        cycle_id=cycle_id,
        instrument=_instrument(),
        execution_bar_slice=_execution_bars(latest_close=latest_close),
        context_bar_slice=_context_bars(),
        portfolio_state=_portfolio(),
        index_snapshot=_index_snapshot() if include_index else None,
        stablecoin_snapshot=_stablecoin_snapshot() if include_stablecoin else None,
    )


def _record_view(session) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            record.runtime_mode,
            record.cycle_id,
            record.matches,
            record.mismatches,
            tuple(sorted(record.key_context.items())),
            json.dumps(record.runtime_output, sort_keys=True),
            json.dumps(record.reference_output, sort_keys=True),
        )
        for record in session.parity_records
    )


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(
        as_of=_dt(0, 0),
        cash_by_asset={"USDT": Decimal("10000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _execution_bars(*, latest_close: str) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="4h",
        end_time=_dt(8, 0),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="4h",
                open_time=_dt(0, 0),
                close_time=_dt(4, 0),
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                is_closed=True,
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="4h",
                open_time=_dt(4, 0),
                close_time=_dt(8, 0),
                open=Decimal("100"),
                high=Decimal(latest_close),
                low=Decimal("99"),
                close=Decimal(latest_close),
                volume=Decimal("120"),
                is_closed=True,
            ),
        ),
    )


def _context_bars() -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1d",
        end_time=_dt(0, 0, day=14),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1d",
                open_time=_dt(0, 0, day=12),
                close_time=_dt(0, 0, day=13),
                open=Decimal("95"),
                high=Decimal("101"),
                low=Decimal("94"),
                close=Decimal("100"),
                volume=Decimal("500"),
                is_closed=True,
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1d",
                open_time=_dt(0, 0, day=13),
                close_time=_dt(0, 0, day=14),
                open=Decimal("100"),
                high=Decimal("104"),
                low=Decimal("99"),
                close=Decimal("102"),
                volume=Decimal("550"),
                is_closed=True,
            ),
        ),
    )


def _index_snapshot() -> IndexSnapshot:
    return IndexSnapshot(
        name="risk-on",
        instrument_id="BTC-USDT",
        index_version="v1",
        as_of=_dt(8, 0),
        value=Decimal("60"),
        constituents=("BTC-USDT", "ETH-USDT"),
        methodology="breadth",
    )


def _stablecoin_snapshot() -> StablecoinSnapshot:
    return StablecoinSnapshot(
        pair="USDT-USD",
        reference_asset="USD",
        snapshot_version="obs.v1",
        source_type="report_only_ingest",
        as_of=_dt(8, 0),
        source_fresh_until=_dt(10, 0),
        stablecoin_net_mint_24h=Decimal("1000000"),
        stablecoin_net_burn_24h=Decimal("200000"),
        stablecoin_supply_change_pct_24h=Decimal("0.22"),
        stablecoin_chain_supply_delta_24h=Decimal("800000"),
        stablecoin_abnormal_transfer_count=1,
        price=Decimal("1.0001"),
        premium_bps=Decimal("1"),
        volume_24h=Decimal("1000000"),
        liquidity_score=Decimal("0.95"),
        is_depegged=False,
    )


def _dt(hour: int, minute: int = 0, *, day: int = 13) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)
