"""Report-only persistence schema tests.

TODO:
- Hydrate full typed read models if JSONL becomes an operator-facing query source.
- Add SQLite migration parity tests if the provisional backend changes.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import IndexSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import RuntimeCycleResult
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.storage import JsonlReportCycleRepository
from app.storage import ReportCycleSerializer


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)


def _build_parts(*, include_optional_features: bool) -> tuple[FeatureSnapshot, DecisionContext, RuntimeCycleResult]:
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
        open_time=_dt(0, 0),
        close_time=_dt(0, 1),
        open=Decimal("100"),
        high=Decimal("103"),
        low=Decimal("99"),
        close=Decimal("102"),
        volume=Decimal("15"),
        is_closed=True,
    )
    feature_values = {
        "candle.close": Decimal("102"),
        "candle.close_return_1": Decimal("0.02"),
    }
    if include_optional_features:
        feature_values["index_suite.value"] = Decimal("60")
        feature_values["stablecoin.price"] = Decimal("1.0001")
    features = FeatureSnapshot(
        instrument_id="BTC-USDT",
        timeframe="1m",
        as_of=_dt(0, 1),
        feature_values=feature_values,
        source_bar_count=2,
        is_complete=True,
    )
    context = DecisionContext(
        cycle_id="cycle-persist-001",
        as_of=_dt(0, 1),
        instrument=instrument,
        latest_candle=candle,
        bar_slice=BarSlice(
            instrument_id="BTC-USDT",
            timeframe="1m",
            end_time=_dt(0, 1),
            candles=(candle,),
        ),
        features=features,
        portfolio_state=PortfolioState(
            as_of=_dt(0, 1),
            cash_by_asset={"USDT": Decimal("5000")},
            position_qty_by_instrument={"BTC-USDT": Decimal("0")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
        index_snapshot=(
            IndexSnapshot(
                name="risk-on",
                instrument_id="BTC-USDT",
                index_version="v1",
                as_of=_dt(0, 1),
                value=Decimal("60"),
                constituents=("BTC-USDT",),
                methodology="breadth",
            )
            if include_optional_features
            else None
        ),
        index_snapshot_status="ok" if include_optional_features else "missing",
        index_snapshot_detail=None if include_optional_features else "no snapshot found for instrument and date",
        index_snapshot_requested_version="v1",
    )
    signal = SignalDecision(
        strategy_name="breakout",
        instrument_id="BTC-USDT",
        timeframe="1m",
        as_of=_dt(0, 1),
        side=SignalSide.BUY,
        confidence=Decimal("0.7"),
        rationale="serialization test",
        target_quantity=Decimal("1"),
    )
    risk = RiskDecision(
        signal=signal,
        status=RiskDecisionStatus.ALLOW,
        evaluated_at=_dt(0, 1),
        reasons=("allow",),
        approved_quantity=Decimal("1"),
    )
    cycle = RuntimeCycleResult(
        cycle_id="cycle-persist-001",
        started_at=_dt(0, 1),
        completed_at=_dt(0, 1),
        processed_instruments=("BTC-USDT",),
        signals=(signal,),
        risk_decisions=(risk,),
        execution_intents=(),
        alerts=("none",),
        success=True,
    )
    return features, context, cycle


def test_report_cycle_serialization_round_trip(tmp_path) -> None:
    serializer = ReportCycleSerializer()
    repository = JsonlReportCycleRepository(tmp_path / "reports.jsonl", serializer)
    features, context, cycle = _build_parts(include_optional_features=True)

    record = serializer.build_record(
        cycle_result=cycle,
        features=features,
        context=context,
        recorded_at=_dt(0, 1),
    )
    repository.append(record)
    rows = repository.read_all()

    assert len(rows) == 1
    assert rows[0]["schema_version"] == "report_cycle.v1"
    assert rows[0]["instrument_id"] == "BTC-USDT"
    assert rows[0]["feature_snapshot_summary"]["feature_count"] == 4
    assert rows[0]["index_suite_context"]["requested_index_version"] == "v1"


def test_report_cycle_serializer_handles_missing_optional_feature_fields() -> None:
    serializer = ReportCycleSerializer()
    features, context, cycle = _build_parts(include_optional_features=False)

    record = serializer.to_dict(
        serializer.build_record(
            cycle_result=cycle,
            features=features,
            context=context,
            recorded_at=_dt(0, 1),
        )
    )

    assert record["feature_snapshot_summary"]["index_features"] is None
    assert record["feature_snapshot_summary"]["stablecoin_features"] is None
    assert record["decision_context_summary"]["has_index_snapshot"] is False
    assert record["index_suite_context"]["status"] == "missing"


def test_report_cycle_schema_shape_is_stable() -> None:
    serializer = ReportCycleSerializer()
    features, context, cycle = _build_parts(include_optional_features=True)

    payload = serializer.to_dict(
        serializer.build_record(
            cycle_result=cycle,
            features=features,
            context=context,
            recorded_at=_dt(0, 1),
        )
    )

    assert sorted(payload.keys()) == [
        "bar_close_time",
        "cycle_timestamp",
        "decision_context_summary",
        "execution_intents",
        "feature_snapshot_summary",
        "index_suite_context",
        "instrument_id",
        "recorded_at",
        "risk_decisions",
        "runtime_cycle_result",
        "schema_version",
        "signal_decisions",
        "timeframe",
    ]
