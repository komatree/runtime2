"""Report-only stablecoin snapshot collector entrypoint."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts import StablecoinSnapshot
from app.storage.stablecoin_reporting import StablecoinSnapshotStorage


@dataclass(frozen=True)
class StablecoinObservabilityCollector:
    """Collects normalized stablecoin snapshots and writes report-only outputs."""

    storage: StablecoinSnapshotStorage

    def ingest(self, snapshot: StablecoinSnapshot) -> None:
        """Persist one normalized stablecoin snapshot in append-only form."""

        self.storage.append(snapshot)
