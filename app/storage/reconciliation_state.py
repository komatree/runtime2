"""Replay-safe reconciliation cursor and unresolved-state storage."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.contracts import OrderStatus
from app.contracts import ReconciliationState
from app.exchanges.binance.models import BinanceOrderLookupResult
from app.exchanges.binance.reconciliation_coordinator import BinanceReconciliationWorkflowResult


def _state_json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class BinancePersistedRecoveryAttempt:
    """Stored recovery attempt used for replay-safe attempt numbering."""

    fingerprint: str
    lookup_field: str
    lookup_value: str
    source: str
    attempt_number: int
    found: bool
    status_summary: str | None
    alert: str | None
    cursor_token: str | None
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class BinanceReconciliationCursorSnapshot:
    """Latest replay-safe reconciliation state for restart recovery."""

    schema_version: str
    updated_at: datetime | None
    private_stream_cursor: str | None
    gap_active: bool
    unresolved_order_ids: tuple[str, ...]
    manual_attention_order_ids: tuple[str, ...]
    last_recovery_trigger_reason: str | None
    last_recovery_automatic: bool
    last_convergence_state: str | None
    last_manual_attention_at: datetime | None
    persisted_attempts: tuple[BinancePersistedRecoveryAttempt, ...]


@dataclass(frozen=True)
class JsonBinanceReconciliationStateStore:
    """JSON-backed reconciliation state store for restart-safe recovery.

    This store is authoritative for:
    - unresolved order ids that must be resumed after restart
    - replay-safe attempt numbering for order-status recovery
    - latest private-stream cursor and gap flag for operator diagnosis
    """

    state_path: Path

    def load_snapshot(self) -> BinanceReconciliationCursorSnapshot:
        """Load the latest reconciliation state snapshot or return an empty one."""

        if not self.state_path.exists():
            return BinanceReconciliationCursorSnapshot(
                schema_version="binance_reconciliation_state.v1",
                updated_at=None,
                private_stream_cursor=None,
                gap_active=False,
                unresolved_order_ids=(),
                manual_attention_order_ids=(),
                last_recovery_trigger_reason=None,
                last_recovery_automatic=False,
                last_convergence_state=None,
                last_manual_attention_at=None,
                persisted_attempts=(),
            )
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return BinanceReconciliationCursorSnapshot(
            schema_version=str(payload["schema_version"]),
            updated_at=(
                datetime.fromisoformat(payload["updated_at"])
                if payload.get("updated_at") is not None
                else None
            ),
            private_stream_cursor=payload.get("private_stream_cursor"),
            gap_active=bool(payload.get("gap_active", False)),
            unresolved_order_ids=tuple(payload.get("unresolved_order_ids", ())),
            manual_attention_order_ids=tuple(payload.get("manual_attention_order_ids", ())),
            last_recovery_trigger_reason=payload.get("last_recovery_trigger_reason"),
            last_recovery_automatic=bool(payload.get("last_recovery_automatic", False)),
            last_convergence_state=payload.get("last_convergence_state"),
            last_manual_attention_at=(
                datetime.fromisoformat(payload["last_manual_attention_at"])
                if payload.get("last_manual_attention_at") is not None
                else None
            ),
            persisted_attempts=tuple(
                BinancePersistedRecoveryAttempt(
                    fingerprint=str(item["fingerprint"]),
                    lookup_field=str(item["lookup_field"]),
                    lookup_value=str(item["lookup_value"]),
                    source=str(item["source"]),
                    attempt_number=int(item["attempt_number"]),
                    found=bool(item["found"]),
                    status_summary=(
                        str(item["status_summary"])
                        if item.get("status_summary") is not None
                        else None
                    ),
                    alert=str(item["alert"]) if item.get("alert") is not None else None,
                    cursor_token=(
                        str(item["cursor_token"])
                        if item.get("cursor_token") is not None
                        else None
                    ),
                    first_seen_at=datetime.fromisoformat(str(item["first_seen_at"])),
                    last_seen_at=datetime.fromisoformat(str(item["last_seen_at"])),
                )
                for item in payload.get("persisted_attempts", ())
            ),
        )

    def resume_expected_order_ids(self, expected_order_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return expected order ids plus unresolved ids from the persisted snapshot."""

        snapshot = self.load_snapshot()
        merged = dict.fromkeys((*expected_order_ids, *snapshot.unresolved_order_ids))
        return tuple(merged.keys())

    def load_recovery_resume_state(self) -> BinanceReconciliationCursorSnapshot:
        """Return the latest full snapshot for restart-safe recovery decisions."""

        return self.load_snapshot()

    def register_lookup_results(
        self,
        *,
        lookup_results: tuple[BinanceOrderLookupResult, ...],
        occurred_at: datetime,
        cursor_token: str | None,
    ) -> tuple[BinanceOrderLookupResult, ...]:
        """Assign replay-safe attempt numbers and ignore duplicate recovery attempts."""

        snapshot = self.load_snapshot()
        by_fingerprint = {attempt.fingerprint: attempt for attempt in snapshot.persisted_attempts}
        attempts = list(snapshot.persisted_attempts)
        normalized: list[BinanceOrderLookupResult] = []

        for lookup in lookup_results:
            fingerprint = self._fingerprint(lookup=lookup, cursor_token=cursor_token)
            existing = by_fingerprint.get(fingerprint)
            if existing is not None:
                normalized.append(
                    BinanceOrderLookupResult(
                        found=lookup.found,
                        lookup_field=lookup.lookup_field,
                        lookup_value=lookup.lookup_value,
                        source=lookup.source,
                        status_summary=lookup.status_summary,
                        alert=lookup.alert,
                        recovered_order_state=lookup.recovered_order_state,
                        recovered_fill_events=lookup.recovered_fill_events,
                        attempt_number=existing.attempt_number,
                    )
                )
                continue

            next_attempt_number = 1 + max(
                (
                    attempt.attempt_number
                    for attempt in attempts
                    if attempt.lookup_field == lookup.lookup_field
                    and attempt.lookup_value == lookup.lookup_value
                ),
                default=0,
            )
            persisted = BinancePersistedRecoveryAttempt(
                fingerprint=fingerprint,
                lookup_field=lookup.lookup_field,
                lookup_value=lookup.lookup_value,
                source=lookup.source,
                attempt_number=next_attempt_number,
                found=lookup.found,
                status_summary=lookup.status_summary,
                alert=lookup.alert,
                cursor_token=cursor_token,
                first_seen_at=occurred_at,
                last_seen_at=occurred_at,
            )
            attempts.append(persisted)
            by_fingerprint[fingerprint] = persisted
            normalized.append(
                BinanceOrderLookupResult(
                    found=lookup.found,
                    lookup_field=lookup.lookup_field,
                    lookup_value=lookup.lookup_value,
                    source=lookup.source,
                    status_summary=lookup.status_summary,
                    alert=lookup.alert,
                    recovered_order_state=lookup.recovered_order_state,
                    recovered_fill_events=lookup.recovered_fill_events,
                    attempt_number=next_attempt_number,
                )
            )

        self._write_snapshot(
            replace(
                snapshot,
                updated_at=occurred_at,
                private_stream_cursor=cursor_token or snapshot.private_stream_cursor,
                persisted_attempts=tuple(attempts),
            )
        )
        return tuple(normalized)

    def persist_workflow_state(
        self,
        *,
        workflow: BinanceReconciliationWorkflowResult,
        occurred_at: datetime,
        cursor_token: str | None,
        has_gap: bool,
    ) -> BinanceReconciliationCursorSnapshot:
        """Persist unresolved and manual-attention order state after one workflow."""

        snapshot = self.load_snapshot()
        unresolved = set(snapshot.unresolved_order_ids)
        manual_attention = set(snapshot.manual_attention_order_ids)

        for state in workflow.order_states:
            pending = state.status in {OrderStatus.RECOVERING, OrderStatus.UNRECONCILED} or (
                state.reconciliation_state
                in {
                    ReconciliationState.UNKNOWN_EXECUTION,
                    ReconciliationState.STATUS_QUERY_PENDING,
                    ReconciliationState.UNRECONCILED_MANUAL_ATTENTION,
                }
            )
            if pending:
                unresolved.add(state.order_id)
            else:
                unresolved.discard(state.order_id)

            if state.reconciliation_state is ReconciliationState.UNRECONCILED_MANUAL_ATTENTION:
                manual_attention.add(state.order_id)
            else:
                manual_attention.discard(state.order_id)

        next_snapshot = replace(
            snapshot,
            updated_at=occurred_at,
            private_stream_cursor=cursor_token or snapshot.private_stream_cursor,
            gap_active=has_gap,
            unresolved_order_ids=tuple(sorted(unresolved)),
            manual_attention_order_ids=tuple(sorted(manual_attention)),
            last_recovery_trigger_reason=workflow.recovery_trigger_reason,
            last_recovery_automatic=workflow.recovery_automatic,
            last_convergence_state=workflow.convergence_state,
            last_manual_attention_at=(
                occurred_at
                if workflow.convergence_state == "unreconciled_manual_attention"
                else snapshot.last_manual_attention_at
            ),
        )
        self._write_snapshot(next_snapshot)
        return next_snapshot

    def _write_snapshot(self, snapshot: BinanceReconciliationCursorSnapshot) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(asdict(snapshot), default=_state_json_default, sort_keys=True),
            encoding="utf-8",
        )

    def _fingerprint(
        self,
        *,
        lookup: BinanceOrderLookupResult,
        cursor_token: str | None,
    ) -> str:
        return "|".join(
            [
                lookup.lookup_field,
                lookup.lookup_value,
                lookup.source,
                lookup.status_summary or "",
                lookup.alert or "",
                "found" if lookup.found else "missing",
                cursor_token or "",
            ]
        )
