"""Structured persistence gateway for report-only runtime output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.contracts import DecisionContext
from app.contracts import FeatureSnapshot
from app.contracts import RuntimeCycleResult
from app.monitoring import ExchangeHealthSnapshot
from app.monitoring import FileRuntimeStatusGateway
from app.monitoring import RuntimeObservabilityService

from .report_repository import JsonlReportCycleRepository
from .report_serializer import ReportCycleSerializer


@dataclass(frozen=True)
class JsonlReportPersistenceGateway:
    """Persists report-only cycles through an explicit repository boundary."""

    output_path: Path
    status_gateway: FileRuntimeStatusGateway | None = None
    mode: str = "report_only"

    def persist_cycle(
        self,
        cycle_result: RuntimeCycleResult,
        *,
        features: FeatureSnapshot,
        context: DecisionContext,
        exchange_health: ExchangeHealthSnapshot | None = None,
    ) -> None:
        """Persist cycle, feature, and decision summaries as append-only JSONL."""

        serializer = ReportCycleSerializer()
        repository = JsonlReportCycleRepository(output_path=self.output_path, serializer=serializer)
        record = serializer.build_record(
            cycle_result=cycle_result,
            features=features,
            context=context,
            recorded_at=cycle_result.completed_at,
        )
        repository.append(record)
        if self.status_gateway is not None:
            observability = RuntimeObservabilityService(mode=self.mode)
            summary = observability.build_cycle_summary(
                cycle_result=cycle_result,
                features=features,
                context=context,
                persisted_at=cycle_result.completed_at,
                exchange_health=exchange_health,
            )
            health = observability.build_health_snapshot(summary=summary, exchange_health=exchange_health)
            self.status_gateway.persist(
                summary=summary,
                health=health,
                operator_report=observability.render_operator_report(summary=summary, health=health),
            )
