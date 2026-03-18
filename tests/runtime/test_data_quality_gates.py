"""Runtime data quality and freshness gate tests.

TODO:
- Add explicit time-sync provider integration tests once runtime wiring reads live clock status.
- Add paper-mode degraded continuity tests when paper persistence includes quality rollups.
"""

from __future__ import annotations

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
from app.contracts import StablecoinSnapshot
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import ReadOnlyIndexSuiteProvider
from app.features.index_suite.repository import InMemoryIndexSuiteRepository
from app.features.index_suite.service import IndexSuiteFeatureService
from app.features.stablecoin import ReadOnlyStablecoinSnapshotProvider
from app.features.stablecoin.repository import InMemoryStablecoinSnapshotRepository
from app.features.stablecoin.service import StablecoinFeatureService
from app.risk import ReportOnlyRiskEvaluator
from app.runtime import ReportOnlyRunner
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.runtime import RuntimeFeatureBuilder
from app.strategies.breakout import BreakoutStrategy
from app.strategies.router import StrategyRouter


class _PersistenceGateway:
    def __init__(self) -> None:
        self.contexts = []
        self.cycles = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.cycles.append(cycle_result)
        self.contexts.append(context)


def test_stale_snapshot_rejection() -> None:
    persistence = _PersistenceGateway()
    context = _runtime_context(
        mode=RunnerMode.RESTRICTED_LIVE,
        persistence_gateway=persistence,
        index_provider=ReadOnlyIndexSuiteProvider(
            repository=InMemoryIndexSuiteRepository(
                snapshots=(
                    IndexSnapshot(
                        name="risk-on",
                        instrument_id="BTC-USDT",
                        index_version="v1",
                        as_of=_dt(day=10, hour=0),
                        value=Decimal("55"),
                        constituents=("BTC-USDT",),
                        methodology="breadth",
                    ),
                )
            ),
            index_version="v1",
            max_snapshot_age=timedelta(hours=12),
        ),
    )

    cycle = RestrictedLiveRunner(context).run_cycle(
        cycle_id="quality-001",
        instrument=_instrument(),
        bar_slice=_execution_bar(closed=True),
        context_bar_slice=_context_bar(closed=True),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is False
    assert DataQualityState.STALE_DATA in cycle.quality_states
    assert "index suite snapshot stale" in cycle.quality_details


def test_incomplete_candle_rejection() -> None:
    persistence = _PersistenceGateway()
    context = _runtime_context(
        mode=RunnerMode.REPORT_ONLY,
        persistence_gateway=persistence,
    )

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="quality-002",
        instrument=_instrument(),
        bar_slice=_execution_bar(closed=False),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is False
    assert cycle.quality_states == (DataQualityState.INCOMPLETE_BAR,)
    assert "latest candle is not closed" in cycle.quality_details


def test_version_mismatch_handling() -> None:
    persistence = _PersistenceGateway()
    context = _runtime_context(
        mode=RunnerMode.REPORT_ONLY,
        persistence_gateway=persistence,
        index_provider=ReadOnlyIndexSuiteProvider(
            repository=InMemoryIndexSuiteRepository(
                snapshots=(
                    IndexSnapshot(
                        name="risk-on",
                        instrument_id="BTC-USDT",
                        index_version="legacy-v0",
                        as_of=_dt(hour=8),
                        value=Decimal("61"),
                        constituents=("BTC-USDT",),
                        methodology="breadth",
                    ),
                )
            ),
            index_version="v1",
            max_snapshot_age=timedelta(hours=12),
        ),
    )

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="quality-003",
        instrument=_instrument(),
        bar_slice=_execution_bar(closed=True),
        context_bar_slice=_context_bar(closed=True),
        portfolio_state=_portfolio(),
    )

    persisted_context = persistence.contexts[-1]
    assert cycle.success is True
    assert DataQualityState.VERSION_MISMATCH in cycle.quality_states
    assert persisted_context.index_snapshot_status == "version_mismatch"
    assert DataQualityState.VERSION_MISMATCH in persisted_context.quality_states


def test_degraded_but_allowed_report_only_behavior() -> None:
    persistence = _PersistenceGateway()
    context = _runtime_context(
        mode=RunnerMode.REPORT_ONLY,
        persistence_gateway=persistence,
        stablecoin_provider=ReadOnlyStablecoinSnapshotProvider(
            repository=InMemoryStablecoinSnapshotRepository(
                snapshots=(
                    StablecoinSnapshot(
                        pair="USDT-USD",
                        reference_asset="USD",
                        snapshot_version="obs.v1",
                        source_type="report_only_ingest",
                        as_of=_dt(hour=6),
                        source_fresh_until=_dt(hour=7),
                        stablecoin_net_mint_24h=Decimal("1000000"),
                        stablecoin_net_burn_24h=Decimal("200000"),
                        stablecoin_supply_change_pct_24h=Decimal("0.22"),
                        stablecoin_chain_supply_delta_24h=Decimal("800000"),
                        stablecoin_abnormal_transfer_count=1,
                    ),
                )
            )
        ),
        time_sync_ok=False,
        time_sync_detail="server time reference unavailable",
    )

    cycle = ReportOnlyRunner(context).run_cycle(
        cycle_id="quality-004",
        instrument=_instrument(),
        bar_slice=_execution_bar(closed=True),
        context_bar_slice=_context_bar(closed=True),
        portfolio_state=_portfolio(),
    )

    persisted_context = persistence.contexts[-1]
    assert cycle.success is True
    assert DataQualityState.STALE_DATA in cycle.quality_states
    assert DataQualityState.TIME_SYNC_UNCERTAIN in cycle.quality_states
    assert "stablecoin snapshot stale" in cycle.quality_details
    assert "server time reference unavailable" in cycle.quality_details
    assert DataQualityState.STALE_DATA in persisted_context.quality_states


def test_restricted_live_fails_closed_when_runtime_clock_skew_is_uncertain() -> None:
    persistence = _PersistenceGateway()
    context = _runtime_context(
        mode=RunnerMode.RESTRICTED_LIVE,
        persistence_gateway=persistence,
        time_sync_ok=False,
        time_sync_detail="time sync uncertain after recalibration attempts",
    )

    cycle = RestrictedLiveRunner(context).run_cycle(
        cycle_id="quality-005",
        instrument=_instrument(),
        bar_slice=_execution_bar(closed=True),
        context_bar_slice=_context_bar(closed=True),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is False
    assert cycle.execution_intents == ()
    assert DataQualityState.TIME_SYNC_UNCERTAIN in cycle.quality_states
    assert "time sync uncertain after recalibration attempts" in cycle.quality_details


def _runtime_context(
    *,
    mode: RunnerMode,
    persistence_gateway,
    index_provider=None,
    stablecoin_provider=None,
    time_sync_ok: bool | None = None,
    time_sync_detail: str | None = None,
) -> RuntimeContext:
    return RuntimeContext(
        mode=mode,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
            index_snapshot_provider=index_provider,
            stablecoin_snapshot_provider=stablecoin_provider,
        ),
        strategy_evaluator=StrategyRouter(
            strategies=(BreakoutStrategy(breakout_threshold=Decimal("0.02")),),
            include_flat_signals=False,
        ),
        risk_evaluator=ReportOnlyRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence_gateway,
        index_snapshot_provider=index_provider,
        stablecoin_snapshot_provider=stablecoin_provider,
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
        time_sync_ok=time_sync_ok,
        time_sync_detail=time_sync_detail,
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
        as_of=_dt(hour=8),
        cash_by_asset={"USDT": Decimal("10000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _execution_bar(*, closed: bool) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="4h",
        end_time=_dt(hour=8),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="4h",
                open_time=_dt(hour=4),
                close_time=_dt(hour=8),
                open=Decimal("100"),
                high=Decimal("103"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=Decimal("120"),
                is_closed=closed,
            ),
        ),
    )


def _context_bar(*, closed: bool) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1d",
        end_time=_dt(day=13, hour=0),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1d",
                open_time=_dt(day=12, hour=0),
                close_time=_dt(day=13, hour=0),
                open=Decimal("98"),
                high=Decimal("104"),
                low=Decimal("97"),
                close=Decimal("102"),
                volume=Decimal("500"),
                is_closed=closed,
            ),
        ),
    )


def _dt(*, day: int = 13, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)
