"""Restricted-live failure-injection campaign for deterministic rehearsal."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceClockSync
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinanceOrderLookupResult
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinancePrivateStreamHealth
from app.exchanges.binance import BinancePrivateStreamState
from app.exchanges.binance import BinanceRestrictedLivePortfolioGate
from app.exchanges.binance import BinanceStatusQueryHealth
from app.exchanges.binance import BinanceStatusQueryState
from app.exchanges.binance import BinanceSymbolMapping
from app.exchanges.binance import BinanceReconciliationService
from app.monitoring.exchange_health import BinanceExchangeHealthService
from app.monitoring.models import ExchangeHealthSnapshot
from app.monitoring.restricted_live_soak import RecordingRestrictedLiveGate
from app.monitoring.restricted_live_soak import RestrictedLiveSoakExchangeHealthProvider
from app.portfolio import LivePortfolioMutationOutcome
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.storage.reconciliation_state import JsonBinanceReconciliationStateStore


def _artifact_json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class RestrictedLiveFailureCyclePlan:
    """One deterministic cycle input for failure-injection rehearsal."""

    cycle_label: str
    payloads: tuple[dict[str, object], ...]
    expected_order_ids: tuple[str, ...] = ()
    lookup_results: tuple[BinanceOrderLookupResult, ...] = ()
    private_stream_health: BinancePrivateStreamHealth | None = None


@dataclass(frozen=True)
class RestrictedLiveFailureScenario:
    """One operator-readable failure-injection scenario."""

    scenario_id: str
    description: str
    cycles: tuple[RestrictedLiveFailureCyclePlan, ...]
    expected_final_mutation_applied: bool
    expect_recovery_trigger: bool = False
    expect_manual_attention: bool = False
    expect_blocked_mutation: bool = False
    expect_ignored_duplicate_fill: bool = False
    expect_degraded_exchange_health: bool = False


@dataclass(frozen=True)
class RestrictedLiveFailureCycleRecord:
    """Inspectable record for one failure-injection cycle."""

    cycle_index: int
    cycle_id: str
    cycle_success: bool
    mutation_attempted: bool
    mutation_applied: bool
    blocked_reasons: tuple[str, ...]
    ignored_fill_ids: tuple[str, ...]
    pending_order_ids: tuple[str, ...]
    reconciliation_states: tuple[str, ...]
    recovery_trigger_reason: str | None
    convergence_state: str | None
    exchange_health_state: str | None
    private_stream_state: str | None
    status_query_states: tuple[str, ...]
    reconnect_attempts: int
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class RestrictedLiveFailureScenarioSummary:
    """Operator-facing summary for one failure-injection scenario."""

    scenario_id: str
    description: str
    scenario_passed: bool
    total_cycles: int
    blocked_mutation_count: int
    applied_mutation_count: int
    ignored_duplicate_fill_count: int
    recovery_trigger_reasons: tuple[str, ...]
    final_convergence_state: str | None
    manual_attention_observed: bool
    exchange_health_states: tuple[str, ...]
    final_exchange_health_state: str | None
    reconnect_attempt_high_watermark: int
    operator_visibility_confirmed: bool
    alerts: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True)
class RestrictedLiveFailureScenarioRun:
    """Full scenario output including cycle records and summary."""

    summary: RestrictedLiveFailureScenarioSummary
    cycle_records: tuple[RestrictedLiveFailureCycleRecord, ...]


@dataclass(frozen=True)
class RestrictedLiveFailureArtifactPaths:
    """Artifact locations for one failure-injection scenario."""

    cycle_records_path: Path
    summary_json_path: Path
    summary_markdown_path: Path


@dataclass(frozen=True)
class RestrictedLiveFailureInjectionArtifactWriter:
    """Persist scenario artifacts under one scenario-specific directory."""

    output_dir: Path

    def persist(
        self,
        *,
        run: RestrictedLiveFailureScenarioRun,
        markdown: str,
    ) -> RestrictedLiveFailureArtifactPaths:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cycle_records_path = self.output_dir / "scenario_cycles.jsonl"
        summary_json_path = self.output_dir / "scenario_summary.json"
        summary_markdown_path = self.output_dir / "scenario_summary.md"
        with cycle_records_path.open("w", encoding="utf-8") as handle:
            for record in run.cycle_records:
                handle.write(json.dumps(asdict(record), default=_artifact_json_default, sort_keys=True))
                handle.write("\n")
        summary_json_path.write_text(
            json.dumps(asdict(run.summary), default=_artifact_json_default, sort_keys=True),
            encoding="utf-8",
        )
        summary_markdown_path.write_text(markdown, encoding="utf-8")
        return RestrictedLiveFailureArtifactPaths(
            cycle_records_path=cycle_records_path,
            summary_json_path=summary_json_path,
            summary_markdown_path=summary_markdown_path,
        )


@dataclass(frozen=True)
class RestrictedLiveFailureInjectionReportingService:
    """Render short operator-facing markdown for failure-injection scenarios."""

    def render_markdown(self, *, run: RestrictedLiveFailureScenarioRun) -> str:
        reasons = ", ".join(run.summary.recovery_trigger_reasons) or "none"
        exchange_states = ", ".join(run.summary.exchange_health_states) or "none"
        alerts = ", ".join(run.summary.alerts) or "none"
        return "\n".join(
            [
                "# Restricted-Live Failure Injection Scenario",
                f"- scenario_id: {run.summary.scenario_id}",
                f"- description: {run.summary.description}",
                f"- scenario_passed: {str(run.summary.scenario_passed).lower()}",
                f"- total_cycles: {run.summary.total_cycles}",
                f"- blocked_mutation_count: {run.summary.blocked_mutation_count}",
                f"- applied_mutation_count: {run.summary.applied_mutation_count}",
                f"- ignored_duplicate_fill_count: {run.summary.ignored_duplicate_fill_count}",
                f"- recovery_trigger_reasons: {reasons}",
                f"- final_convergence_state: {run.summary.final_convergence_state or 'none'}",
                f"- manual_attention_observed: {str(run.summary.manual_attention_observed).lower()}",
                f"- exchange_health_states: {exchange_states}",
                f"- final_exchange_health_state: {run.summary.final_exchange_health_state or 'none'}",
                f"- reconnect_attempt_high_watermark: {run.summary.reconnect_attempt_high_watermark}",
                f"- operator_visibility_confirmed: {str(run.summary.operator_visibility_confirmed).lower()}",
                f"- alerts: {alerts}",
            ]
        )


@dataclass(frozen=True)
class RestrictedLiveFailureInjectionRunner:
    """Run deterministic restricted-live failure-injection scenarios."""

    output_root: Path

    def run_scenario(self, *, scenario: RestrictedLiveFailureScenario) -> RestrictedLiveFailureScenarioRun:
        scenario_dir = self.output_root / scenario.scenario_id
        state_store = JsonBinanceReconciliationStateStore(
            state_path=scenario_dir / "reconciliation_state.json",
        )
        cycle_records: list[RestrictedLiveFailureCycleRecord] = []
        current_portfolio = _portfolio()
        already_applied_fill_ids: tuple[str, ...] = ()

        for cycle_index, plan in enumerate(scenario.cycles, start=1):
            payload_source = _ScenarioPayloadSource(
                payloads=plan.payloads,
                private_stream_health=plan.private_stream_health,
            )
            gate = RecordingRestrictedLiveGate(
                BinanceRestrictedLivePortfolioGate(
                    payload_source=payload_source,
                    private_stream_client=BinancePrivateStreamClient(config=_config()),
                    private_payload_translator=BinancePrivatePayloadTranslator(
                        symbol_mappings=(
                            BinanceSymbolMapping(
                                instrument_id="BTC-USDT",
                                venue_symbol="BTCUSDT",
                            ),
                        ),
                    ),
                    reconciliation_service=BinanceReconciliationService(),
                    order_client=BinanceOrderClient(
                        config=_config(),
                        clock_sync=BinanceClockSync(_config()),
                    ),
                    lookup_transport=_ScenarioLookupTransport(plan.lookup_results),
                    reconciliation_state_store=state_store,
                )
            )
            persistence = _FailureInjectionPersistenceGateway()
            provider = RestrictedLiveSoakExchangeHealthProvider(
                health_service=BinanceExchangeHealthService(),
                payload_source=payload_source,
                recording_gate=gate,
            )
            runner = RestrictedLiveRunner(
                RuntimeContext(
                    mode=RunnerMode.RESTRICTED_LIVE,
                    feature_builder=_FeatureBuilder(),
                    strategy_evaluator=_StrategyEvaluator(),
                    risk_evaluator=_RiskEvaluator(),
                    execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
                    persistence_gateway=persistence,
                    venue_profile=_venue_profile(),
                    execution_venue="binance",
                    live_portfolio_mutation_gate=gate,
                    exchange_health_provider=provider,
                )
            )
            cycle = runner.run_cycle(
                cycle_id=f"{scenario.scenario_id}-{plan.cycle_label}",
                instrument=_instrument(),
                bar_slice=_bar_slice(),
                portfolio_state=current_portfolio,
                expected_live_order_ids=plan.expected_order_ids,
                already_applied_fill_ids=already_applied_fill_ids,
            )
            gate_result = gate.last_result
            assert gate_result is not None
            mutation_outcome = gate_result.mutation_outcome
            if mutation_outcome.mutation_applied:
                current_portfolio = mutation_outcome.portfolio_state
            already_applied_fill_ids = tuple(
                dict.fromkeys(
                    (
                        *already_applied_fill_ids,
                        *mutation_outcome.translation_result.applied_fill_ids,
                    )
                )
            )
            exchange_health = persistence.latest_exchange_health()
            workflow = None if gate_result.transport_result is None else gate_result.transport_result.workflow_result
            cycle_records.append(
                RestrictedLiveFailureCycleRecord(
                    cycle_index=cycle_index,
                    cycle_id=cycle.cycle_id,
                    cycle_success=cycle.success,
                    mutation_attempted=mutation_outcome.mutation_attempted,
                    mutation_applied=mutation_outcome.mutation_applied,
                    blocked_reasons=tuple(
                        alert
                        for alert in mutation_outcome.alerts
                        if "blocked" in alert or "mismatch" in alert or "malformed" in alert
                    ),
                    ignored_fill_ids=mutation_outcome.translation_result.ignored_fill_ids,
                    pending_order_ids=mutation_outcome.translation_result.pending_order_ids,
                    reconciliation_states=tuple(
                        event.reconciliation_state.value for event in cycle.reconciliation_events
                    ),
                    recovery_trigger_reason=(
                        None if workflow is None else workflow.recovery_trigger_reason
                    ),
                    convergence_state=(
                        None if workflow is None else workflow.convergence_state
                    ),
                    exchange_health_state=(
                        None if exchange_health is None else exchange_health.overall_state.value
                    ),
                    private_stream_state=(
                        None
                        if exchange_health is None
                        else exchange_health.private_stream.state.value
                    ),
                    status_query_states=tuple(
                        health.state.value
                        for health in (
                            ()
                            if gate_result.transport_result is None
                            else gate_result.transport_result.status_query_health
                        )
                    ),
                    reconnect_attempts=(
                        0
                        if plan.private_stream_health is None
                        else plan.private_stream_health.reconnect_attempts
                    ),
                    alerts=cycle.alerts,
                )
            )

        summary = self._build_summary(scenario=scenario, cycle_records=tuple(cycle_records))
        return RestrictedLiveFailureScenarioRun(summary=summary, cycle_records=tuple(cycle_records))

    def run_campaign(
        self,
        *,
        scenarios: tuple[RestrictedLiveFailureScenario, ...],
    ) -> tuple[RestrictedLiveFailureArtifactPaths, ...]:
        reporting = RestrictedLiveFailureInjectionReportingService()
        persisted: list[RestrictedLiveFailureArtifactPaths] = []
        for scenario in scenarios:
            run = self.run_scenario(scenario=scenario)
            persisted.append(
                RestrictedLiveFailureInjectionArtifactWriter(
                    output_dir=self.output_root / scenario.scenario_id,
                ).persist(
                    run=run,
                    markdown=reporting.render_markdown(run=run),
                )
            )
        return tuple(persisted)

    def _build_summary(
        self,
        *,
        scenario: RestrictedLiveFailureScenario,
        cycle_records: tuple[RestrictedLiveFailureCycleRecord, ...],
    ) -> RestrictedLiveFailureScenarioSummary:
        blocked_mutation_count = sum(1 for record in cycle_records if record.blocked_reasons)
        applied_mutation_count = sum(1 for record in cycle_records if record.mutation_applied)
        ignored_duplicate_fill_count = sum(len(record.ignored_fill_ids) for record in cycle_records)
        recovery_trigger_reasons = tuple(
            dict.fromkeys(
                record.recovery_trigger_reason
                for record in cycle_records
                if record.recovery_trigger_reason
                and record.recovery_trigger_reason != "not_required"
            )
        )
        exchange_health_states = tuple(
            dict.fromkeys(
                record.exchange_health_state
                for record in cycle_records
                if record.exchange_health_state is not None
            )
        )
        final_record = cycle_records[-1]
        manual_attention_observed = any(
            "unreconciled_manual_attention" in record.reconciliation_states
            or record.convergence_state == "unreconciled_manual_attention"
            for record in cycle_records
        )
        operator_visibility_confirmed = any(
            (record.exchange_health_state is not None)
            and (record.alerts or record.recovery_trigger_reason or record.blocked_reasons)
            for record in cycle_records
        )
        alerts = tuple(dict.fromkeys(alert for record in cycle_records for alert in record.alerts))
        scenario_passed = (
            final_record.mutation_applied is scenario.expected_final_mutation_applied
            and (not scenario.expect_recovery_trigger or bool(recovery_trigger_reasons))
            and (not scenario.expect_manual_attention or manual_attention_observed)
            and (not scenario.expect_blocked_mutation or blocked_mutation_count > 0)
            and (not scenario.expect_ignored_duplicate_fill or ignored_duplicate_fill_count > 0)
            and (
                not scenario.expect_degraded_exchange_health
                or any(state in {"degraded", "fatal"} for state in exchange_health_states)
            )
            and operator_visibility_confirmed
        )
        return RestrictedLiveFailureScenarioSummary(
            scenario_id=scenario.scenario_id,
            description=scenario.description,
            scenario_passed=scenario_passed,
            total_cycles=len(cycle_records),
            blocked_mutation_count=blocked_mutation_count,
            applied_mutation_count=applied_mutation_count,
            ignored_duplicate_fill_count=ignored_duplicate_fill_count,
            recovery_trigger_reasons=recovery_trigger_reasons,
            final_convergence_state=final_record.convergence_state,
            manual_attention_observed=manual_attention_observed,
            exchange_health_states=exchange_health_states,
            final_exchange_health_state=final_record.exchange_health_state,
            reconnect_attempt_high_watermark=max(
                (record.reconnect_attempts for record in cycle_records),
                default=0,
            ),
            operator_visibility_confirmed=operator_visibility_confirmed,
            alerts=alerts,
            recorded_at=datetime.now(UTC),
        )


def build_default_failure_injection_scenarios() -> tuple[RestrictedLiveFailureScenario, ...]:
    """Return the default restricted-live failure-injection campaign."""

    return (
        RestrictedLiveFailureScenario(
            scenario_id="private_stream_disconnect",
            description="private stream terminates and reconciliation escalates to manual attention",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="cycle-1",
                    payloads=(_terminated_payload(event_type="eventStreamTerminated"),),
                    expected_order_ids=("9101",),
                    lookup_results=(
                        _lookup_failure("9101"),
                        _lookup_failure("9101"),
                        _lookup_failure("9101"),
                    ),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.TERMINATED,
                        reconnect_attempts=1,
                        alerts=("private stream disconnected",),
                        authoritative=False,
                    ),
                ),
            ),
            expected_final_mutation_applied=False,
            expect_recovery_trigger=True,
            expect_manual_attention=True,
            expect_blocked_mutation=True,
            expect_degraded_exchange_health=True,
        ),
        RestrictedLiveFailureScenario(
            scenario_id="listen_key_expiration",
            description="listen-key expiry blocks mutation first, then resumes after a later fill arrives",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="expired",
                    payloads=(_terminated_payload(event_type="listenKeyExpired"),),
                    expected_order_ids=("9201",),
                    lookup_results=(
                        _lookup_success("9201", status_summary="filled"),
                    ),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.TERMINATED,
                        reconnect_attempts=1,
                        alerts=("listen key expired",),
                        authoritative=False,
                    ),
                ),
                RestrictedLiveFailureCyclePlan(
                    cycle_label="recovered",
                    payloads=(_filled_trade_payload(order_id=9201, trade_id=19201),),
                    expected_order_ids=("9201",),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.STREAMING,
                        reconnect_attempts=1,
                    ),
                ),
            ),
            expected_final_mutation_applied=True,
            expect_recovery_trigger=True,
            expect_blocked_mutation=True,
            expect_degraded_exchange_health=True,
        ),
        RestrictedLiveFailureScenario(
            scenario_id="websocket_reconnect_storms",
            description="reconnect storms remain operator-visible and keep exchange health degraded",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="storm-1",
                    payloads=(),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=2,
                        alerts=("heartbeat overdue", "reconnect storm"),
                        authoritative=False,
                    ),
                ),
                RestrictedLiveFailureCyclePlan(
                    cycle_label="storm-2",
                    payloads=(),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=5,
                        alerts=("heartbeat overdue", "reconnect storm"),
                        authoritative=False,
                    ),
                ),
                RestrictedLiveFailureCyclePlan(
                    cycle_label="storm-3",
                    payloads=(),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.DEGRADED,
                        reconnect_attempts=8,
                        alerts=("heartbeat overdue", "reconnect storm"),
                        authoritative=False,
                    ),
                ),
            ),
            expected_final_mutation_applied=False,
            expect_degraded_exchange_health=True,
        ),
        RestrictedLiveFailureScenario(
            scenario_id="delayed_private_events",
            description="missing private updates recover first through REST, then the late fill arrives safely",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="delayed",
                    payloads=(_account_update_payload(),),
                    expected_order_ids=("9301",),
                    lookup_results=(
                        _lookup_success("9301", status_summary="filled"),
                    ),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.STREAMING,
                        reconnect_attempts=0,
                    ),
                ),
                RestrictedLiveFailureCyclePlan(
                    cycle_label="late-fill",
                    payloads=(_filled_trade_payload(order_id=9301, trade_id=19301),),
                    expected_order_ids=("9301",),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.STREAMING,
                        reconnect_attempts=0,
                    ),
                ),
            ),
            expected_final_mutation_applied=True,
            expect_recovery_trigger=True,
            expect_blocked_mutation=True,
        ),
        RestrictedLiveFailureScenario(
            scenario_id="missing_order_events",
            description="expected order updates never arrive and reconciliation escalates manually",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="missing",
                    payloads=(_account_update_payload(),),
                    expected_order_ids=("9401",),
                    lookup_results=(
                        _lookup_failure("9401"),
                        _lookup_failure("9401"),
                        _lookup_failure("9401"),
                    ),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.STREAMING,
                        reconnect_attempts=0,
                    ),
                ),
            ),
            expected_final_mutation_applied=False,
            expect_recovery_trigger=True,
            expect_manual_attention=True,
            expect_blocked_mutation=True,
            expect_degraded_exchange_health=True,
        ),
        RestrictedLiveFailureScenario(
            scenario_id="duplicated_fill_events",
            description="duplicate fills are deduplicated so mutation applies once without double counting",
            cycles=(
                RestrictedLiveFailureCyclePlan(
                    cycle_label="duplicate-fill",
                    payloads=(
                        _filled_trade_payload(order_id=9501, trade_id=19501),
                        _filled_trade_payload(order_id=9501, trade_id=19501),
                    ),
                    expected_order_ids=("9501",),
                    private_stream_health=_private_health(
                        state=BinancePrivateStreamState.STREAMING,
                        reconnect_attempts=0,
                    ),
                ),
            ),
            expected_final_mutation_applied=True,
            expect_ignored_duplicate_fill=True,
        ),
    )


@dataclass(frozen=True)
class _ScenarioPayloadSource:
    payloads: tuple[dict[str, object], ...]
    private_stream_health: BinancePrivateStreamHealth | None

    def poll_private_payloads(self) -> tuple[dict[str, object], ...]:
        return self.payloads

    def current_health(self) -> BinancePrivateStreamHealth | None:
        return self.private_stream_health


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
            state=(
                BinanceStatusQueryState.SUCCESS
                if result.found
                else BinanceStatusQueryState.FAILED
            ),
            checked_at=_dt(0, 2),
            transport="failure_injection_lookup_transport",
            alert=result.alert,
        )
        return result


class _FeatureBuilder:
    def build(self, bar_slice: BarSlice, context_bar_slice: BarSlice | None = None) -> FeatureSnapshot:
        return FeatureSnapshot(
            instrument_id=bar_slice.instrument_id,
            timeframe=bar_slice.timeframe,
            as_of=bar_slice.end_time,
            feature_values={"candle.close_return_1": Decimal("0.02")},
            source_bar_count=2,
            is_complete=True,
        )


class _StrategyEvaluator:
    def evaluate(self, context):
        return (
            SignalDecision(
                strategy_name="breakout_v1",
                instrument_id=context.instrument.instrument_id,
                timeframe=context.features.timeframe,
                as_of=context.as_of,
                side=SignalSide.BUY,
                confidence=Decimal("0.8"),
                rationale="restricted-live failure injection",
                target_quantity=Decimal("1"),
            ),
        )


class _RiskEvaluator:
    def evaluate(self, signals, portfolio_state, venue_profile):
        return tuple(
            RiskDecision(
                signal=signal,
                status=RiskDecisionStatus.ALLOW,
                evaluated_at=signal.as_of,
                reasons=("failure injection allow",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class _FailureInjectionPersistenceGateway:
    def __init__(self) -> None:
        self.records: list[tuple[Any, ExchangeHealthSnapshot | None]] = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.records.append((cycle_result, exchange_health))

    def latest_exchange_health(self) -> ExchangeHealthSnapshot | None:
        return None if not self.records else self.records[-1][1]


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
    )


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(
        as_of=_dt(0, 2),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _bar_slice() -> BarSlice:
    return BarSlice(
        instrument_id="BTC-USDT",
        timeframe="1m",
        end_time=_dt(0, 2),
        candles=(
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 0),
                close_time=_dt(0, 1),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
            ),
            Candle(
                instrument_id="BTC-USDT",
                timeframe="1m",
                open_time=_dt(0, 1),
                close_time=_dt(0, 2),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("100"),
                close=Decimal("101"),
                volume=Decimal("1"),
            ),
        ),
    )


def _venue_profile() -> VenueProfile:
    return VenueProfile(
        venue="binance",
        account_scope="spot",
        maker_fee_bps=Decimal("7"),
        taker_fee_bps=Decimal("10"),
        supports_market_orders=True,
        supports_post_only=True,
        default_time_in_force=TimeInForce.GTC,
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    )


def _private_health(
    *,
    state: BinancePrivateStreamState,
    reconnect_attempts: int,
    alerts: tuple[str, ...] = (),
    authoritative: bool | None = None,
) -> BinancePrivateStreamHealth:
    return BinancePrivateStreamHealth(
        state=state,
        reconnect_attempts=reconnect_attempts,
        last_message_at=_dt(0, 1),
        session_expires_at=_dt(1, 0),
        is_authoritative=(
            state is BinancePrivateStreamState.STREAMING
            if authoritative is None
            else authoritative
        ),
        alerts=alerts,
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


def _account_update_payload() -> dict[str, object]:
    return {
        "e": "outboundAccountPosition",
        "E": 1773360010000,
        "B": [
            {"a": "USDT", "f": "1000", "l": "25"},
            {"a": "BTC", "f": "0.25", "l": "0"},
        ],
    }


def _terminated_payload(*, event_type: str) -> dict[str, object]:
    return {
        "e": event_type,
        "E": int(_dt(0, 0).timestamp() * 1000),
    }


def _lookup_failure(order_id: str) -> BinanceOrderLookupResult:
    return BinanceOrderLookupResult(
        found=False,
        lookup_field="exchange_order_id",
        lookup_value=order_id,
        source="failure_injection_lookup_transport",
        status_summary=None,
        alert="lookup unresolved",
    )


def _lookup_success(order_id: str, *, status_summary: str) -> BinanceOrderLookupResult:
    return BinanceOrderLookupResult(
        found=True,
        lookup_field="exchange_order_id",
        lookup_value=order_id,
        source="failure_injection_lookup_transport",
        status_summary=status_summary,
        alert=None,
    )


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
