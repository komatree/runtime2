"""Restricted-live soak reporting and orchestration artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Any
from typing import TYPE_CHECKING

from app.contracts import AccountSnapshot
from app.contracts import PortfolioState
from app.contracts import RuntimeCycleResult
from app.monitoring.models import ExchangeHealthSnapshot

if TYPE_CHECKING:
    from app.runtime import RestrictedLiveRunner


class RestrictedLiveSoakStopReason(str, Enum):
    """Why a restricted-live soak finished or aborted."""

    COMPLETED = "completed"
    FATAL_EXCHANGE_HEALTH = "fatal_exchange_health"
    MANUAL_ATTENTION = "manual_attention"
    MAX_BLOCKED_MUTATIONS = "max_blocked_mutations"


@dataclass(frozen=True)
class RestrictedLiveSoakTransition:
    """Append-only transition record for one soak cycle."""

    cycle_index: int
    cycle_id: str
    recorded_at: datetime
    cycle_success: bool
    mutation_attempted: bool
    mutation_applied: bool
    blocked_mutation: bool
    reconnect_count: int
    refresh_attempts: int
    refresh_failures: int
    heartbeat_overdue_events: int
    reconciliation_recovery_attempts: int
    exchange_health_state: str
    private_stream_state: str
    reconciliation_state: str
    clock_sync_state: str
    status_query_state: str
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class RestrictedLiveReconnectEvent:
    """Explicit reconnect evidence for one soak cycle."""

    cycle_index: int
    cycle_id: str
    recorded_at: datetime
    reconnect_count: int
    reconnect_delta: int
    reason: str | None = None


@dataclass(frozen=True)
class RestrictedLiveListenKeyRefreshEvent:
    """Explicit listen-key refresh evidence for one soak cycle."""

    cycle_index: int
    cycle_id: str
    recorded_at: datetime
    refresh_attempts: int
    refresh_failures: int
    refresh_delta: int
    result: str | None = None


@dataclass(frozen=True)
class RestrictedLiveReconciliationRecord:
    """Explicit reconciliation recovery evidence for one soak cycle."""

    cycle_index: int
    cycle_id: str
    recorded_at: datetime
    recovery_attempt_count: int
    recovery_trigger_reason: str | None
    recovery_automatic: bool
    gap_detected: bool
    resumed_from_snapshot: bool
    convergence_state: str | None
    manual_attention: bool
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestrictedLiveAccountUpdateRecord:
    """Concise persisted account-side update evidence for one soak cycle."""

    cycle_index: int
    cycle_id: str
    recorded_at: datetime
    snapshot_as_of: datetime
    venue: str
    account_scope: str
    source_event_type: str
    translation_version: str
    is_partial: bool
    updated_assets: tuple[str, ...]
    balance_rows: tuple[dict[str, Any], ...]
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestrictedLiveSoakSummary:
    """Operator-facing summary for one restricted-live soak run."""

    started_at: datetime
    ended_at: datetime
    total_cycles: int
    completed_cycles: int
    blocked_mutation_count: int
    reconnect_count: int
    refresh_attempts: int
    refresh_failures: int
    heartbeat_overdue_events: int
    reconciliation_recovery_attempts: int
    reconciliation_recovery_successes: int
    reconciliation_recovery_success_rate: float | None
    account_update_event_count: int
    account_update_partial_count: int
    account_update_full_count: int
    final_exchange_health_state: str
    stop_reason: str
    aborted: bool
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class RestrictedLiveSoakRun:
    """Full soak result including transition history and final summary."""

    summary: RestrictedLiveSoakSummary
    transitions: tuple[RestrictedLiveSoakTransition, ...]
    reconnect_events: tuple[RestrictedLiveReconnectEvent, ...] = ()
    listen_key_refresh_events: tuple[RestrictedLiveListenKeyRefreshEvent, ...] = ()
    reconciliation_records: tuple[RestrictedLiveReconciliationRecord, ...] = ()
    account_update_records: tuple[RestrictedLiveAccountUpdateRecord, ...] = ()


@dataclass(frozen=True)
class RestrictedLiveSoakArtifactPaths:
    """Filesystem locations for one persisted restricted-live soak run."""

    health_transitions_path: Path
    reconnect_events_path: Path
    listen_key_refresh_path: Path
    reconciliation_events_path: Path
    account_update_events_path: Path
    summary_json_path: Path
    summary_markdown_path: Path


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


@dataclass(frozen=True)
class RestrictedLiveSoakArtifactWriter:
    """Write append-only transition and summary artifacts for soak runs."""

    output_dir: Path

    def persist(self, *, run: RestrictedLiveSoakRun, markdown: str) -> RestrictedLiveSoakArtifactPaths:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        transitions_path = self.output_dir / "health_transitions.jsonl"
        reconnect_path = self.output_dir / "reconnect_events.jsonl"
        refresh_path = self.output_dir / "listen_key_refresh.jsonl"
        reconciliation_path = self.output_dir / "reconciliation_events.jsonl"
        account_update_path = self.output_dir / "account_update_events.jsonl"
        summary_json_path = self.output_dir / "soak_summary.json"
        summary_markdown_path = self.output_dir / "soak_summary.md"
        with transitions_path.open("a", encoding="utf-8") as handle:
            for transition in run.transitions:
                handle.write(json.dumps(asdict(transition), default=_json_default, sort_keys=True))
                handle.write("\n")
        with reconnect_path.open("a", encoding="utf-8") as handle:
            for event in run.reconnect_events:
                handle.write(json.dumps(asdict(event), default=_json_default, sort_keys=True))
                handle.write("\n")
        with refresh_path.open("a", encoding="utf-8") as handle:
            for event in run.listen_key_refresh_events:
                handle.write(json.dumps(asdict(event), default=_json_default, sort_keys=True))
                handle.write("\n")
        with reconciliation_path.open("a", encoding="utf-8") as handle:
            for record in run.reconciliation_records:
                handle.write(json.dumps(asdict(record), default=_json_default, sort_keys=True))
                handle.write("\n")
        with account_update_path.open("a", encoding="utf-8") as handle:
            for record in run.account_update_records:
                handle.write(json.dumps(asdict(record), default=_json_default, sort_keys=True))
                handle.write("\n")
        summary_json_path.write_text(
            json.dumps(asdict(run.summary), default=_json_default, sort_keys=True),
            encoding="utf-8",
        )
        summary_markdown_path.write_text(markdown, encoding="utf-8")
        return RestrictedLiveSoakArtifactPaths(
            health_transitions_path=transitions_path,
            reconnect_events_path=reconnect_path,
            listen_key_refresh_path=refresh_path,
            reconciliation_events_path=reconciliation_path,
            account_update_events_path=account_update_path,
            summary_json_path=summary_json_path,
            summary_markdown_path=summary_markdown_path,
        )


@dataclass(frozen=True)
class RestrictedLiveSoakReportingService:
    """Render operator-facing markdown for restricted-live soak runs."""

    def render_markdown(self, *, run: RestrictedLiveSoakRun) -> str:
        alerts = ", ".join(run.summary.alerts) or "none"
        return "\n".join(
            [
                "# Restricted-Live Soak Summary",
                f"- started_at: {run.summary.started_at.isoformat()}",
                f"- ended_at: {run.summary.ended_at.isoformat()}",
                f"- total_cycles: {run.summary.total_cycles}",
                f"- completed_cycles: {run.summary.completed_cycles}",
                f"- blocked_mutation_count: {run.summary.blocked_mutation_count}",
                f"- reconnect_count: {run.summary.reconnect_count}",
                f"- refresh_attempts: {run.summary.refresh_attempts}",
                f"- refresh_failures: {run.summary.refresh_failures}",
                f"- heartbeat_overdue_events: {run.summary.heartbeat_overdue_events}",
                f"- reconciliation_recovery_attempts: {run.summary.reconciliation_recovery_attempts}",
                f"- reconciliation_recovery_successes: {run.summary.reconciliation_recovery_successes}",
                (
                    "- reconciliation_recovery_success_rate: none"
                    if run.summary.reconciliation_recovery_success_rate is None
                    else f"- reconciliation_recovery_success_rate: {run.summary.reconciliation_recovery_success_rate:.4f}"
                ),
                f"- account_update_event_count: {run.summary.account_update_event_count}",
                f"- account_update_partial_count: {run.summary.account_update_partial_count}",
                f"- account_update_full_count: {run.summary.account_update_full_count}",
                f"- final_exchange_health_state: {run.summary.final_exchange_health_state}",
                f"- stop_reason: {run.summary.stop_reason}",
                f"- aborted: {str(run.summary.aborted).lower()}",
                f"- alerts: {alerts}",
            ]
        )


@dataclass(frozen=True)
class RestrictedLiveSoakStopCriteria:
    """Explicit stop criteria for restricted-live soak runs."""

    max_cycles: int | None = None
    max_duration: timedelta | None = None
    poll_interval_seconds: float = 0.0
    max_blocked_mutations: int = 3
    abort_on_fatal_exchange_health: bool = True
    abort_on_manual_attention: bool = True


@dataclass
class RecordingRestrictedLiveGate:
    """Runtime gate wrapper that preserves detailed gate results for soak reporting."""

    delegate: Any

    def __post_init__(self) -> None:
        self.last_result = None

    def apply(self, *, portfolio_state, expected_order_ids=(), already_applied_fill_ids=()):
        self.last_result = self.delegate.apply_with_details(
            portfolio_state=portfolio_state,
            expected_order_ids=expected_order_ids,
            already_applied_fill_ids=already_applied_fill_ids,
        )
        return self.last_result.mutation_outcome


@dataclass(frozen=True)
class RestrictedLiveSoakExchangeHealthProvider:
    """Current exchange-health provider for restricted-live soak cycles."""

    health_service: Any
    payload_source: Any
    recording_gate: RecordingRestrictedLiveGate

    def current_health(self) -> ExchangeHealthSnapshot | None:
        gate_result = self.recording_gate.last_result
        transport_result = None if gate_result is None else gate_result.transport_result
        return self.health_service.build_snapshot(
            private_stream_health=self.payload_source.current_health(),
            reconciliation_workflow=(
                None if transport_result is None else transport_result.workflow_result
            ),
            clock_status=None,
            status_query_health=(
                ()
                if transport_result is None
                else transport_result.status_query_health
            ),
            cursor_snapshot=(
                None if transport_result is None else transport_result.cursor_snapshot
            ),
            generated_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class RestrictedLiveSoakRunner:
    """Repeated restricted-live rehearsal runner for long-running soak evidence."""

    runner: Any
    recording_gate: RecordingRestrictedLiveGate
    exchange_health_provider: RestrictedLiveSoakExchangeHealthProvider
    payload_source: Any
    time_provider: Any = lambda: datetime.now(UTC)
    sleep_fn: Any = sleep

    def run(
        self,
        *,
        criteria: RestrictedLiveSoakStopCriteria,
        cycle_id_prefix: str,
        instrument,
        bar_slice,
        context_bar_slice,
        portfolio_state: PortfolioState,
    ) -> RestrictedLiveSoakRun:
        transitions: list[RestrictedLiveSoakTransition] = []
        reconnect_events: list[RestrictedLiveReconnectEvent] = []
        refresh_events: list[RestrictedLiveListenKeyRefreshEvent] = []
        reconciliation_records: list[RestrictedLiveReconciliationRecord] = []
        account_update_records: list[RestrictedLiveAccountUpdateRecord] = []
        current_portfolio = portfolio_state
        already_applied_fill_ids: tuple[str, ...] = ()
        blocked_mutation_count = 0
        recovery_attempt_count = 0
        recovery_success_count = 0
        stop_reason = RestrictedLiveSoakStopReason.COMPLETED
        started_at = self.time_provider()
        deadline = (
            started_at + criteria.max_duration
            if criteria.max_duration is not None
            else None
        )
        cycle_index = 0
        previous_reconnect_count = 0
        previous_refresh_attempts = 0

        while True:
            if criteria.max_cycles is not None and cycle_index >= criteria.max_cycles:
                break
            if deadline is not None and self.time_provider() >= deadline:
                break
            cycle_index += 1
            cycle = self.runner.run_cycle(
                cycle_id=f"{cycle_id_prefix}-{cycle_index:04d}",
                instrument=instrument,
                bar_slice=bar_slice,
                context_bar_slice=context_bar_slice,
                portfolio_state=current_portfolio,
                already_applied_fill_ids=already_applied_fill_ids,
            )
            gate_result = self.recording_gate.last_result
            mutation_outcome = None if gate_result is None else gate_result.mutation_outcome
            transport_result = None if gate_result is None else gate_result.transport_result
            exchange_health = self.exchange_health_provider.current_health()
            stats = self.payload_source.stats_snapshot()
            if mutation_outcome is not None and mutation_outcome.mutation_applied:
                current_portfolio = mutation_outcome.portfolio_state
            if mutation_outcome is not None:
                already_applied_fill_ids = tuple(
                    dict.fromkeys(
                        (
                            *already_applied_fill_ids,
                            *mutation_outcome.translation_result.applied_fill_ids,
                            *mutation_outcome.translation_result.ignored_fill_ids,
                        )
                    )
                )
            blocked = bool(
                mutation_outcome is not None
                and mutation_outcome.mutation_attempted
                and not mutation_outcome.mutation_applied
            )
            if blocked:
                blocked_mutation_count += 1
            if transport_result is not None:
                recovery_attempt_count += len(transport_result.status_query_health)
                if transport_result.workflow_result.convergence_state == "converged_terminal":
                    recovery_success_count += 1
            transition = RestrictedLiveSoakTransition(
                cycle_index=cycle_index,
                cycle_id=cycle.cycle_id,
                recorded_at=cycle.completed_at,
                cycle_success=cycle.success,
                mutation_attempted=False if mutation_outcome is None else mutation_outcome.mutation_attempted,
                mutation_applied=False if mutation_outcome is None else mutation_outcome.mutation_applied,
                blocked_mutation=blocked,
                reconnect_count=stats.reconnect_count,
                refresh_attempts=stats.refresh_attempts,
                refresh_failures=stats.refresh_failures,
                heartbeat_overdue_events=stats.heartbeat_overdue_events,
                reconciliation_recovery_attempts=recovery_attempt_count,
                exchange_health_state=(
                    "unknown"
                    if exchange_health is None
                    else exchange_health.overall_state.value
                ),
                private_stream_state=(
                    "unknown"
                    if exchange_health is None
                    else exchange_health.private_stream.state.value
                ),
                reconciliation_state=(
                    "unknown"
                    if exchange_health is None
                    else exchange_health.reconciliation.state.value
                ),
                clock_sync_state=(
                    "unknown"
                    if exchange_health is None
                    else exchange_health.clock_sync.state.value
                ),
                status_query_state=(
                    "unknown"
                    if exchange_health is None
                    else exchange_health.status_query.state.value
                ),
                alerts=cycle.alerts,
            )
            transitions.append(transition)
            reconnect_delta = stats.reconnect_count - previous_reconnect_count
            if reconnect_delta > 0:
                reconnect_events.append(
                    RestrictedLiveReconnectEvent(
                        cycle_index=cycle_index,
                        cycle_id=cycle.cycle_id,
                        recorded_at=cycle.completed_at,
                        reconnect_count=stats.reconnect_count,
                        reconnect_delta=reconnect_delta,
                        reason=stats.last_transport_error,
                    )
                )
            refresh_delta = stats.refresh_attempts - previous_refresh_attempts
            if refresh_delta > 0:
                refresh_events.append(
                    RestrictedLiveListenKeyRefreshEvent(
                        cycle_index=cycle_index,
                        cycle_id=cycle.cycle_id,
                        recorded_at=cycle.completed_at,
                        refresh_attempts=stats.refresh_attempts,
                        refresh_failures=stats.refresh_failures,
                        refresh_delta=refresh_delta,
                        result=stats.last_refresh_result,
                    )
                )
            previous_reconnect_count = stats.reconnect_count
            previous_refresh_attempts = stats.refresh_attempts
            if transport_result is not None:
                reconciliation_records.append(
                    RestrictedLiveReconciliationRecord(
                        cycle_index=cycle_index,
                        cycle_id=cycle.cycle_id,
                        recorded_at=cycle.completed_at,
                        recovery_attempt_count=len(transport_result.status_query_health),
                        recovery_trigger_reason=transport_result.workflow_result.recovery_trigger_reason,
                        recovery_automatic=transport_result.workflow_result.recovery_automatic,
                        gap_detected=transport_result.workflow_result.gap_detected,
                        resumed_from_snapshot=transport_result.workflow_result.resumed_from_snapshot,
                        convergence_state=transport_result.workflow_result.convergence_state,
                        manual_attention=(
                            transport_result.workflow_result.convergence_state
                            == "unreconciled_manual_attention"
                        ),
                        alerts=transport_result.workflow_result.alerts,
                    )
                )
                account_update_records.extend(
                    self._build_account_update_records(
                        cycle_index=cycle_index,
                        cycle_id=cycle.cycle_id,
                        recorded_at=cycle.completed_at,
                        transport_result=transport_result,
                    )
                )

            if (
                criteria.abort_on_fatal_exchange_health
                and exchange_health is not None
                and exchange_health.overall_state.value == "fatal"
            ):
                stop_reason = RestrictedLiveSoakStopReason.FATAL_EXCHANGE_HEALTH
                break
            if (
                criteria.abort_on_manual_attention
                and exchange_health is not None
                and exchange_health.reconciliation.state.value == "fatal"
            ):
                stop_reason = RestrictedLiveSoakStopReason.MANUAL_ATTENTION
                break
            if blocked_mutation_count >= criteria.max_blocked_mutations:
                stop_reason = RestrictedLiveSoakStopReason.MAX_BLOCKED_MUTATIONS
                break
            if deadline is not None and self.time_provider() >= deadline:
                break
            if criteria.poll_interval_seconds > 0:
                sleep_seconds = criteria.poll_interval_seconds
                if deadline is not None:
                    remaining_seconds = (deadline - self.time_provider()).total_seconds()
                    if remaining_seconds <= 0:
                        break
                    sleep_seconds = min(sleep_seconds, remaining_seconds)
                self.sleep_fn(sleep_seconds)

        ended_at = transitions[-1].recorded_at if transitions else started_at
        final_exchange_state = transitions[-1].exchange_health_state if transitions else "unknown"
        recovery_workflows = len(
            [record for record in reconciliation_records if record.recovery_attempt_count > 0]
        )
        summary = RestrictedLiveSoakSummary(
            started_at=started_at,
            ended_at=ended_at,
            total_cycles=criteria.max_cycles or len(transitions),
            completed_cycles=len(transitions),
            blocked_mutation_count=blocked_mutation_count,
            reconnect_count=self.payload_source.stats_snapshot().reconnect_count,
            refresh_attempts=self.payload_source.stats_snapshot().refresh_attempts,
            refresh_failures=self.payload_source.stats_snapshot().refresh_failures,
            heartbeat_overdue_events=self.payload_source.stats_snapshot().heartbeat_overdue_events,
            reconciliation_recovery_attempts=recovery_attempt_count,
            reconciliation_recovery_successes=recovery_success_count,
            reconciliation_recovery_success_rate=(
                None
                if recovery_workflows == 0
                else recovery_success_count / recovery_workflows
            ),
            account_update_event_count=len(account_update_records),
            account_update_partial_count=len([record for record in account_update_records if record.is_partial]),
            account_update_full_count=len([record for record in account_update_records if not record.is_partial]),
            final_exchange_health_state=final_exchange_state,
            stop_reason=stop_reason.value,
            aborted=stop_reason is not RestrictedLiveSoakStopReason.COMPLETED,
            alerts=tuple(alert for item in transitions for alert in item.alerts),
        )
        return RestrictedLiveSoakRun(
            summary=summary,
            transitions=tuple(transitions),
            reconnect_events=tuple(reconnect_events),
            listen_key_refresh_events=tuple(refresh_events),
            reconciliation_records=tuple(reconciliation_records),
            account_update_records=tuple(account_update_records),
        )

    def _build_account_update_records(
        self,
        *,
        cycle_index: int,
        cycle_id: str,
        recorded_at: datetime,
        transport_result: Any,
    ) -> tuple[RestrictedLiveAccountUpdateRecord, ...]:
        records: list[RestrictedLiveAccountUpdateRecord] = []
        for translation in getattr(transport_result, "translations", ()):
            snapshot = getattr(translation, "account_snapshot", None)
            if snapshot is None:
                continue
            records.append(
                RestrictedLiveAccountUpdateRecord(
                    cycle_index=cycle_index,
                    cycle_id=cycle_id,
                    recorded_at=recorded_at,
                    snapshot_as_of=snapshot.as_of,
                    venue=snapshot.venue,
                    account_scope=snapshot.account_scope,
                    source_event_type=snapshot.source_event_type,
                    translation_version=snapshot.translation_version,
                    is_partial=snapshot.is_partial,
                    updated_assets=tuple(balance.asset for balance in snapshot.balances),
                    balance_rows=tuple(self._serialize_balance_rows(snapshot)),
                    alerts=snapshot.alerts,
                )
            )
        return tuple(records)

    @staticmethod
    def _serialize_balance_rows(snapshot: AccountSnapshot) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for balance in snapshot.balances:
            rows.append(
                {
                    "asset": balance.asset,
                    "free": balance.free,
                    "locked": balance.locked,
                    "delta": balance.delta,
                    "updated_at": balance.updated_at,
                }
            )
        return tuple(rows)
