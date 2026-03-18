"""Scenario-based regression coverage for runtime2.

TODO:
- Add multi-instrument scenario fixtures when phase-1 scope expands.
- Add scenario snapshots backed by `data/` replay fixtures once curated datasets exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import DataQualityState
from app.contracts import IndexSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import StablecoinSnapshot
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import IndexSuiteFeatureService
from app.features.index_suite import ReadOnlyIndexSuiteProvider
from app.features.index_suite.repository import InMemoryIndexSuiteRepository
from app.features.stablecoin import ReadOnlyStablecoinSnapshotProvider
from app.features.stablecoin.service import StablecoinFeatureService
from app.features.stablecoin.repository import InMemoryStablecoinSnapshotRepository
from app.risk import ReportOnlyRiskEvaluator
from app.runtime import PaperRunner
from app.runtime import ReportOnlyRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.runtime import RuntimeFeatureBuilder
from app.strategies.router import StrategyRouter
from app.exchanges.binance import BinanceOrderLookupResult
from app.exchanges.binance import BinanceOrderReconciliationResult
from app.exchanges.binance import BinanceReconciliationCoordinator


@dataclass(frozen=True)
class ScenarioFixture:
    """Operator-readable scenario fixture metadata."""

    name: str
    cycle_ids: tuple[str, ...]
    closes: tuple[str, ...]
    signal_plan: dict[str, SignalSide]


class _PersistenceGateway:
    def __init__(self) -> None:
        self.cycles = []
        self.contexts = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.cycles.append(cycle_result)
        self.contexts.append(context)


class _FeatureBuilder:
    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None):
        from app.contracts import FeatureSnapshot

        values = {
            "candle.close_return_1": (bar_slice.candles[-1].close - bar_slice.candles[-1].open)
            / bar_slice.candles[-1].open
        }
        if context_bar_slice is not None:
            values["context.1d.close"] = context_bar_slice.candles[-1].close
        return FeatureSnapshot(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            feature_values=values,
            source_bar_count=len(bar_slice.candles),
            is_complete=True,
        )


class _ScenarioStrategyEvaluator:
    def __init__(self, plan: dict[str, SignalSide]) -> None:
        self.plan = plan

    def evaluate(self, context):
        side = self.plan.get(context.cycle_id)
        if side is None:
            return ()
        return (
            SignalDecision(
                strategy_name="breakout",
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=side,
                confidence=Decimal("0.75"),
                rationale=f"scenario {context.cycle_id}",
                target_quantity=Decimal("1"),
            ),
        )


class _ScenarioRiskEvaluator:
    def evaluate(self, signals, portfolio_state, venue_profile):
        return tuple(
            RiskDecision(
                signal=signal,
                status=RiskDecisionStatus.ALLOW,
                evaluated_at=signal.as_of,
                reasons=("scenario allow",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


def test_scenario_clean_no_action_market_report_only() -> None:
    scenario = ScenarioFixture(
        name="clean no-action market",
        cycle_ids=("scenario-no-action",),
        closes=("100.5",),
        signal_plan={},
    )
    context, _ = _scenario_context(mode=RunnerMode.REPORT_ONLY, signal_plan=scenario.signal_plan)

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id=scenario.cycle_ids[0],
        instrument=_instrument(),
        bar_slice=_bar_slice(close_price=scenario.closes[0], end_minute=2),
        context_bar_slice=_context_slice(),
        portfolio_state=_portfolio(),
    )

    assert cycle.signals == ()
    assert cycle.risk_decisions == ()
    assert cycle.execution_intents == ()
    assert cycle.quality_states == ()


def test_scenario_breakout_entry_report_only() -> None:
    scenario = ScenarioFixture(
        name="breakout entry",
        cycle_ids=("scenario-breakout",),
        closes=("103",),
        signal_plan={"scenario-breakout": SignalSide.BUY},
    )
    context, _ = _scenario_context(mode=RunnerMode.REPORT_ONLY, signal_plan=scenario.signal_plan)

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id=scenario.cycle_ids[0],
        instrument=_instrument(),
        bar_slice=_bar_slice(close_price=scenario.closes[0], end_minute=2),
        context_bar_slice=_context_slice(),
        portfolio_state=_portfolio(),
    )

    assert tuple(decision.status for decision in cycle.risk_decisions) == (RiskDecisionStatus.ALLOW,)
    assert len(cycle.execution_intents) == 1
    assert cycle.execution_intents[0].side.value == "buy"
    assert cycle.execution_intents[0].quantity == Decimal("1")


def test_scenario_hold_across_multiple_cycles_paper() -> None:
    scenario = ScenarioFixture(
        name="hold across multiple cycles",
        cycle_ids=("scenario-enter", "scenario-hold-1", "scenario-hold-2"),
        closes=("103", "104", "105"),
        signal_plan={"scenario-enter": SignalSide.BUY},
    )
    context, _ = _scenario_context(mode=RunnerMode.PAPER, signal_plan=scenario.signal_plan)

    session = PaperRunner(context).run_cycles(
        session_id=scenario.name,
        instrument=_instrument(),
        cycle_inputs=tuple(
            (
                cycle_id,
                _bar_slice(close_price=close, end_minute=2 + offset),
            )
            for offset, (cycle_id, close) in enumerate(zip(scenario.cycle_ids, scenario.closes, strict=True))
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert session.cycle_outcomes[0].ending_portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert session.cycle_outcomes[1].ending_portfolio_state == session.cycle_outcomes[0].ending_portfolio_state
    assert session.cycle_outcomes[2].ending_portfolio_state == session.cycle_outcomes[1].ending_portfolio_state
    assert tuple(len(outcome.cycle_result.risk_decisions) for outcome in session.cycle_outcomes) == (1, 0, 0)


def test_scenario_exit_condition_paper() -> None:
    scenario = ScenarioFixture(
        name="exit condition",
        cycle_ids=("scenario-enter", "scenario-exit"),
        closes=("103", "105"),
        signal_plan={
            "scenario-enter": SignalSide.BUY,
            "scenario-exit": SignalSide.SELL,
        },
    )
    context, _ = _scenario_context(mode=RunnerMode.PAPER, signal_plan=scenario.signal_plan)

    session = PaperRunner(context).run_cycles(
        session_id=scenario.name,
        instrument=_instrument(),
        cycle_inputs=(
            ("scenario-enter", _bar_slice(close_price="103", end_minute=2)),
            ("scenario-exit", _bar_slice(close_price="105", end_minute=3)),
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert tuple(decision.status for decision in session.cycle_outcomes[0].cycle_result.risk_decisions) == (
        RiskDecisionStatus.ALLOW,
    )
    assert tuple(decision.status for decision in session.cycle_outcomes[1].cycle_result.risk_decisions) == (
        RiskDecisionStatus.ALLOW,
    )
    assert session.final_portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("0")
    assert session.final_portfolio_state.cash_by_asset["USDT"] == Decimal("1002")


def test_scenario_degraded_feature_inputs_report_only() -> None:
    persistence = _PersistenceGateway()
    context = RuntimeContext(
        mode=RunnerMode.REPORT_ONLY,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
            stablecoin_snapshot_provider=ReadOnlyStablecoinSnapshotProvider(
                repository=InMemoryStablecoinSnapshotRepository(
                    snapshots=(
                        StablecoinSnapshot(
                            pair="USDT-USD",
                            reference_asset="USD",
                            snapshot_version="obs.v1",
                            source_type="report_only_ingest",
                            as_of=_dt(6),
                            source_fresh_until=_dt(7),
                            stablecoin_net_mint_24h=Decimal("1000000"),
                            stablecoin_net_burn_24h=Decimal("200000"),
                            stablecoin_supply_change_pct_24h=Decimal("0.22"),
                            stablecoin_chain_supply_delta_24h=Decimal("800000"),
                            stablecoin_abnormal_transfer_count=1,
                        ),
                    )
                )
            ),
        ),
        strategy_evaluator=_ScenarioStrategyEvaluator({"scenario-degraded": SignalSide.BUY}),
        risk_evaluator=_ScenarioRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence,
        stablecoin_snapshot_provider=ReadOnlyStablecoinSnapshotProvider(
            repository=InMemoryStablecoinSnapshotRepository(
                snapshots=(
                    StablecoinSnapshot(
                        pair="USDT-USD",
                        reference_asset="USD",
                        snapshot_version="obs.v1",
                        source_type="report_only_ingest",
                        as_of=_dt(6),
                        source_fresh_until=_dt(7),
                        stablecoin_net_mint_24h=Decimal("1000000"),
                        stablecoin_net_burn_24h=Decimal("200000"),
                        stablecoin_supply_change_pct_24h=Decimal("0.22"),
                        stablecoin_chain_supply_delta_24h=Decimal("800000"),
                        stablecoin_abnormal_transfer_count=1,
                    ),
                )
            )
        ),
        execution_venue="binance",
        time_sync_ok=False,
        time_sync_detail="server time reference unavailable",
    )

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="scenario-degraded",
        instrument=_instrument(),
        bar_slice=_bar_slice(close_price="103", end_minute=8),
        context_bar_slice=_context_slice(),
        portfolio_state=_portfolio(as_of_minute=8),
    )

    assert cycle.success is True
    assert DataQualityState.STALE_DATA in cycle.quality_states
    assert DataQualityState.TIME_SYNC_UNCERTAIN in cycle.quality_states
    assert len(cycle.execution_intents) == 1
    assert "stablecoin snapshot stale" in cycle.quality_details


def test_scenario_reconciliation_driven_recovery() -> None:
    workflow = BinanceReconciliationCoordinator().coordinate(
        reconciliation_result=BinanceOrderReconciliationResult(
            matched_order_ids=(),
            missing_order_ids=("order-recover",),
            unknown_execution_ids=("order-recover",),
            alerts=("unknown execution observed",),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="order-recover",
                source="rest_status",
                status_summary="filled",
            ),
        ),
        occurred_at=_dt(8),
    )

    recovered = [state for state in workflow.order_states if state.order_id == "order-recover"][-1]
    assert recovered.status is not None
    assert recovered.status.value == "filled"
    assert recovered.reconciliation_state is not None
    assert recovered.reconciliation_state.value == "recovered_terminal_state"
    assert "unknown execution observed" in workflow.alerts


def _scenario_context(*, mode: RunnerMode, signal_plan: dict[str, SignalSide]) -> tuple[RuntimeContext, _PersistenceGateway]:
    persistence = _PersistenceGateway()
    context = RuntimeContext(
        mode=mode,
        feature_builder=_FeatureBuilder(),
        strategy_evaluator=_ScenarioStrategyEvaluator(signal_plan),
        risk_evaluator=_ScenarioRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence,
        venue_profile=VenueProfile(
            venue="binance",
            account_scope="spot",
            maker_fee_bps=Decimal("7"),
            taker_fee_bps=Decimal("10"),
            supports_market_orders=True,
            supports_post_only=True,
            default_time_in_force=TimeInForce.GTC,
            supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
        ),
        execution_venue="binance" if mode is not RunnerMode.REPORT_ONLY else "unassigned_venue",
    )
    return context, persistence


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )


def _portfolio(*, as_of_minute: int = 2) -> PortfolioState:
    return PortfolioState(
        as_of=_dt(as_of_minute),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _bar_slice(*, close_price: str, end_minute: int) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(end_minute),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(end_minute - 1),
                close_time=_dt(end_minute),
                open=Decimal("100"),
                high=Decimal(close_price),
                low=Decimal("99.5"),
                close=Decimal(close_price),
                volume=Decimal("10"),
                is_closed=True,
            ),
        ),
    )


def _context_slice() -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1d",
        end_time=datetime(2026, 3, 13, 0, 0, tzinfo=UTC),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1d",
                open_time=datetime(2026, 3, 12, 0, 0, tzinfo=UTC),
                close_time=datetime(2026, 3, 13, 0, 0, tzinfo=UTC),
                open=Decimal("98"),
                high=Decimal("104"),
                low=Decimal("97"),
                close=Decimal("102"),
                volume=Decimal("500"),
                is_closed=True,
            ),
        ),
    )


def _dt(minute: int) -> datetime:
    return datetime(2026, 3, 13, 0, minute, tzinfo=UTC)
