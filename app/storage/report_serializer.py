"""Serializer for append-only report cycle records."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import RuntimeCycleResult

from .report_models import DecisionContextSummaryRecord
from .report_models import FeatureSnapshotSummaryRecord
from .report_models import IndexSuiteContextRecord
from .report_models import ReportCycleRecord


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _to_json_compatible(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_compatible(item) for item in value]
    return value


class ReportCycleSerializer:
    """Builds a stable JSON-compatible record for report-only persistence."""

    schema_version = "report_cycle.v1"

    def build_record(
        self,
        *,
        cycle_result: RuntimeCycleResult,
        features: FeatureSnapshot,
        context: DecisionContext,
        recorded_at: datetime,
    ) -> ReportCycleRecord:
        """Return an explicit record model ready for append-only persistence."""

        feature_names = tuple(sorted(features.feature_values.keys()))
        candle_features = {
            key: str(value)
            for key, value in features.feature_values.items()
            if key.startswith("candle.")
        }
        index_features = {
            key: str(value)
            for key, value in features.feature_values.items()
            if key.startswith("index_suite.")
        } or None
        stablecoin_features = {
            key: str(value)
            for key, value in features.feature_values.items()
            if key.startswith("stablecoin.")
        } or None

        return ReportCycleRecord(
            schema_version=self.schema_version,
            recorded_at=recorded_at,
            cycle_timestamp=context.as_of,
            instrument_id=context.instrument.instrument_id,
            timeframe=context.features.timeframe,
            bar_close_time=context.latest_candle.close_time,
            feature_snapshot_summary=FeatureSnapshotSummaryRecord(
                feature_count=len(feature_names),
                feature_names=feature_names,
                is_complete=features.is_complete,
                source_bar_count=features.source_bar_count,
                candle_features=candle_features,
                index_features=index_features,
                stablecoin_features=stablecoin_features,
            ),
            signal_decisions=tuple(_to_json_compatible(signal) for signal in cycle_result.signals),
            risk_decisions=tuple(_to_json_compatible(decision) for decision in cycle_result.risk_decisions),
            execution_intents=tuple(_to_json_compatible(intent) for intent in cycle_result.execution_intents),
            runtime_cycle_result=_to_json_compatible(cycle_result),
            decision_context_summary=DecisionContextSummaryRecord(
                cycle_id=context.cycle_id,
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                bar_close_time=context.latest_candle.close_time,
                has_index_snapshot=context.index_snapshot is not None,
                has_stablecoin_snapshot=context.stablecoin_snapshot is not None,
                index_snapshot_version=context.index_snapshot.index_version if context.index_snapshot is not None else None,
                index_snapshot_status=context.index_snapshot_status,
            ),
            index_suite_context=IndexSuiteContextRecord(
                present=context.index_snapshot is not None,
                instrument_id=context.instrument.instrument_id,
                requested_as_of=context.as_of,
                requested_index_version=context.index_snapshot_requested_version,
                snapshot_as_of=context.index_snapshot.as_of if context.index_snapshot is not None else None,
                index_version=context.index_snapshot.index_version if context.index_snapshot is not None else None,
                value=str(context.index_snapshot.value) if context.index_snapshot is not None else None,
                status=context.index_snapshot_status,
                detail=context.index_snapshot_detail,
            ),
        )

    def to_dict(self, record: ReportCycleRecord) -> dict[str, Any]:
        """Convert a record to a JSON-compatible dictionary."""

        return _to_json_compatible(record)

    def from_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the payload as a stable schema-shaped dictionary.

        Round-trip validation currently targets schema shape rather than full
        dataclass hydration to keep optional sections tolerant during iteration.
        """

        return payload
