"""End-to-end report-only run with stubbed Binance kline payloads."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import Instrument
from app.contracts import PortfolioState
from app.execution import ReportOnlyExecutionIntentBuilder
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceMarketDataClient
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
from app.strategies.router import StrategyRouter


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def test_end_to_end_report_only_run_with_stubbed_real_data(tmp_path: Path) -> None:
    output_path = tmp_path / "report_only_real_data.jsonl"
    context = RuntimeContext(
        mode=RunnerMode.REPORT_ONLY,
        feature_builder=RuntimeFeatureBuilder(
            candle_service=CandleFeatureService(),
            index_suite_service=IndexSuiteFeatureService(),
            stablecoin_service=StablecoinFeatureService(),
            composer=FeatureComposer(tolerate_partial=True),
        ),
        strategy_evaluator=StrategyRouter(
            strategies=(BreakoutStrategy(breakout_threshold=Decimal("0.02")),),
            include_flat_signals=False,
        ),
        risk_evaluator=ReportOnlyRiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=JsonlReportPersistenceGateway(output_path),
        execution_venue="binance",
    )
    runner = ReportOnlyRunner(context)
    market_data_client = BinanceMarketDataClient(
        config=BinanceAdapterConfig(
            rest_base_url="https://api.binance.com",
            websocket_base_url="wss://stream.binance.com:9443",
        )
    )

    cycle = runner.run_real_data_cycle(
        cycle_id="real-data-001",
        instrument=Instrument(
            instrument_id="BTC-USDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_precision=2,
            quantity_precision=6,
        ),
        portfolio_state=PortfolioState(
            as_of=_dt(2025, 1, 2, 1),
            cash_by_asset={"USDT": Decimal("10000")},
            position_qty_by_instrument={"BTC-USDT": Decimal("0")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
        market_data_client=market_data_client,
        execution_klines=(
            [1735689600000, "100", "103", "99", "101", "10", 1735703999000, "1000", 100],
            [1735704000000, "101", "106", "100", "104", "11", 1735718399000, "1200", 110],
        ),
        context_klines=(
            [1735603200000, "95", "105", "90", "100", "100", 1735689599000, "9000", 900],
            [1735689600000, "100", "110", "98", "108", "120", 1735775999000, "10000", 950],
        ),
        reference_time=_dt(2025, 1, 2, 1),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert cycle.success is True
    assert len(cycle.execution_intents) == 1
    assert "context.1d.close" in payload["feature_snapshot_summary"]["feature_names"]
