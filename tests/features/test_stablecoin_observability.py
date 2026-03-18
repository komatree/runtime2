"""Stablecoin observability report-only tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import StablecoinSnapshot
from app.features.stablecoin import InMemoryStablecoinSnapshotRepository
from app.features.stablecoin import ReadOnlyStablecoinSnapshotProvider
from app.features.stablecoin import StablecoinFeatureService
from app.features.stablecoin import StablecoinObservabilityCollector
from app.features.stablecoin import StablecoinSnapshotStatus
from app.storage import StablecoinSnapshotStorage


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)


def _snapshot(*, fresh_until: datetime) -> StablecoinSnapshot:
    return StablecoinSnapshot(
        pair="USDT-USD",
        reference_asset="USD",
        snapshot_version="obs.v1",
        source_type="report_only_ingest",
        as_of=_dt(0, 0),
        source_fresh_until=fresh_until,
        stablecoin_net_mint_24h=Decimal("1000000"),
        stablecoin_net_burn_24h=Decimal("300000"),
        stablecoin_supply_change_pct_24h=Decimal("0.35"),
        stablecoin_chain_supply_delta_24h=Decimal("700000"),
        stablecoin_abnormal_transfer_count=4,
        price=Decimal("1.0001"),
        premium_bps=Decimal("1"),
    )


def _bar_slice() -> BarSlice:
    candle = Candle(
        instrument_id="BTC-USDT",
        timeframe="4h",
        open_time=_dt(0, 0),
        close_time=_dt(4, 0),
        open=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("99"),
        close=Decimal("103"),
        volume=Decimal("10"),
        is_closed=True,
    )
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="4h",
        end_time=_dt(4, 0),
        candles=(candle,),
    )


def test_stablecoin_schema_validation() -> None:
    snapshot = _snapshot(fresh_until=_dt(6, 0))

    assert snapshot.stablecoin_net_mint_24h == Decimal("1000000")
    assert snapshot.source_type == "report_only_ingest"


def test_stablecoin_append_only_storage(tmp_path: Path) -> None:
    storage = StablecoinSnapshotStorage(
        jsonl_path=tmp_path / "stablecoin.jsonl",
        csv_path=tmp_path / "stablecoin.csv",
        markdown_path=tmp_path / "stablecoin.md",
    )
    collector = StablecoinObservabilityCollector(storage=storage)

    collector.ingest(_snapshot(fresh_until=_dt(6, 0)))
    collector.ingest(_snapshot(fresh_until=_dt(7, 0)))

    jsonl_lines = (tmp_path / "stablecoin.jsonl").read_text(encoding="utf-8").strip().splitlines()
    csv_lines = (tmp_path / "stablecoin.csv").read_text(encoding="utf-8").strip().splitlines()
    markdown_text = (tmp_path / "stablecoin.md").read_text(encoding="utf-8")

    assert len(jsonl_lines) == 2
    assert len(csv_lines) == 3
    assert "Stablecoin Observability Summary" in markdown_text
    assert storage.read_latest() is not None


def test_stablecoin_optional_feature_inclusion(tmp_path: Path) -> None:
    repository = InMemoryStablecoinSnapshotRepository(snapshots=(_snapshot(fresh_until=_dt(6, 0)),))
    provider = ReadOnlyStablecoinSnapshotProvider(repository=repository)
    service = StablecoinFeatureService()
    bar_slice = _bar_slice()

    ok = provider.resolve_snapshot(as_of=_dt(4, 0))
    stale = provider.resolve_snapshot(as_of=_dt(8, 0))
    present_bundle = service.build(bar_slice=bar_slice, stablecoin_snapshot=provider.get_snapshot(as_of=_dt(4, 0)))
    missing_bundle = service.build(bar_slice=bar_slice, stablecoin_snapshot=provider.get_snapshot(as_of=_dt(8, 0)))

    assert ok.status is StablecoinSnapshotStatus.OK
    assert stale.status is StablecoinSnapshotStatus.STALE
    assert present_bundle.feature_values["stablecoin.net_mint_24h"] == Decimal("1000000")
    assert present_bundle.feature_values["stablecoin.source_fresh"] == Decimal("1")
    assert missing_bundle.missing_inputs == ("stablecoin_snapshot",)
