"""Read-only repository for precomputed Index Suite snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.contracts import IndexSnapshot


class IndexSuiteLookupStatus(str, Enum):
    """Lookup outcome for read-only Index Suite snapshot resolution."""

    OK = "ok"
    MISSING = "missing"
    STALE = "stale"
    VERSION_MISMATCH = "version_mismatch"


@dataclass(frozen=True)
class IndexSuiteLookupResult:
    """Result of resolving a snapshot for one instrument/date/version request."""

    status: IndexSuiteLookupStatus
    requested_instrument_id: str
    requested_index_version: str
    requested_as_of: datetime
    snapshot: IndexSnapshot | None = None
    detail: str | None = None


@dataclass(frozen=True)
class InMemoryIndexSuiteRepository:
    """Read-only repository over precomputed Index Suite snapshots."""

    snapshots: tuple[IndexSnapshot, ...]

    def resolve_latest(
        self,
        *,
        instrument_id: str,
        as_of: datetime,
        index_version: str,
        max_snapshot_age,
    ) -> IndexSuiteLookupResult:
        """Resolve the latest valid snapshot by instrument/date/version."""

        candidates = tuple(
            snapshot
            for snapshot in self.snapshots
            if snapshot.instrument_id == instrument_id and snapshot.as_of <= as_of
        )
        if not candidates:
            return IndexSuiteLookupResult(
                status=IndexSuiteLookupStatus.MISSING,
                requested_instrument_id=instrument_id,
                requested_index_version=index_version,
                requested_as_of=as_of,
                detail="no snapshot found for instrument and date",
            )

        matching_version = tuple(snapshot for snapshot in candidates if snapshot.index_version == index_version)
        if not matching_version:
            return IndexSuiteLookupResult(
                status=IndexSuiteLookupStatus.VERSION_MISMATCH,
                requested_instrument_id=instrument_id,
                requested_index_version=index_version,
                requested_as_of=as_of,
                snapshot=max(candidates, key=lambda item: item.as_of),
                detail="latest snapshot version does not match requested index version",
            )

        latest = max(matching_version, key=lambda item: item.as_of)
        snapshot_age = as_of - latest.as_of
        if snapshot_age > max_snapshot_age:
            return IndexSuiteLookupResult(
                status=IndexSuiteLookupStatus.STALE,
                requested_instrument_id=instrument_id,
                requested_index_version=index_version,
                requested_as_of=as_of,
                snapshot=latest,
                detail="snapshot is older than allowed age",
            )

        return IndexSuiteLookupResult(
            status=IndexSuiteLookupStatus.OK,
            requested_instrument_id=instrument_id,
            requested_index_version=index_version,
            requested_as_of=as_of,
            snapshot=latest,
        )
