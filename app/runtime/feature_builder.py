"""Shared feature builder for runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import FeatureSnapshot
from app.features.base import FeatureComposer
from app.features.candle import CandleFeatureService
from app.features.index_suite import IndexSuiteFeatureService
from app.features.stablecoin import StablecoinFeatureService

from .runtime_context import IndexSnapshotProvider
from .runtime_context import StablecoinSnapshotProvider


@dataclass(frozen=True)
class RuntimeFeatureBuilder:
    """Composes feature services into one strategy-facing snapshot."""

    candle_service: CandleFeatureService
    index_suite_service: IndexSuiteFeatureService
    stablecoin_service: StablecoinFeatureService
    composer: FeatureComposer
    index_snapshot_provider: IndexSnapshotProvider | None = None
    stablecoin_snapshot_provider: StablecoinSnapshotProvider | None = None

    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        """Build a unified feature snapshot for one bar-close event."""

        index_snapshot = None
        index_lookup_result = None
        if self.index_snapshot_provider is not None:
            if hasattr(self.index_snapshot_provider, "resolve_snapshot"):
                index_lookup_result = self.index_snapshot_provider.resolve_snapshot(
                    instrument_id=bar_slice.instrument_id,
                    as_of=bar_slice.end_time,
                )
                index_snapshot = index_lookup_result.snapshot if index_lookup_result.status.value == "ok" else None
            else:
                index_snapshot = self.index_snapshot_provider.get_snapshot(
                    instrument_id=bar_slice.instrument_id,
                    as_of=bar_slice.end_time,
                )
        stablecoin_snapshot = None
        if self.stablecoin_snapshot_provider is not None:
            stablecoin_snapshot = self.stablecoin_snapshot_provider.get_snapshot(as_of=bar_slice.end_time)

        bundles = (
            self.candle_service.build(
                bar_slice=bar_slice,
                index_snapshot=index_snapshot,
                stablecoin_snapshot=stablecoin_snapshot,
            ),
            self.index_suite_service.build(
                bar_slice=bar_slice,
                index_snapshot=index_snapshot,
                stablecoin_snapshot=stablecoin_snapshot,
            ),
            self.stablecoin_service.build(
                bar_slice=bar_slice,
                index_snapshot=index_snapshot,
                stablecoin_snapshot=stablecoin_snapshot,
            ),
        )
        snapshot = self.composer.compose(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            bundles=bundles,
        )
        enriched = dict(snapshot.feature_values)
        if index_lookup_result is not None:
            enriched["index_suite.snapshot_present"] = (
                Decimal("1") if index_lookup_result.status.value == "ok" else Decimal("0")
            )
            enriched["index_suite.snapshot_stale"] = (
                Decimal("1") if index_lookup_result.status.value == "stale" else Decimal("0")
            )
            enriched["index_suite.snapshot_version_match"] = (
                Decimal("0") if index_lookup_result.status.value == "version_mismatch" else Decimal("1")
            )
            if index_lookup_result.snapshot is not None:
                enriched["index_suite.snapshot_age_seconds"] = Decimal(
                    str(int((bar_slice.end_time - index_lookup_result.snapshot.as_of).total_seconds()))
                )
        if context_bar_slice is None:
            return FeatureSnapshot(
                instrument_id=snapshot.instrument_id,
                timeframe=snapshot.timeframe,
                as_of=snapshot.as_of,
                feature_values=enriched,
                source_bar_count=snapshot.source_bar_count,
                is_complete=snapshot.is_complete,
            )

        context_latest = context_bar_slice.candles[-1]
        previous_context = context_bar_slice.candles[-2] if len(context_bar_slice.candles) > 1 else context_latest
        context_return = context_latest.close - previous_context.close
        enriched["context.1d.close"] = context_latest.close
        enriched["context.1d.close_delta_1"] = context_return
        return FeatureSnapshot(
            instrument_id=snapshot.instrument_id,
            timeframe=snapshot.timeframe,
            as_of=snapshot.as_of,
            feature_values=enriched,
            source_bar_count=max(snapshot.source_bar_count, len(context_bar_slice.candles)),
            is_complete=snapshot.is_complete and context_latest.is_closed,
        )
