"""Paper-mode integration tests.

TODO:
- Add sell-side and realized-PnL coverage once more strategies are active.
- Add multi-instrument paper portfolio accounting when phase-1 expands.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.execution import ReportOnlyExecutionIntentBuilder
from app.runtime import PaperRunner
from app.runtime import PaperSessionResult
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.storage import JsonlPaperStatePersistenceGateway


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


def _bar_slice(close_price: str) -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(0, 2),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 1),
                close_time=_dt(0, 2),
                open=Decimal("100"),
                high=Decimal(close_price),
                low=Decimal("99.5"),
                close=Decimal(close_price),
                volume=Decimal("10"),
                is_closed=True,
            ),
        ),
    )


def _portfolio(cash: str = "1000", qty: str = "0") -> PortfolioState:
    return PortfolioState(
        as_of=_dt(0, 1),
        cash_by_asset={"USDT": Decimal(cash)},
        position_qty_by_instrument={"BTC-USDT": Decimal(qty)},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


class _FeatureBuilder:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        self.calls.append(bar_slice.end_time)
        return FeatureSnapshot(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            feature_values={
                "candle.close_return_1": (bar_slice.candles[-1].close - bar_slice.candles[-1].open)
                / bar_slice.candles[-1].open
            },
            source_bar_count=len(bar_slice.candles),
            is_complete=True,
        )


class _StrategyEvaluator:
    def __init__(self, plan: dict[str, SignalSide]) -> None:
        self.plan = plan

    def evaluate(self, context):
        planned_side = self.plan.get(context.cycle_id)
        if planned_side is None:
            return ()
        return (
            SignalDecision(
                strategy_name="breakout",
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=planned_side,
                confidence=Decimal("0.75"),
                rationale="paper action test",
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
                reasons=("paper allow",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class _PersistenceGateway:
    def __init__(self) -> None:
        self.persisted = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.persisted.append((cycle_result, features, context, exchange_health))


def _context(action: bool) -> RuntimeContext:
    plan = {}
    if action:
        plan = {
            "paper-002": SignalSide.BUY,
            "paper-003": SignalSide.BUY,
            "paper-004a": SignalSide.BUY,
            "paper-004b": SignalSide.BUY,
            "paper-enter": SignalSide.BUY,
            "paper-exit": SignalSide.SELL,
        }
    feature_builder = _FeatureBuilder()
    return RuntimeContext(
        mode=RunnerMode.PAPER,
        feature_builder=feature_builder,
        strategy_evaluator=_StrategyEvaluator(plan=plan),
        risk_evaluator=_RiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=_PersistenceGateway(),
        execution_venue="binance",
    )


def _read_state_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_paper_no_action_cycle(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    runner = PaperRunner(
        _context(action=False),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(state_path),
    )
    outcome = runner.run_cycle(
        cycle_id="paper-001",
        instrument=_instrument(),
        bar_slice=_bar_slice("100"),
        portfolio_state=_portfolio(),
    )

    assert outcome.cycle_result.success is True
    assert outcome.cycle_result.execution_intents == ()
    assert outcome.order_states == ()
    assert outcome.ending_portfolio_state == outcome.starting_portfolio_state
    assert outcome.ending_position_states[0].quantity == Decimal("0")
    assert len(_read_state_rows(state_path)) == 1


def test_paper_action_cycle(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    runner = PaperRunner(
        _context(action=True),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(state_path),
    )
    outcome = runner.run_cycle(
        cycle_id="paper-002",
        instrument=_instrument(),
        bar_slice=_bar_slice("103"),
        portfolio_state=_portfolio(),
    )

    assert len(outcome.cycle_result.execution_intents) == 1
    assert len(outcome.order_states) == 1
    assert len(outcome.fill_events) == 1
    assert outcome.order_states[0].status.value == "filled"
    assert outcome.fill_events[0].price == Decimal("103")
    assert outcome.ending_position_states[0].quantity == Decimal("1")


def test_paper_portfolio_state_transition(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    runner = PaperRunner(
        _context(action=True),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(state_path),
    )
    outcome = runner.run_cycle(
        cycle_id="paper-003",
        instrument=_instrument(),
        bar_slice=_bar_slice("103"),
        portfolio_state=_portfolio(cash="1000", qty="0"),
    )

    assert outcome.ending_portfolio_state.cash_by_asset["USDT"] == Decimal("897")
    assert outcome.ending_portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert outcome.ending_portfolio_state.average_entry_price_by_instrument["BTC-USDT"] == Decimal("103")
    assert outcome.ending_portfolio_state.gross_exposure == Decimal("103")


def test_paper_multiple_cycle_continuity(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    runner = PaperRunner(
        _context(action=True),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(state_path),
    )
    first = runner.run_cycle(
        cycle_id="paper-004a",
        instrument=_instrument(),
        bar_slice=_bar_slice("103"),
        portfolio_state=_portfolio(cash="1000", qty="0"),
    )
    second = runner.run_cycle(
        cycle_id="paper-004b",
        instrument=_instrument(),
        bar_slice=_bar_slice("104"),
        portfolio_state=first.ending_portfolio_state,
    )

    rows = _read_state_rows(state_path)
    assert second.ending_portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("2")
    assert second.ending_portfolio_state.cash_by_asset["USDT"] == Decimal("793")
    assert len(rows) == 2
    assert rows[0]["cycle_id"] == "paper-004a"
    assert rows[1]["cycle_id"] == "paper-004b"


def test_paper_multi_cycle_no_action_continuity(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    summary_path = tmp_path / "paper_summary.jsonl"
    runner = PaperRunner(
        _context(action=False),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(
            output_path=state_path,
            summary_output_path=summary_path,
        ),
    )

    session = runner.run_cycles(
        session_id="paper-session-no-action",
        instrument=_instrument(),
        cycle_inputs=(
            ("paper-na-1", _bar_slice_at(close_price="100", end_hour=0, end_minute=2)),
            ("paper-na-2", _bar_slice_at(close_price="101", end_hour=0, end_minute=3)),
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert isinstance(session, PaperSessionResult)
    assert session.final_portfolio_state == _portfolio()
    assert all(not outcome.order_states for outcome in session.cycle_outcomes)
    summary_rows = _read_state_rows(summary_path)
    assert summary_rows[0]["total_cycles"] == 2
    assert summary_rows[0]["action_cycle_count"] == 0


def test_paper_enter_hold_exit_continuity(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    summary_path = tmp_path / "paper_summary.jsonl"
    runner = PaperRunner(
        _context(action=True),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(
            output_path=state_path,
            summary_output_path=summary_path,
        ),
    )

    session = runner.run_cycles(
        session_id="paper-session-ehe",
        instrument=_instrument(),
        cycle_inputs=(
            ("paper-enter", _bar_slice_at(close_price="103", end_hour=0, end_minute=2)),
            ("paper-hold", _bar_slice_at(close_price="104", end_hour=0, end_minute=3)),
            ("paper-exit", _bar_slice_at(close_price="105", end_hour=0, end_minute=4)),
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert session.cycle_outcomes[0].ending_position_states[0].quantity == Decimal("1")
    assert session.cycle_outcomes[1].ending_position_states[0].quantity == Decimal("1")
    assert session.cycle_outcomes[2].ending_position_states[0].quantity == Decimal("0")
    assert session.final_portfolio_state.cash_by_asset["USDT"] == Decimal("1002")


def test_repeated_feature_snapshot_updates() -> None:
    context = _context(action=False)
    runner = PaperRunner(context)

    runner.run_cycles(
        session_id="paper-session-features",
        instrument=_instrument(),
        cycle_inputs=(
            ("paper-f-1", _bar_slice_at(close_price="100", end_hour=0, end_minute=2)),
            ("paper-f-2", _bar_slice_at(close_price="102", end_hour=0, end_minute=3)),
            ("paper-f-3", _bar_slice_at(close_price="104", end_hour=0, end_minute=4)),
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert context.feature_builder.calls == [_dt(0, 2), _dt(0, 3), _dt(0, 4)]


def test_portfolio_state_integrity_after_multiple_cycles(tmp_path: Path) -> None:
    state_path = tmp_path / "paper_state.jsonl"
    runner = PaperRunner(
        _context(action=True),
        state_persistence_gateway=JsonlPaperStatePersistenceGateway(output_path=state_path),
    )

    session = runner.run_cycles(
        session_id="paper-session-integrity",
        instrument=_instrument(),
        cycle_inputs=(
            ("paper-enter", _bar_slice_at(close_price="103", end_hour=0, end_minute=2)),
            ("paper-hold", _bar_slice_at(close_price="104", end_hour=0, end_minute=3)),
            ("paper-exit", _bar_slice_at(close_price="105", end_hour=0, end_minute=4)),
        ),
        initial_portfolio_state=_portfolio(),
    )

    assert session.final_portfolio_state.gross_exposure == Decimal("0")
    assert session.final_portfolio_state.net_exposure == Decimal("0")
    assert session.final_portfolio_state.unrealized_pnl == Decimal("0")
    assert session.final_position_states[0].market_value == Decimal("0")


def _bar_slice_at(*, close_price: str, end_hour: int, end_minute: int) -> BarSlice:
    end_time = _dt(end_hour, end_minute)
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=end_time,
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(end_hour, end_minute - 1),
                close_time=end_time,
                open=Decimal("100"),
                high=Decimal(close_price),
                low=Decimal("99.5"),
                close=Decimal(close_price),
                volume=Decimal("10"),
                is_closed=True,
            ),
        ),
    )
