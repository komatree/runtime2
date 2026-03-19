"""Deterministic reconciliation disruption scenarios and evidence artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceClockSync
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinanceOrderLookupResult
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinanceReconciliationService
from app.exchanges.binance import BinanceStatusQueryHealth
from app.exchanges.binance import BinanceStatusQueryState
from app.exchanges.binance import BinanceSymbolMapping
from app.storage.reconciliation_reporting import JsonlReconciliationPersistenceGateway
from app.storage.reconciliation_state import JsonBinanceReconciliationStateStore


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class ReconciliationDisruptionStep:
    """One deterministic reconciliation step."""

    step_id: str
    expected_order_ids: tuple[str, ...]
    private_payloads: tuple[dict[str, object], ...]
    lookup_results: tuple[BinanceOrderLookupResult, ...] = ()
    has_gap: bool = False


@dataclass(frozen=True)
class ReconciliationDisruptionScenario:
    """One operator-readable reconciliation disruption scenario."""

    scenario_id: str
    description: str
    steps: tuple[ReconciliationDisruptionStep, ...]
    expected_final_convergence_state: str
    expect_manual_attention: bool = False
    expect_recovery_trigger: bool = False


@dataclass(frozen=True)
class ReconciliationDisruptionWorkflowRecord:
    """Persisted summary for one disruption workflow step."""

    step_index: int
    step_id: str
    matched_order_ids: tuple[str, ...]
    missing_order_ids: tuple[str, ...]
    unknown_execution_ids: tuple[str, ...]
    recovery_attempt_count: int
    recovery_summary_count: int
    recovery_trigger_reason: str | None
    recovery_automatic: bool
    convergence_state: str | None
    manual_attention: bool
    status_query_states: tuple[str, ...]
    unresolved_order_ids: tuple[str, ...]
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationDisruptionScenarioSummary:
    """Operator-facing scenario summary."""

    scenario_id: str
    description: str
    scenario_passed: bool
    total_steps: int
    total_recovery_attempts: int
    persisted_attempt_count: int
    trigger_reasons: tuple[str, ...]
    convergence_states: tuple[str, ...]
    final_convergence_state: str | None
    manual_attention_observed: bool
    unresolved_order_ids: tuple[str, ...]
    alerts: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True)
class ReconciliationDisruptionScenarioRun:
    """Full scenario output including workflow records and summary."""

    summary: ReconciliationDisruptionScenarioSummary
    workflow_records: tuple[ReconciliationDisruptionWorkflowRecord, ...]


@dataclass(frozen=True)
class ReconciliationDisruptionArtifactPaths:
    """Artifact locations for one disruption scenario."""

    workflow_records_path: Path
    workflow_log_path: Path
    reconciliation_state_path: Path
    summary_json_path: Path
    summary_markdown_path: Path


@dataclass(frozen=True)
class ReconciliationDisruptionArtifactWriter:
    """Persist machine-readable scenario artifacts."""

    output_dir: Path

    def persist(self, *, run: ReconciliationDisruptionScenarioRun, markdown: str) -> ReconciliationDisruptionArtifactPaths:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        workflow_records_path = self.output_dir / "workflow_records.jsonl"
        workflow_log_path = self.output_dir / "reconciliation_workflows.jsonl"
        state_path = self.output_dir / "reconciliation_state.json"
        summary_json_path = self.output_dir / "scenario_summary.json"
        summary_markdown_path = self.output_dir / "scenario_summary.md"

        with workflow_records_path.open("w", encoding="utf-8") as handle:
            for record in run.workflow_records:
                handle.write(json.dumps(asdict(record), default=_json_default, sort_keys=True))
                handle.write("\n")
        summary_json_path.write_text(
            json.dumps(asdict(run.summary), default=_json_default, sort_keys=True),
            encoding="utf-8",
        )
        summary_markdown_path.write_text(markdown, encoding="utf-8")
        return ReconciliationDisruptionArtifactPaths(
            workflow_records_path=workflow_records_path,
            workflow_log_path=workflow_log_path,
            reconciliation_state_path=state_path,
            summary_json_path=summary_json_path,
            summary_markdown_path=summary_markdown_path,
        )


@dataclass(frozen=True)
class ReconciliationDisruptionReportingService:
    """Render short operator-facing markdown summaries."""

    def render_markdown(self, *, run: ReconciliationDisruptionScenarioRun) -> str:
        triggers = ", ".join(run.summary.trigger_reasons) or "none"
        convergence = ", ".join(run.summary.convergence_states) or "none"
        unresolved = ", ".join(run.summary.unresolved_order_ids) or "none"
        alerts = ", ".join(run.summary.alerts) or "none"
        return "\n".join(
            [
                "# Reconciliation Disruption Scenario",
                f"- scenario_id: {run.summary.scenario_id}",
                f"- description: {run.summary.description}",
                f"- scenario_passed: {str(run.summary.scenario_passed).lower()}",
                f"- total_steps: {run.summary.total_steps}",
                f"- total_recovery_attempts: {run.summary.total_recovery_attempts}",
                f"- persisted_attempt_count: {run.summary.persisted_attempt_count}",
                f"- trigger_reasons: {triggers}",
                f"- convergence_states: {convergence}",
                f"- final_convergence_state: {run.summary.final_convergence_state or 'none'}",
                f"- manual_attention_observed: {str(run.summary.manual_attention_observed).lower()}",
                f"- unresolved_order_ids: {unresolved}",
                f"- alerts: {alerts}",
            ]
        )


@dataclass(frozen=True)
class ReconciliationDisruptionRunner:
    """Run deterministic reconciliation disruption scenarios."""

    output_root: Path

    def run_scenario(self, *, scenario: ReconciliationDisruptionScenario) -> ReconciliationDisruptionScenarioRun:
        scenario_dir = self.output_root / scenario.scenario_id
        state_store = JsonBinanceReconciliationStateStore(state_path=scenario_dir / "reconciliation_state.json")
        workflow_gateway = JsonlReconciliationPersistenceGateway(
            output_path=scenario_dir / "reconciliation_workflows.jsonl",
        )
        service = BinanceReconciliationService()
        client = BinancePrivateStreamClient(config=_config())
        translator = BinancePrivatePayloadTranslator(
            symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
        )
        order_client = BinanceOrderClient(config=_config(), clock_sync=BinanceClockSync(_config()))
        records: list[ReconciliationDisruptionWorkflowRecord] = []

        for step_index, step in enumerate(scenario.steps, start=1):
            result = service.reconcile_with_transports(
                expected_order_ids=step.expected_order_ids,
                private_payloads=step.private_payloads,
                private_stream_client=client,
                translator=translator,
                order_client=order_client,
                lookup_transport=_ScenarioLookupTransport(step.lookup_results),
                state_store=state_store,
                cursor=f"{scenario.scenario_id}:{step.step_id}",
                has_gap=step.has_gap,
                occurred_at=_dt(0, step_index),
            )
            workflow_gateway.persist_workflow(result.workflow_result)
            snapshot = state_store.load_snapshot()
            records.append(
                ReconciliationDisruptionWorkflowRecord(
                    step_index=step_index,
                    step_id=step.step_id,
                    matched_order_ids=result.reconciliation_result.matched_order_ids,
                    missing_order_ids=result.reconciliation_result.missing_order_ids,
                    unknown_execution_ids=result.reconciliation_result.unknown_execution_ids,
                    recovery_attempt_count=len(result.workflow_result.recovery_attempts),
                    recovery_summary_count=len(result.workflow_result.recovery_summaries),
                    recovery_trigger_reason=result.workflow_result.recovery_trigger_reason,
                    recovery_automatic=result.workflow_result.recovery_automatic,
                    convergence_state=result.workflow_result.convergence_state,
                    manual_attention=any(
                        state.reconciliation_state is not None
                        and state.reconciliation_state.value == "unreconciled_manual_attention"
                        for state in result.workflow_result.order_states
                    ),
                    status_query_states=tuple(health.state.value for health in result.status_query_health),
                    unresolved_order_ids=snapshot.unresolved_order_ids,
                    alerts=result.workflow_result.alerts,
                )
            )

        summary = self._build_summary(
            scenario=scenario,
            records=tuple(records),
            snapshot=state_store.load_snapshot(),
        )
        return ReconciliationDisruptionScenarioRun(summary=summary, workflow_records=tuple(records))

    def run_campaign(
        self,
        *,
        scenarios: tuple[ReconciliationDisruptionScenario, ...],
    ) -> tuple[ReconciliationDisruptionArtifactPaths, ...]:
        reporting = ReconciliationDisruptionReportingService()
        paths: list[ReconciliationDisruptionArtifactPaths] = []
        for scenario in scenarios:
            run = self.run_scenario(scenario=scenario)
            paths.append(
                ReconciliationDisruptionArtifactWriter(output_dir=self.output_root / scenario.scenario_id).persist(
                    run=run,
                    markdown=reporting.render_markdown(run=run),
                )
            )
        return tuple(paths)

    def _build_summary(
        self,
        *,
        scenario: ReconciliationDisruptionScenario,
        records: tuple[ReconciliationDisruptionWorkflowRecord, ...],
        snapshot,
    ) -> ReconciliationDisruptionScenarioSummary:
        trigger_reasons = tuple(
            dict.fromkeys(
                record.recovery_trigger_reason
                for record in records
                if record.recovery_trigger_reason and record.recovery_trigger_reason != "not_required"
            )
        )
        convergence_states = tuple(
            dict.fromkeys(
                record.convergence_state
                for record in records
                if record.convergence_state is not None
            )
        )
        manual_attention_observed = any(record.manual_attention for record in records)
        alerts = tuple(dict.fromkeys(alert for record in records for alert in record.alerts))
        scenario_passed = (
            records[-1].convergence_state == scenario.expected_final_convergence_state
            and (not scenario.expect_manual_attention or manual_attention_observed)
            and (not scenario.expect_recovery_trigger or bool(trigger_reasons))
        )
        return ReconciliationDisruptionScenarioSummary(
            scenario_id=scenario.scenario_id,
            description=scenario.description,
            scenario_passed=scenario_passed,
            total_steps=len(records),
            total_recovery_attempts=sum(record.recovery_attempt_count for record in records),
            persisted_attempt_count=len(snapshot.persisted_attempts),
            trigger_reasons=trigger_reasons,
            convergence_states=convergence_states,
            final_convergence_state=records[-1].convergence_state,
            manual_attention_observed=manual_attention_observed,
            unresolved_order_ids=snapshot.unresolved_order_ids,
            alerts=alerts,
            recorded_at=datetime.now(UTC),
        )


def build_default_reconciliation_disruption_scenarios() -> tuple[ReconciliationDisruptionScenario, ...]:
    """Return the default reconciliation disruption campaign."""

    return (
        ReconciliationDisruptionScenario(
            scenario_id="private_event_loss",
            description="private event loss triggers automatic REST recovery and terminal convergence",
            steps=(
                ReconciliationDisruptionStep(
                    step_id="gap-recovery",
                    expected_order_ids=("6101",),
                    private_payloads=(),
                    lookup_results=(
                        _lookup_success("6101", status_summary="filled"),
                    ),
                    has_gap=True,
                ),
            ),
            expected_final_convergence_state="converged_terminal",
            expect_recovery_trigger=True,
        ),
        ReconciliationDisruptionScenario(
            scenario_id="delayed_status_query",
            description="status lookup stays pending first, then converges on a later retry",
            steps=(
                ReconciliationDisruptionStep(
                    step_id="pending",
                    expected_order_ids=("6201",),
                    private_payloads=(),
                    lookup_results=(
                        _lookup_success("6201", status_summary="new"),
                        _lookup_success("6201", status_summary="new"),
                        _lookup_success("6201", status_summary="new"),
                    ),
                    has_gap=True,
                ),
                ReconciliationDisruptionStep(
                    step_id="resolved",
                    expected_order_ids=(),
                    private_payloads=(),
                    lookup_results=(
                        _lookup_success("6201", status_summary="filled"),
                    ),
                    has_gap=True,
                ),
            ),
            expected_final_convergence_state="converged_terminal",
            expect_recovery_trigger=True,
        ),
        ReconciliationDisruptionScenario(
            scenario_id="duplicated_execution_reports",
            description="duplicate execution reports stay deterministic without manual-attention escalation",
            steps=(
                ReconciliationDisruptionStep(
                    step_id="duplicate-trades",
                    expected_order_ids=("6301",),
                    private_payloads=(
                        _filled_trade_payload(order_id=6301, trade_id=16301),
                        _filled_trade_payload(order_id=6301, trade_id=16301),
                    ),
                ),
            ),
            expected_final_convergence_state="not_required",
        ),
        ReconciliationDisruptionScenario(
            scenario_id="partial_fill_reorder",
            description="reordered partial fills remain deterministic and avoid unnecessary escalation",
            steps=(
                ReconciliationDisruptionStep(
                    step_id="late-partial",
                    expected_order_ids=("6401",),
                    private_payloads=(
                        _partial_trade_payload(order_id=6401, trade_id=26402, cumulative="0.5", last="0.2"),
                    ),
                ),
                ReconciliationDisruptionStep(
                    step_id="early-partial-arrives-late",
                    expected_order_ids=("6401",),
                    private_payloads=(
                        _partial_trade_payload(order_id=6401, trade_id=26401, cumulative="0.3", last="0.3"),
                    ),
                ),
            ),
            expected_final_convergence_state="not_required",
        ),
    )


class _ScenarioLookupTransport:
    def __init__(self, results: tuple[BinanceOrderLookupResult, ...]) -> None:
        self._results = list(results)
        self._last_health: BinanceStatusQueryHealth | None = None

    def lookup_by_client_order_id(self, *, client_order_id: str) -> BinanceOrderLookupResult:
        return self._next("client_order_id", client_order_id)

    def lookup_by_exchange_order_id(self, *, exchange_order_id: str) -> BinanceOrderLookupResult:
        return self._next("exchange_order_id", exchange_order_id)

    def last_health(self) -> BinanceStatusQueryHealth | None:
        return self._last_health

    def _next(self, lookup_field: str, lookup_value: str) -> BinanceOrderLookupResult:
        result = self._results.pop(0) if self._results else _lookup_failure(lookup_value)
        self._last_health = BinanceStatusQueryHealth(
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            state=BinanceStatusQueryState.SUCCESS if result.found else BinanceStatusQueryState.FAILED,
            checked_at=_dt(0, 2),
            transport="reconciliation_disruption_lookup_transport",
            alert=result.alert,
        )
        return result


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
    )


def _lookup_success(order_id: str, *, status_summary: str) -> BinanceOrderLookupResult:
    return BinanceOrderLookupResult(
        found=True,
        lookup_field="exchange_order_id",
        lookup_value=order_id,
        source="reconciliation_disruption_lookup_transport",
        status_summary=status_summary,
        alert=None,
    )


def _lookup_failure(order_id: str) -> BinanceOrderLookupResult:
    return BinanceOrderLookupResult(
        found=False,
        lookup_field="exchange_order_id",
        lookup_value=order_id,
        source="reconciliation_disruption_lookup_transport",
        status_summary=None,
        alert="lookup unresolved",
    )


def _filled_trade_payload(*, order_id: int, trade_id: int) -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360000000,
        "s": "BTCUSDT",
        "c": f"client-{order_id}",
        "S": "BUY",
        "o": "MARKET",
        "X": "FILLED",
        "x": "TRADE",
        "q": "1",
        "z": "1",
        "l": "1",
        "L": "100",
        "Z": "100",
        "n": "1",
        "N": "USDT",
        "i": order_id,
        "t": trade_id,
        "m": False,
    }


def _partial_trade_payload(
    *,
    order_id: int,
    trade_id: int,
    cumulative: str,
    last: str,
) -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360005000,
        "s": "BTCUSDT",
        "c": f"client-{order_id}",
        "S": "BUY",
        "o": "LIMIT",
        "X": "PARTIALLY_FILLED",
        "x": "TRADE",
        "q": "1.0",
        "z": cumulative,
        "l": last,
        "L": "101500",
        "Z": "40600",
        "n": "0.05",
        "N": "USDT",
        "i": order_id,
        "t": trade_id,
        "p": "101500",
        "m": True,
    }


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
