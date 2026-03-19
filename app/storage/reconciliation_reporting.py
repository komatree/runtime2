"""Append-only reconciliation recovery logging."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.exchanges.binance.reconciliation_coordinator import BinanceReconciliationWorkflowResult
from .reconciliation_state import BinanceReconciliationCursorSnapshot


def _reconciliation_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class JsonlReconciliationPersistenceGateway:
    """Persists recovery attempts and outcomes for operator inspection."""

    output_path: Path

    def persist_workflow(self, workflow: BinanceReconciliationWorkflowResult) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "binance_reconciliation_workflow.v3",
            "workflow": asdict(workflow),
            "recovery_attempt_count": len(workflow.recovery_attempts),
            "recovery_summary_count": len(workflow.recovery_summaries),
        }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=_reconciliation_json_default, sort_keys=True))
            handle.write("\n")


@dataclass(frozen=True)
class FileReconciliationCursorPersistenceGateway:
    """Persists the latest reconciliation cursor snapshot for restart-safe recovery."""

    output_path: Path

    def persist_snapshot(self, snapshot: BinanceReconciliationCursorSnapshot) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(asdict(snapshot), default=_reconciliation_json_default, sort_keys=True),
            encoding="utf-8",
        )
