"""Append-only parity comparison persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def _parity_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class ParityComparisonRecord:
    """Persisted parity comparison for one replayed cycle and one runtime mode."""

    schema_version: str
    recorded_at: datetime
    runtime_mode: str
    cycle_id: str
    instrument_id: str
    timeframe: str
    bar_close_time: datetime
    matches: bool
    mismatches: tuple[str, ...]
    key_context: dict[str, Any]
    runtime_output: dict[str, Any]
    reference_output: dict[str, Any]


@dataclass(frozen=True)
class JsonlParityComparisonGateway:
    """Appends explicit parity drift artifacts as JSONL."""

    output_path: Path

    def persist_record(self, record: ParityComparisonRecord) -> None:
        """Append one parity record for audit and debugging."""

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), default=_parity_json_default, sort_keys=True))
            handle.write("\n")
