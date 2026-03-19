"""Read-only index suite feature service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import IndexSnapshot
from app.contracts import StablecoinSnapshot

from app.features.base import FeatureBundle
from .repository import InMemoryIndexSuiteRepository
from .repository import IndexSuiteLookupResult
from .repository import IndexSuiteLookupStatus


class IndexSuiteFeatureService:
    """Adapts precomputed index snapshots into unified feature values.

    This service is intentionally read-only. It does not compute index values
    and simply maps upstream snapshots into strategy-facing feature names.
    """

    def build(
        self,
        *,
        bar_slice: BarSlice,
        index_snapshot: IndexSnapshot | None = None,
        stablecoin_snapshot: StablecoinSnapshot | None = None,
    ) -> FeatureBundle:
        """Build index-suite features from a precomputed snapshot when present."""

        if index_snapshot is None:
            return FeatureBundle(
                feature_values={},
                is_complete=False,
                source_bar_count=len(bar_slice.candles),
                missing_inputs=("index_snapshot",),
            )

        return FeatureBundle(
            feature_values={
                "index_suite.value": index_snapshot.value,
                "index_suite.constituent_count": Decimal(len(index_snapshot.constituents)),
                "index_suite.version_present": Decimal("1"),
            },
            is_complete=True,
            source_bar_count=len(bar_slice.candles),
            missing_inputs=(),
        )


@dataclass(frozen=True)
class ReadOnlyIndexSuiteProvider:
    """Read-only provider for resolving latest valid precomputed Index Suite snapshots.

    Strategies and risk must consume Index Suite only through `DecisionContext`
    and `FeatureSnapshot`, never by querying this provider directly.
    """

    repository: InMemoryIndexSuiteRepository
    index_version: str
    max_snapshot_age: timedelta

    def resolve_snapshot(self, *, instrument_id: str, as_of) -> IndexSuiteLookupResult:
        """Resolve and classify the latest valid snapshot for one decision time."""

        return self.repository.resolve_latest(
            instrument_id=instrument_id,
            as_of=as_of,
            index_version=self.index_version,
            max_snapshot_age=self.max_snapshot_age,
        )

    def get_snapshot(self, *, instrument_id: str, as_of) -> IndexSnapshot | None:
        """Return only a valid snapshot; missing/stale/mismatch resolves to `None`."""

        result = self.resolve_snapshot(instrument_id=instrument_id, as_of=as_of)
        if result.status is not IndexSuiteLookupStatus.OK:
            return None
        return result.snapshot
