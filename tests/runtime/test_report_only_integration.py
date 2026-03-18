"""Report-only integration tests using the real vertical-slice skeleton.

TODO:
- Add rejection-path assertions once richer risk rules exist.
- Add multi-instrument replay coverage when runtime orchestration expands.
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
from app.runtime import ReportOnlyRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.runtime import RuntimeFeatureBuilder
from app.storage import JsonlReportPersistenceGateway
from app.strategies.breakout import BreakoutStrategy
from app.strategies.regime import RegimeStrategy
from app.strategies.router import StrategyRouter


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)


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
        as_of=_dt(0, 2),
        cash_by_asset={"USDT": Decimal("10000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _bar_slice(*, latest_close: str) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(0, 2),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 0),
                close_time=_dt(0, 1),
                open=Decimal("100"),
                high=Decimal("100.5"),
                low=Decimal("99.5"),
                close=Decimal("100"),
                volume=Decimal("10"),
                is_closed=True,
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 1),
                close_time=_dt(0, 2),
                open=Decimal("100"),
                high=Decimal(latest_close),
                low=Decimal("99.8"),
                close=Decimal(latest_close),
                volume=Decimal("12"),
                is_closed=True,
            ),
        ),
    )


class _StaticIndexProvider:
    def __init__(self, snapshot: IndexSnapshot | None) -> None:
        self.snapshot = snapshot

    def get_snapshot(self, *, instrument_id: str, as_of) -> IndexSnapshot | None:
        return self.snapshot


class _StaticStablecoinProvider:
    def __init__(self, snapshot: StablecoinSnapshot | None) -> None:
        self.snapshot = snapshot

    def get_snapshot(self, *, as_of) -> StablecoinSnapshot | None:
        return self.snapshot


def _build_context(tmp_path: Path, *, index_snapshot=None, stablecoin_snapshot=None) -> RuntimeContext:
    return RuntimeContext(
        mode=RunnerMode.REPORT_ONLY,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
            index_snapshot_provider=_StaticIndexProvider(index_snapshot),
            stablecoin_snapshot_provider=_StaticStablecoinProvider(stablecoin_snapshot),
        ),
        strategy_evaluator=StrategyRouter(
            strategies=(
                BreakoutStrategy(breakout_threshold=Decimal("0.02")),
                RegimeStrategy(),
            ),
            include_flat_signals=False,
        ),
        risk_evaluator=ReportOnlyRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=JsonlReportPersistenceGateway(tmp_path / "reports" / "runtime_report.jsonl"),
        index_snapshot_provider=_StaticIndexProvider(index_snapshot),
        stablecoin_snapshot_provider=_StaticStablecoinProvider(stablecoin_snapshot),
        execution_venue="binance",
    )


def _load_report(tmp_path: Path) -> dict:
    report_path = tmp_path / "reports" / "runtime_report.jsonl"
    lines = report_path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


def test_end_to_end_report_only_cycle(tmp_path: Path) -> None:
    context = _build_context(
        tmp_path,
        index_snapshot=IndexSnapshot(
            name="risk-on",
            instrument_id="BTC-USDT",
            index_version="v1",
            as_of=_dt(0, 2),
            value=Decimal("60"),
            constituents=("BTC-USDT", "ETH-USDT"),
            methodology="breadth",
        ),
        stablecoin_snapshot=StablecoinSnapshot(
            pair="USDT-USD",
            reference_asset="USD",
            snapshot_version="obs.v1",
            source_type="report_only_ingest",
            as_of=_dt(0, 2),
            source_fresh_until=_dt(0, 30),
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
        ),
    )
    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="report-001",
        instrument=_instrument(),
        bar_slice=_bar_slice(latest_close="103"),
        portfolio_state=_portfolio(),
    )

    payload = _load_report(tmp_path)
    assert cycle.success is True
    assert len(cycle.execution_intents) == 1
    assert payload["decision_context_summary"]["has_index_snapshot"] is True
    assert payload["decision_context_summary"]["has_stablecoin_snapshot"] is True


def test_no_action_cycle(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="report-002",
        instrument=_instrument(),
        bar_slice=_bar_slice(latest_close="100.5"),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is True
    assert cycle.signals == ()
    assert cycle.execution_intents == ()
    assert "report-only cycle produced no executable intents" in cycle.alerts


def test_action_producing_placeholder_cycle(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="report-003",
        instrument=_instrument(),
        bar_slice=_bar_slice(latest_close="103"),
        portfolio_state=_portfolio(),
    )

    assert len(cycle.signals) == 1
    assert len(cycle.risk_decisions) == 1
    assert len(cycle.execution_intents) == 1
    assert cycle.execution_intents[0].venue == "binance"


def test_missing_optional_feature_sources(tmp_path: Path) -> None:
    context = _build_context(tmp_path, index_snapshot=None, stablecoin_snapshot=None)
    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="report-004",
        instrument=_instrument(),
        bar_slice=_bar_slice(latest_close="103"),
        portfolio_state=_portfolio(),
    )

    payload = _load_report(tmp_path)
    feature_names = set(payload["feature_snapshot_summary"]["feature_names"])
    assert cycle.success is True
    assert payload["decision_context_summary"]["has_index_snapshot"] is False
    assert payload["decision_context_summary"]["has_stablecoin_snapshot"] is False
    assert "candle.close_return_1" in feature_names
    assert "index_suite.value" not in feature_names
