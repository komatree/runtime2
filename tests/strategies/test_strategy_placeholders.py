"""Strategy layer baseline tests.

TODO:
- Add router conflict-resolution policies when ranking rules are defined.
- Add richer regime-context coverage once structured regime contracts exist.
"""

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import SignalSide
from app.strategies.base import Strategy
from app.strategies.breakout import BreakoutStrategy
from app.strategies.regime import RegimeStrategy
from app.strategies.router import StrategyRouter


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 12, hour, minute, tzinfo=UTC)


def _context(feature_values: dict[str, Decimal]) -> DecisionContext:
    instrument = Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )
    candle = Candle(
        instrument_id="BTC-USDT",
        timeframe="5m",
        open_time=_dt(1, 0),
        close_time=_dt(1, 5),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=Decimal("20"),
        is_closed=True,
    )
    return DecisionContext(
        cycle_id="cycle-001",
        as_of=_dt(1, 5),
        instrument=instrument,
        latest_candle=candle,
        bar_slice=BarSlice(
            instrument_id="BTC-USDT",
            timeframe="5m",
            end_time=_dt(1, 5),
            candles=(candle,),
        ),
        features=FeatureSnapshot(
            instrument_id="BTC-USDT",
            timeframe="5m",
            as_of=_dt(1, 5),
            feature_values=feature_values,
            source_bar_count=1,
            is_complete=True,
        ),
        portfolio_state=PortfolioState(
            as_of=_dt(1, 5),
            cash_by_asset={"USDT": Decimal("5000")},
            position_qty_by_instrument={"BTC-USDT": Decimal("0")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
    )


def test_strategy_interface_contract() -> None:
    strategy: Strategy = BreakoutStrategy()
    results = strategy.evaluate(_context({"candle.close_return_1": Decimal("0.00")}))

    assert isinstance(results, tuple)


def test_breakout_placeholder_output_shape() -> None:
    strategy = BreakoutStrategy(breakout_threshold=Decimal("0.01"))
    results = strategy.evaluate(
        _context(
            {
                "candle.close_return_1": Decimal("0.03"),
                "breakout.score": Decimal("0.70"),
            }
        )
    )

    assert len(results) == 1
    assert results[0].strategy_name == "breakout"
    assert results[0].side is SignalSide.BUY
    assert results[0].target_quantity == Decimal("1")


def test_regime_output_shape() -> None:
    strategy = RegimeStrategy()
    results = strategy.evaluate(
        _context(
            {
                "candle.close_return_1": Decimal("0.01"),
                "index_suite.value": Decimal("60"),
            }
        )
    )

    assert len(results) == 1
    assert results[0].strategy_name == "regime"
    assert results[0].side is SignalSide.FLAT
    assert "regime_state=risk_on" in results[0].rationale


def test_router_composition_behavior() -> None:
    router = StrategyRouter(
        strategies=(
            BreakoutStrategy(breakout_threshold=Decimal("0.01")),
            RegimeStrategy(),
        ),
        include_flat_signals=True,
    )
    results = router.evaluate(
        _context(
            {
                "candle.close_return_1": Decimal("0.03"),
                "breakout.score": Decimal("0.80"),
                "index_suite.value": Decimal("55"),
            }
        )
    )

    assert len(results) == 2
    assert {result.strategy_name for result in results} == {"breakout", "regime"}
