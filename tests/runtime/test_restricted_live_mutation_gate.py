"""Restricted-live mutation gate visibility tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import ReconciliationEvent
from app.contracts import ReconciliationState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.portfolio import LivePortfolioMutationOutcome
from app.portfolio import LivePortfolioTranslationResult
from app.portfolio import LiveTranslationStatus
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext


def test_restricted_live_cycle_surfaces_mutation_block_reason() -> None:
    context = RuntimeContext(
        mode=RunnerMode.RESTRICTED_LIVE,
        feature_builder=_FeatureBuilder(),
        strategy_evaluator=_StrategyEvaluator(),
        risk_evaluator=_RiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=_PersistenceGateway(),
        venue_profile=_venue_profile(),
        execution_venue="binance",
        live_portfolio_mutation_gate=_BlockedGate(),
    )
    runner = RestrictedLiveRunner(context)

    cycle = runner.run_cycle(
        cycle_id="restricted-live-001",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        portfolio_state=_portfolio(),
    )

    assert cycle.success is False
    assert cycle.reconciliation_events[-1].reconciliation_state is ReconciliationState.UNRECONCILED_MANUAL_ATTENTION
    assert "restricted-live portfolio mutation blocked by mandatory safeguard gate" in cycle.alerts


class _FeatureBuilder:
    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        return FeatureSnapshot(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            feature_values={"candle.close_return_1": Decimal("0.02")},
            source_bar_count=2,
            is_complete=True,
        )


class _StrategyEvaluator:
    def evaluate(self, context):
        return (
            SignalDecision(
                strategy_name="breakout_v1",
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=SignalSide.BUY,
                confidence=Decimal("0.8"),
                rationale="test",
                target_quantity=Decimal("1"),
            ),
        )


class _RiskEvaluator:
    def evaluate(self, signals, portfolio_state, venue_profile):
        return tuple(
            RiskDecision(
                signal=signal,
                status=RiskDecisionStatus.ALLOW,
                evaluated_at=signal.as_of,
                reasons=("ok",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class _PersistenceGateway:
    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        return None


class _BlockedGate:
    def apply(self, *, portfolio_state, expected_order_ids=(), already_applied_fill_ids=()):
        return LivePortfolioMutationOutcome(
            mutation_attempted=True,
            mutation_applied=False,
            portfolio_state=portfolio_state,
            translation_result=LivePortfolioTranslationResult(
                status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                portfolio_state=portfolio_state,
                applied_fill_ids=(),
                ignored_fill_ids=(),
                pending_order_ids=("order-1",),
                alerts=("portfolio mutation blocked pending reconciliation for order: order-1",),
                aggregations=(),
                requires_manual_attention=True,
            ),
            reconciliation_events=(
                ReconciliationEvent(
                    venue="binance",
                    order_id="order-1",
                    reconciliation_state=ReconciliationState.UNRECONCILED_MANUAL_ATTENTION,
                    occurred_at=_dt(),
                    detail="manual attention required",
                ),
            ),
            alerts=("portfolio mutation blocked pending reconciliation for order: order-1",),
        )


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )


def _bar_slice() -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=datetime(2026, 3, 13, 0, 0, tzinfo=UTC),
                close_time=datetime(2026, 3, 13, 0, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=datetime(2026, 3, 13, 0, 1, tzinfo=UTC),
                close_time=datetime(2026, 3, 13, 0, 2, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("100"),
                close=Decimal("101"),
                volume=Decimal("1"),
            ),
        ),
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(
        as_of=_dt(),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _venue_profile() -> VenueProfile:
    return VenueProfile(
        venue="binance",
        account_scope="spot",
        maker_fee_bps=Decimal("7"),
        taker_fee_bps=Decimal("10"),
        supports_market_orders=True,
        supports_post_only=True,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    )


def _dt() -> datetime:
    return datetime(2026, 3, 13, 0, 2, tzinfo=UTC)
