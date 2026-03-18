"""Feature layer baseline tests.

TODO:
- Add edge cases for stale snapshots and incomplete auxiliary data.
- Add runtime-level feature builder composition tests once wired in.
"""

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import IndexSnapshot
from app.contracts import StablecoinSnapshot
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import IndexSuiteFeatureService
from app.features.stablecoin import StablecoinFeatureService


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 12, hour, minute, tzinfo=UTC)


def _bar_slice() -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="5m",
        end_time=_dt(1, 10),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="5m",
                open_time=_dt(1, 0),
                close_time=_dt(1, 5),
                open=Decimal("100"),
                high=Decimal("103"),
                low=Decimal("99"),
                close=Decimal("102"),
                volume=Decimal("15"),
                is_closed=True,
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="5m",
                open_time=_dt(1, 5),
                close_time=_dt(1, 10),
                open=Decimal("102"),
                high=Decimal("106"),
                low=Decimal("101"),
                close=Decimal("105"),
                volume=Decimal("18"),
                is_closed=True,
            ),
        ),
    )


def test_feature_snapshot_composition() -> None:
    bar_slice = _bar_slice()
    candle_bundle = CandleFeatureService().build(bar_slice=bar_slice)
    index_bundle = IndexSuiteFeatureService().build(
        bar_slice=bar_slice,
        index_snapshot=IndexSnapshot(
            name="risk-on",
            instrument_id="BTC-USDT",
            index_version="v1",
            as_of=bar_slice.end_time,
            value=Decimal("55"),
            constituents=("BTC-USDT", "ETH-USDT"),
            methodology="breadth",
        ),
    )
    stable_bundle = StablecoinFeatureService().build(
        bar_slice=bar_slice,
        stablecoin_snapshot=StablecoinSnapshot(
            pair="USDT-USD",
            reference_asset="USD",
            snapshot_version="obs.v1",
            source_type="report_only_ingest",
            as_of=bar_slice.end_time,
            source_fresh_until=_dt(1, 20),
            stablecoin_net_mint_24h=Decimal("1000000"),
            stablecoin_net_burn_24h=Decimal("250000"),
            stablecoin_supply_change_pct_24h=Decimal("0.20"),
            stablecoin_chain_supply_delta_24h=Decimal("750000"),
            stablecoin_abnormal_transfer_count=2,
            price=Decimal("1.0002"),
            premium_bps=Decimal("2"),
            volume_24h=Decimal("120000000"),
            liquidity_score=Decimal("0.93"),
            is_depegged=False,
        ),
    )

    snapshot = FeatureComposer(tolerate_partial=True).compose(
        instrument_id=bar_slice.instrument_id,
        timeframe=bar_slice.timeframe,
        as_of=bar_slice.end_time,
        bundles=(candle_bundle, index_bundle, stable_bundle),
    )

    assert snapshot.feature_values["candle.close"] == Decimal("105")
    assert snapshot.feature_values["index_suite.value"] == Decimal("55")
    assert snapshot.feature_values["stablecoin.premium_bps"] == Decimal("2")
    assert snapshot.feature_values["stablecoin.net_mint_24h"] == Decimal("1000000")
    assert snapshot.source_bar_count == 2


def test_missing_partial_feature_tolerance() -> None:
    bar_slice = _bar_slice()
    candle_bundle = CandleFeatureService().build(bar_slice=bar_slice)
    missing_index_bundle = IndexSuiteFeatureService().build(bar_slice=bar_slice)

    snapshot = FeatureComposer(tolerate_partial=True).compose(
        instrument_id=bar_slice.instrument_id,
        timeframe=bar_slice.timeframe,
        as_of=bar_slice.end_time,
        bundles=(candle_bundle, missing_index_bundle),
    )

    assert snapshot.is_complete is True
    assert "index_suite.value" not in snapshot.feature_values
    assert snapshot.feature_values["candle.is_closed"] == Decimal("1")


def test_index_suite_read_only_stub_behavior() -> None:
    bar_slice = _bar_slice()
    service = IndexSuiteFeatureService()

    missing = service.build(bar_slice=bar_slice)
    present = service.build(
        bar_slice=bar_slice,
        index_snapshot=IndexSnapshot(
            name="risk-off",
            instrument_id="BTC-USDT",
            index_version="v1",
            as_of=bar_slice.end_time,
            value=Decimal("32"),
            constituents=("BTC-USDT",),
            methodology="defensive breadth",
        ),
    )

    assert missing.is_complete is False
    assert missing.missing_inputs == ("index_snapshot",)
    assert present.feature_values["index_suite.constituent_count"] == Decimal("1")
    assert present.feature_values["index_suite.version_present"] == Decimal("1")


def test_stablecoin_snapshot_stub_behavior() -> None:
    bar_slice = _bar_slice()
    service = StablecoinFeatureService()

    missing = service.build(bar_slice=bar_slice)
    present = service.build(
        bar_slice=bar_slice,
        stablecoin_snapshot=StablecoinSnapshot(
            pair="USDC-USD",
            reference_asset="USD",
            snapshot_version="obs.v1",
            source_type="report_only_ingest",
            as_of=bar_slice.end_time,
            source_fresh_until=_dt(1, 20),
            stablecoin_net_mint_24h=Decimal("500000"),
            stablecoin_net_burn_24h=Decimal("100000"),
            stablecoin_supply_change_pct_24h=Decimal("-0.10"),
            stablecoin_chain_supply_delta_24h=Decimal("-250000"),
            stablecoin_abnormal_transfer_count=7,
            price=Decimal("0.998"),
            premium_bps=Decimal("-20"),
            volume_24h=Decimal("90000000"),
            liquidity_score=Decimal("0.80"),
            is_depegged=True,
        ),
    )

    assert missing.is_complete is False
    assert missing.missing_inputs == ("stablecoin_snapshot",)
    assert present.feature_values["stablecoin.is_depegged"] == Decimal("1")
    assert present.feature_values["stablecoin.abnormal_transfer_count"] == Decimal("7")
