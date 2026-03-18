"""Runtime layer baseline tests.

TODO:
- Add paper and restricted-live cycle coverage once execution builders are shared.
- Add persistence failure-path tests with explicit alert expectations.
"""

from datetime import UTC
from datetime import datetime
from decimal import Decimal

import pytest

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.monitoring import BinanceExchangeHealthService
from app.monitoring import ExchangeHealthState
from app.runtime import BarCloseValidator
from app.runtime import PaperRunner
from app.runtime import ReportOnlyRunner
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 12, hour, minute, tzinfo=UTC)


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )


def _bar_slice(*, closed: bool = True) -> BarSlice:
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
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100.5"),
                volume=Decimal("10"),
                is_closed=True,
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 1),
                close_time=_dt(0, 2),
                open=Decimal("100.5"),
                high=Decimal("102"),
                low=Decimal("100"),
                close=Decimal("101.5"),
                volume=Decimal("12"),
                is_closed=closed,
            ),
        ),
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(
        as_of=_dt(0, 2),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


class StubFeatureBuilder:
    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        return FeatureSnapshot(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            feature_values={"momentum_1": Decimal("0.3")},
            source_bar_count=len(bar_slice.candles),
            is_complete=True,
        )


class StubStrategyEvaluator:
    def evaluate(self, context):
        return (
            SignalDecision(
                strategy_name="breakout_v1",
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=SignalSide.BUY,
                confidence=Decimal("0.75"),
                rationale="close above breakout threshold",
                target_quantity=Decimal("0.01"),
            ),
        )


class StubRiskEvaluator:
    def evaluate(self, signals, portfolio_state, venue_profile):
        return tuple(
            RiskDecision(
                signal=signal,
                status=RiskDecisionStatus.ALLOW,
                evaluated_at=signal.as_of,
                reasons=("within configured risk limits",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class StubPersistenceGateway:
    def __init__(self) -> None:
        self.calls = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.calls.append(
            {
                "cycle_result": cycle_result,
                "features": features,
                "context": context,
                "exchange_health": exchange_health,
            }
        )


class StubExchangeHealthProvider:
    def current_health(self):
        from app.exchanges.binance import BinanceClockStatus
        from app.exchanges.binance import BinancePrivateStreamHealth
        from app.exchanges.binance import BinancePrivateStreamState
        from app.exchanges.binance import BinanceStatusQueryHealth
        from app.exchanges.binance import BinanceStatusQueryState

        return BinanceExchangeHealthService().build_snapshot(
            private_stream_health=BinancePrivateStreamHealth(
                state=BinancePrivateStreamState.STREAMING,
                reconnect_attempts=0,
                is_authoritative=True,
            ),
            clock_status=BinanceClockStatus(
                offset_ms=10,
                round_trip_ms=20,
                is_within_tolerance=True,
                checked_at=_dt(0, 2),
                server_time_ms=1773360000000,
                local_time_ms=1773360000010,
                is_uncertain=False,
            ),
            status_query_health=(
                BinanceStatusQueryHealth(
                    lookup_field="exchange_order_id",
                    lookup_value="order-1",
                    state=BinanceStatusQueryState.SUCCESS,
                    checked_at=_dt(0, 2),
                    transport="signed_rest_order_lookup",
                ),
            ),
        )


def _context(mode: RunnerMode) -> RuntimeContext:
    venue_profile = VenueProfile(
        venue="binance",
        account_scope="spot",
        maker_fee_bps=Decimal("7"),
        taker_fee_bps=Decimal("10"),
        supports_market_orders=True,
        supports_post_only=True,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    )
    return RuntimeContext(
        mode=mode,
        feature_builder=StubFeatureBuilder(),
        strategy_evaluator=StubStrategyEvaluator(),
        risk_evaluator=StubRiskEvaluator(),
        persistence_gateway=StubPersistenceGateway(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        venue_profile=venue_profile,
        execution_venue="binance",
    )


def _context_without_venue(mode: RunnerMode) -> RuntimeContext:
    return RuntimeContext(
        mode=mode,
        feature_builder=StubFeatureBuilder(),
        strategy_evaluator=StubStrategyEvaluator(),
        risk_evaluator=StubRiskEvaluator(),
        persistence_gateway=StubPersistenceGateway(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
    )


def test_runner_initialization() -> None:
    report_runner = ReportOnlyRunner(_context(RunnerMode.REPORT_ONLY))
    paper_runner = PaperRunner(_context(RunnerMode.PAPER))
    live_runner = RestrictedLiveRunner(_context(RunnerMode.RESTRICTED_LIVE))

    assert report_runner.context.mode is RunnerMode.REPORT_ONLY
    assert paper_runner.context.mode is RunnerMode.PAPER
    assert live_runner.context.mode is RunnerMode.RESTRICTED_LIVE


def test_mode_separation() -> None:
    with pytest.raises(ValueError, match="report_only mode"):
        ReportOnlyRunner(_context(RunnerMode.PAPER))
    with pytest.raises(ValueError, match="paper mode"):
        PaperRunner(_context(RunnerMode.RESTRICTED_LIVE))
    with pytest.raises(ValueError, match="restricted_live mode"):
        RestrictedLiveRunner(_context(RunnerMode.REPORT_ONLY))


def test_bar_close_validator_behavior() -> None:
    validator = BarCloseValidator()
    valid = validator.validate(_bar_slice(closed=True))
    invalid = validator.validate(_bar_slice(closed=False))

    assert valid.is_valid is True
    assert invalid.is_valid is False
    assert invalid.reasons == ("latest candle is not closed",)


def test_runtime_cycle_result_generation_report_only() -> None:
    context = _context(RunnerMode.REPORT_ONLY)
    runner = ReportOnlyRunner(context)

    cycle = runner.run_cycle(
        cycle_id="cycle-001",
        instrument=_instrument(),
        bar_slice=_bar_slice(closed=True),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is True
    assert len(cycle.signals) == 1
    assert len(cycle.risk_decisions) == 1
    assert len(cycle.execution_intents) == 1
    assert "report-only generated intents were persisted only; no exchange submission" in cycle.alerts
    assert len(context.persistence_gateway.calls) == 1
    assert context.persistence_gateway.calls[0]["exchange_health"] is not None
    assert context.persistence_gateway.calls[0]["exchange_health"].overall_state is ExchangeHealthState.UNKNOWN


@pytest.mark.parametrize(
    ("mode", "runner_cls"),
    (
        (RunnerMode.REPORT_ONLY, ReportOnlyRunner),
        (RunnerMode.PAPER, PaperRunner),
        (RunnerMode.RESTRICTED_LIVE, RestrictedLiveRunner),
    ),
)
def test_binance_runtime_paths_persist_unknown_exchange_health_when_provider_absent(mode, runner_cls) -> None:
    context = _context(mode)
    runner = runner_cls(context)

    kwargs = {
        "cycle_id": f"{mode.value}-health-001",
        "instrument": _instrument(),
        "bar_slice": _bar_slice(closed=True),
        "portfolio_state": _portfolio(),
    }
    cycle_output = runner.run_cycle(**kwargs)
    cycle = cycle_output.cycle_result if hasattr(cycle_output, "cycle_result") else cycle_output

    assert cycle.processed_instruments == ("BTC-USDT",)
    persisted_health = context.persistence_gateway.calls[-1]["exchange_health"]
    assert persisted_health is not None
    assert persisted_health.overall_state is ExchangeHealthState.UNKNOWN
    assert persisted_health.private_stream.state is ExchangeHealthState.UNKNOWN
    assert persisted_health.reconciliation.state is ExchangeHealthState.UNKNOWN
    assert persisted_health.clock_sync.state is ExchangeHealthState.UNKNOWN
    assert persisted_health.status_query.state is ExchangeHealthState.UNKNOWN


def test_report_only_uses_neutral_venue_fallback() -> None:
    context = _context_without_venue(RunnerMode.REPORT_ONLY)
    runner = ReportOnlyRunner(context)

    cycle = runner.run_cycle(
        cycle_id="cycle-neutral-001",
        instrument=_instrument(),
        bar_slice=_bar_slice(closed=True),
        portfolio_state=_portfolio(),
    )

    assert cycle.execution_intents[0].venue == "unassigned_venue"


def test_runtime_uses_exchange_health_provider_when_present() -> None:
    context = _context(RunnerMode.REPORT_ONLY)
    context = RuntimeContext(
        mode=context.mode,
        feature_builder=context.feature_builder,
        strategy_evaluator=context.strategy_evaluator,
        risk_evaluator=context.risk_evaluator,
        persistence_gateway=context.persistence_gateway,
        execution_intent_builder=context.execution_intent_builder,
        venue_profile=context.venue_profile,
        execution_venue=context.execution_venue,
        exchange_health_provider=StubExchangeHealthProvider(),
    )
    runner = ReportOnlyRunner(context)

    runner.run_cycle(
        cycle_id="cycle-provider-001",
        instrument=_instrument(),
        bar_slice=_bar_slice(closed=True),
        portfolio_state=_portfolio(),
    )

    persisted_health = context.persistence_gateway.calls[-1]["exchange_health"]
    assert persisted_health is not None
    assert persisted_health.overall_state is ExchangeHealthState.HEALTHY
    assert persisted_health.private_stream.detail == "private stream connected and authoritative"
