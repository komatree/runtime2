"""Read-only stablecoin observability snapshot services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.contracts import StablecoinSnapshot


class StablecoinSnapshotStatus(str, Enum):
    """Resolution status for report-only stablecoin observability snapshots."""

    OK = "ok"
    MISSING = "missing"
    STALE = "stale"


@dataclass(frozen=True)
class StablecoinSnapshotLookupResult:
    """Result of resolving the latest stablecoin snapshot."""

    status: StablecoinSnapshotStatus
    requested_as_of: datetime
    snapshot: StablecoinSnapshot | None = None
    detail: str | None = None


@dataclass(frozen=True)
class InMemoryStablecoinSnapshotRepository:
    """Read-only repository over precomputed stablecoin observability snapshots."""

    snapshots: tuple[StablecoinSnapshot, ...]

    def resolve_latest(self, *, as_of: datetime) -> StablecoinSnapshotLookupResult:
        """Resolve the latest snapshot that is valid for the requested time."""

        candidates = tuple(snapshot for snapshot in self.snapshots if snapshot.as_of <= as_of)
        if not candidates:
            return StablecoinSnapshotLookupResult(
                status=StablecoinSnapshotStatus.MISSING,
                requested_as_of=as_of,
                detail="no stablecoin snapshot found for requested time",
            )
        latest = max(candidates, key=lambda item: item.as_of)
        if latest.source_fresh_until < as_of:
            return StablecoinSnapshotLookupResult(
                status=StablecoinSnapshotStatus.STALE,
                requested_as_of=as_of,
                snapshot=latest,
                detail="stablecoin snapshot freshness expired",
            )
        return StablecoinSnapshotLookupResult(
            status=StablecoinSnapshotStatus.OK,
            requested_as_of=as_of,
            snapshot=latest,
        )


@dataclass(frozen=True)
class ReadOnlyStablecoinSnapshotProvider:
    """Read-only provider for report-only stablecoin observability snapshots."""

    repository: InMemoryStablecoinSnapshotRepository

    def resolve_snapshot(self, *, as_of: datetime) -> StablecoinSnapshotLookupResult:
        """Resolve the latest stablecoin snapshot for one decision time."""

        return self.repository.resolve_latest(as_of=as_of)

    def get_snapshot(self, *, as_of: datetime) -> StablecoinSnapshot | None:
        """Return only a fresh snapshot; stale snapshots resolve to `None`."""

        result = self.resolve_snapshot(as_of=as_of)
        if result.status is not StablecoinSnapshotStatus.OK:
            return None
        return result.snapshot
