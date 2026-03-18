"""Contract layer baseline tests.

TODO:
- Add versioning and schema-evolution coverage when persisted formats exist.
- Add cross-contract compatibility tests for storage serialization.
"""

from datetime import UTC
from datetime import datetime
from decimal import Decimal

import pytest

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import AccountSnapshot
from app.contracts import AssetBalanceSnapshot
from app.contracts import DecisionContext
from app.contracts import ExecutionIntent
from app.contracts import FeatureSnapshot
from app.contracts import FillEvent
from app.contracts import IndexSnapshot
from app.contracts import Instrument
from app.contracts import LiquidityRole
from app.contracts import OrderSide
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import OrderType
from app.contracts import PositionState
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import RuntimeCycleResult
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import StablecoinSnapshot
from app.contracts import TimeInForce
from app.contracts import VenueProfile


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 12, hour, minute, tzinfo=UTC)


def test_instrument_and_venue_profile_constructors() -> None:
    instrument = Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional=Decimal("10"),
    )
    venue = VenueProfile(
        venue="binance",
        account_scope="spot",
        maker_fee_bps=Decimal("7.5"),
        taker_fee_bps=Decimal("10.0"),
        supports_market_orders=True,
        supports_post_only=True,
        supports_reduce_only=False,
        supports_client_order_ids=True,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
        max_requests_per_second=20,
    )

    assert instrument.instrument_id == "BTC-USDT"
    assert instrument.price_increment == Decimal("0.01")
    assert venue.default_time_in_force is TimeInForce.GTC
    assert TimeInForce.IOC in venue.supported_time_in_force


def test_venue_neutral_contracts_support_multiple_venues() -> None:
    bybit = VenueProfile(
        venue="bybit",
        account_scope="linear",
        maker_fee_bps=Decimal("1"),
        taker_fee_bps=Decimal("5"),
        supports_market_orders=True,
        supports_post_only=True,
        supports_reduce_only=True,
        supports_client_order_ids=True,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK),
    )
    bithumb_instrument = Instrument(
        instrument_id="ETH-KRW",
        base_asset="ETH",
        quote_asset="KRW",
        price_precision=0,
        quantity_precision=8,
        price_increment=Decimal("1000"),
        quantity_increment=Decimal("0.0001"),
        is_active=True,
    )

    assert bybit.supports_reduce_only is True
    assert bybit.supported_time_in_force[-1] is TimeInForce.FOK
    assert bithumb_instrument.quote_asset == "KRW"


def test_candle_and_bar_slice_validate_invariants() -> None:
    candle_1 = Candle(
        instrument_id="BTC-USDT",
        timeframe="1m",
        open_time=_dt(0, 0),
        close_time=_dt(0, 1),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("102"),
        volume=Decimal("12.5"),
        quote_volume=Decimal("1275"),
        trade_count=42,
        is_closed=True,
    )
    candle_2 = Candle(
        instrument_id="BTC-USDT",
        timeframe="1m",
        open_time=_dt(0, 1),
        close_time=_dt(0, 2),
        open=Decimal("102"),
        high=Decimal("106"),
        low=Decimal("101"),
        close=Decimal("104"),
        volume=Decimal("10"),
        trade_count=30,
        is_closed=True,
    )

    bar_slice = BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(0, 2),
        candles=(candle_1, candle_2),
    )

    assert bar_slice.candles[-1].close == Decimal("104")


def test_candle_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="high must be"):
        Candle(
            instrument_id="BTC-USDT",
            timeframe="1m",
            open_time=_dt(0, 0),
            close_time=_dt(0, 1),
            open=Decimal("100"),
            high=Decimal("99"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )


def test_feature_and_market_snapshots_are_representative() -> None:
    features = FeatureSnapshot(
        instrument_id="BTC-USDT",
        timeframe="5m",
        as_of=_dt(1, 0),
        feature_values={
            "returns_5": Decimal("0.013"),
            "atr_14": Decimal("42.1"),
        },
        source_bar_count=14,
        is_complete=True,
    )
    market_index = IndexSnapshot(
        name="crypto-risk-on",
        instrument_id="BTC-USDT",
        index_version="v1",
        as_of=_dt(1, 0),
        value=Decimal("57.4"),
        constituents=("BTC-USDT", "ETH-USDT"),
        methodology="weighted momentum breadth",
    )
    stablecoin = StablecoinSnapshot(
        pair="USDT-USD",
        reference_asset="USD",
        snapshot_version="obs.v1",
        source_type="report_only_ingest",
        as_of=_dt(1, 0),
        source_fresh_until=_dt(1, 30),
        stablecoin_net_mint_24h=Decimal("1000000"),
        stablecoin_net_burn_24h=Decimal("250000"),
        stablecoin_supply_change_pct_24h=Decimal("0.35"),
        stablecoin_chain_supply_delta_24h=Decimal("750000"),
        stablecoin_abnormal_transfer_count=3,
        price=Decimal("0.9996"),
        premium_bps=Decimal("-4"),
        volume_24h=Decimal("150000000"),
        liquidity_score=Decimal("0.88"),
        is_depegged=False,
    )

    assert features.is_complete is True
    assert market_index.constituents[0] == "BTC-USDT"
    assert stablecoin.price == Decimal("0.9996")
    assert stablecoin.source_type == "report_only_ingest"


def test_account_snapshot_contract_is_representative() -> None:
    snapshot = AccountSnapshot(
        venue="binance",
        account_scope="spot",
        as_of=_dt(1, 5),
        balances=(
            AssetBalanceSnapshot(
                asset="USDT",
                free=Decimal("1000"),
                locked=Decimal("25"),
                updated_at=_dt(1, 5),
            ),
            AssetBalanceSnapshot(
                asset="BTC",
                delta=Decimal("0.01"),
                updated_at=_dt(1, 5),
            ),
        ),
        source_event_type="outboundAccountPosition",
        translation_version="binance.private.v1",
        is_partial=False,
    )

    assert snapshot.balances[0].free == Decimal("1000")
    assert snapshot.balances[1].delta == Decimal("0.01")


def test_decision_context_signal_and_risk_flow_example() -> None:
    instrument = Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )
    candle = Candle(
        instrument_id="BTC-USDT",
        timeframe="15m",
        open_time=_dt(2, 0),
        close_time=_dt(2, 15),
        open=Decimal("101"),
        high=Decimal("106"),
        low=Decimal("100"),
        close=Decimal("105"),
        volume=Decimal("25"),
        trade_count=50,
    )
    bars = BarSlice(
        instrument_id="BTC-USDT",
        timeframe="15m",
        end_time=_dt(2, 15),
        candles=(candle,),
    )
    features = FeatureSnapshot(
        instrument_id="BTC-USDT",
        timeframe="15m",
        as_of=_dt(2, 15),
        feature_values={"breakout_score": Decimal("0.74")},
        source_bar_count=20,
        is_complete=True,
    )
    portfolio = PortfolioState(
        as_of=_dt(2, 15),
        cash_by_asset={"USDT": Decimal("10000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0.1")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("98000")},
        realized_pnl=Decimal("150"),
        unrealized_pnl=Decimal("20"),
        gross_exposure=Decimal("10500"),
        net_exposure=Decimal("10500"),
    )
    context = DecisionContext(
        cycle_id="cycle-001",
        as_of=_dt(2, 15),
        instrument=instrument,
        latest_candle=candle,
        bar_slice=bars,
        features=features,
        portfolio_state=portfolio,
    )
    signal = SignalDecision(
        strategy_name="breakout_v1",
        instrument_id="BTC-USDT",
        timeframe="15m",
        as_of=_dt(2, 15),
        side=SignalSide.BUY,
        confidence=Decimal("0.82"),
        rationale="breakout above range high",
        target_notional=Decimal("2500"),
    )
    risk = RiskDecision(
        signal=signal,
        status=RiskDecisionStatus.ALLOW,
        evaluated_at=_dt(2, 15),
        reasons=("within portfolio limits",),
        approved_notional=Decimal("2500"),
        rule_hits=("max_symbol_exposure",),
    )

    assert context.features.feature_values["breakout_score"] == Decimal("0.74")
    assert risk.status is RiskDecisionStatus.ALLOW


def test_execution_order_fill_and_cycle_result_example() -> None:
    signal = SignalDecision(
        strategy_name="pullback_v1",
        instrument_id="ETH-USDT",
        timeframe="5m",
        as_of=_dt(3, 5),
        side=SignalSide.SELL,
        confidence=Decimal("0.65"),
        rationale="mean reversion signal exhausted",
        target_quantity=Decimal("0.5"),
    )
    risk = RiskDecision(
        signal=signal,
        status=RiskDecisionStatus.ADJUST,
        evaluated_at=_dt(3, 5),
        reasons=("reduced size due to concentration",),
        approved_quantity=Decimal("0.25"),
    )
    intent = ExecutionIntent(
        intent_id="intent-001",
        venue="upbit",
        instrument_id="ETH-USDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        quantity=Decimal("0.25"),
        limit_price=Decimal("3100"),
        submitted_at=_dt(3, 5),
        source_strategy="pullback_v1",
        rationale="risk-adjusted pullback exit",
    )
    order = OrderState(
        venue="upbit",
        order_id="order-001",
        client_order_id="client-001",
        instrument_id="ETH-USDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PARTIALLY_FILLED,
        requested_quantity=Decimal("0.25"),
        filled_quantity=Decimal("0.10"),
        remaining_quantity=Decimal("0.15"),
        limit_price=Decimal("3100"),
        average_fill_price=Decimal("3101"),
        last_update_time=_dt(3, 6),
    )
    fill = FillEvent(
        venue="upbit",
        order_id="order-001",
        fill_id="fill-001",
        instrument_id="ETH-USDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.10"),
        price=Decimal("3101"),
        fee=Decimal("0.31"),
        fee_asset="USDT",
        occurred_at=_dt(3, 6),
        liquidity_role=LiquidityRole.MAKER,
    )
    cycle = RuntimeCycleResult(
        cycle_id="cycle-002",
        started_at=_dt(3, 5),
        completed_at=_dt(3, 6),
        processed_instruments=("ETH-USDT",),
        signals=(signal,),
        risk_decisions=(risk,),
        execution_intents=(intent,),
        alerts=(),
        success=True,
    )

    assert order.filled_quantity == fill.quantity
    assert cycle.execution_intents[0].venue == "upbit"


def test_execution_intent_requires_limit_price_for_limit_orders() -> None:
    with pytest.raises(ValueError, match="limit_price is required"):
        ExecutionIntent(
            intent_id="intent-002",
            venue="binance",
            instrument_id="BTC-USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            quantity=Decimal("0.01"),
            submitted_at=_dt(4, 0),
            source_strategy="breakout_v1",
            rationale="missing limit price should fail",
        )


def test_position_state_constructor() -> None:
    position = PositionState(
        instrument_id="BTC-USDT",
        quantity=Decimal("1.25"),
        average_entry_price=Decimal("100"),
        mark_price=Decimal("110"),
        market_value=Decimal("137.5"),
        unrealized_pnl=Decimal("12.5"),
    )

    assert position.instrument_id == "BTC-USDT"
    assert position.mark_price == Decimal("110")
