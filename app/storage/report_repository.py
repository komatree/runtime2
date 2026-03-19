"""Append-only repository boundary for report-only cycle records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .report_models import ReportCycleRecord
from .report_serializer import ReportCycleSerializer


@dataclass(frozen=True)
class JsonlReportCycleRepository:
    """Append-only JSONL repository for report-only cycle records."""

    output_path: Path
    serializer: ReportCycleSerializer

    def append(self, record: ReportCycleRecord) -> None:
        """Append one report cycle record to the repository."""

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self.serializer.to_dict(record), sort_keys=True))
            handle.write("\n")

    def read_all(self) -> list[dict]:
        """Read all persisted records for debugging or test validation."""

        if not self.output_path.exists():
            return []
        return [
            self.serializer.from_dict(json.loads(line))
            for line in self.output_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
