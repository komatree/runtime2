"""Explicit append-only report models for report-only runtime cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FeatureSnapshotSummaryRecord:
    """Debug-oriented summary of a feature snapshot.

    Optional feature families remain optional in the schema so missing upstream
    sources can be observed without breaking serialization.
    """

    feature_count: int
    feature_names: tuple[str, ...]
    is_complete: bool
    source_bar_count: int
    candle_features: dict[str, str]
    index_features: dict[str, str] | None = None
    stablecoin_features: dict[str, str] | None = None


@dataclass(frozen=True)
class DecisionContextSummaryRecord:
    """Compact context view persisted alongside the full cycle audit record."""

    cycle_id: str
    instrument_id: str
    timeframe: str
    as_of: datetime
    bar_close_time: datetime
    has_index_snapshot: bool
    has_stablecoin_snapshot: bool
    index_snapshot_version: str | None = None
    index_snapshot_status: str | None = None


@dataclass(frozen=True)
class IndexSuiteContextRecord:
    """Persisted decision-time Index Suite context."""

    present: bool
    instrument_id: str
    requested_as_of: datetime
    requested_index_version: str | None = None
    snapshot_as_of: datetime | None = None
    index_version: str | None = None
    value: str | None = None
    status: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ReportCycleRecord:
    """Append-only persisted report-only cycle record.

    Future migration point:
    - The schema is JSONL-first for debugging clarity.
    - A future SQLite migration can map these top-level sections into tables
      without changing the meaning of the persisted fields.
    """

    schema_version: str
    recorded_at: datetime
    cycle_timestamp: datetime
    instrument_id: str
    timeframe: str
    bar_close_time: datetime
    feature_snapshot_summary: FeatureSnapshotSummaryRecord
    signal_decisions: tuple[dict[str, Any], ...]
    risk_decisions: tuple[dict[str, Any], ...]
    execution_intents: tuple[dict[str, Any], ...]
    runtime_cycle_result: dict[str, Any]
    decision_context_summary: DecisionContextSummaryRecord
    index_suite_context: IndexSuiteContextRecord | None = None
