"""Read-only Index Suite repository and provider tests."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import IndexSnapshot
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import InMemoryIndexSuiteRepository
from app.features.index_suite import IndexSuiteFeatureService
from app.features.index_suite import IndexSuiteLookupStatus
from app.features.index_suite import ReadOnlyIndexSuiteProvider
from app.features.stablecoin import StablecoinFeatureService
from app.runtime import RuntimeFeatureBuilder


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, tzinfo=UTC)


def _snapshot(as_of: datetime, version: str = "v1") -> IndexSnapshot:
    return IndexSnapshot(
        name="risk-on",
        instrument_id="BTC-USDT",
        index_version=version,
        as_of=as_of,
        value=Decimal("55"),
        constituents=("BTC-USDT", "ETH-USDT"),
        methodology="breadth",
    )


def _bar_slice() -> BarSlice:
    candle_1 = Candle(
        instrument_id="BTC-USDT",
        timeframe="4h",
        open_time=_dt(12, 0),
        close_time=_dt(12, 4),
        open=Decimal("100"),
        high=Decimal("103"),
        low=Decimal("99"),
        close=Decimal("102"),
        volume=Decimal("10"),
        is_closed=True,
    )
    candle_2 = Candle(
        instrument_id="BTC-USDT",
        timeframe="4h",
        open_time=_dt(12, 4),
        close_time=_dt(12, 8),
        open=Decimal("102"),
        high=Decimal("106"),
        low=Decimal("101"),
        close=Decimal("105"),
        volume=Decimal("12"),
        is_closed=True,
    )
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="4h",
        end_time=_dt(12, 8),
        candles=(candle_1, candle_2),
    )


def test_successful_snapshot_lookup() -> None:
    repository = InMemoryIndexSuiteRepository(snapshots=(_snapshot(_dt(12, 7)),))
    provider = ReadOnlyIndexSuiteProvider(
        repository=repository,
        index_version="v1",
        max_snapshot_age=timedelta(hours=12),
    )

    result = provider.resolve_snapshot(instrument_id="BTC-USDT", as_of=_dt(12, 8))

    assert result.status is IndexSuiteLookupStatus.OK
    assert result.snapshot is not None
    assert result.snapshot.index_version == "v1"


def test_missing_snapshot_handling() -> None:
    repository = InMemoryIndexSuiteRepository(snapshots=())
    provider = ReadOnlyIndexSuiteProvider(
        repository=repository,
        index_version="v1",
        max_snapshot_age=timedelta(hours=12),
    )

    result = provider.resolve_snapshot(instrument_id="BTC-USDT", as_of=_dt(12, 8))

    assert result.status is IndexSuiteLookupStatus.MISSING
    assert provider.get_snapshot(instrument_id="BTC-USDT", as_of=_dt(12, 8)) is None


def test_stale_snapshot_behavior() -> None:
    repository = InMemoryIndexSuiteRepository(snapshots=(_snapshot(_dt(10, 0)),))
    provider = ReadOnlyIndexSuiteProvider(
        repository=repository,
        index_version="v1",
        max_snapshot_age=timedelta(hours=12),
    )

    result = provider.resolve_snapshot(instrument_id="BTC-USDT", as_of=_dt(12, 8))

    assert result.status is IndexSuiteLookupStatus.STALE
    assert provider.get_snapshot(instrument_id="BTC-USDT", as_of=_dt(12, 8)) is None


def test_feature_snapshot_composition_with_and_without_index_suite() -> None:
    provider = ReadOnlyIndexSuiteProvider(
        repository=InMemoryIndexSuiteRepository(snapshots=(_snapshot(_dt(12, 7)),)),
        index_version="v1",
        max_snapshot_age=timedelta(hours=12),
    )
    builder_with = RuntimeFeatureBuilder(
        candle_service=CandleFeatureService(),
        index_suite_service=IndexSuiteFeatureService(),
        stablecoin_service=StablecoinFeatureService(),
        composer=FeatureComposer(tolerate_partial=True),
        index_snapshot_provider=provider,
    )
    builder_without = RuntimeFeatureBuilder(
        candle_service=CandleFeatureService(),
        index_suite_service=IndexSuiteFeatureService(),
        stablecoin_service=StablecoinFeatureService(),
        composer=FeatureComposer(tolerate_partial=True),
    )

    with_index = builder_with.build(_bar_slice())
    without_index = builder_without.build(_bar_slice())

    assert with_index.feature_values["index_suite.value"] == Decimal("55")
    assert with_index.feature_values["index_suite.snapshot_present"] == Decimal("1")
    assert "index_suite.value" not in without_index.feature_values
