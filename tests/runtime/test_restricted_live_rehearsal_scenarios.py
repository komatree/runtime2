"""End-to-end restricted-live rehearsal verification scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from pathlib import Path

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
from app.exchanges.binance import BinanceOrderClient
from app.exchanges.binance import BinanceOrderLookupResult
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinanceReconciliationService
from app.exchanges.binance import BinanceRestrictedLivePortfolioGate
from app.exchanges.binance import BinanceStatusQueryHealth
from app.exchanges.binance import BinanceStatusQueryState
from app.exchanges.binance import BinanceSymbolMapping
from app.exchanges.binance import BinanceClockSync
from app.monitoring import RestrictedLiveScenarioArtifactWriter
from app.monitoring import RestrictedLiveScenarioReportingService
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.storage import JsonBinanceReconciliationStateStore


def test_restricted_live_rehearsal_safe_mutation_scenario(tmp_path: Path) -> None:
    cycle, summary = _run_scenario(
        tmp_path=tmp_path,
        scenario_name="safe_mutation",
        payloads=(_filled_trade_payload(order_id=9001),),
        lookup_results=(),
        expected_order_ids=("9001",),
        expected_mutation_applied=True,
    )

    assert cycle.success is True
    assert "restricted-live portfolio mutation passed mandatory safeguard gate" in cycle.alerts
    assert summary.scenario_passed is True
    assert summary.mutation_applied is True


def test_restricted_live_rehearsal_ambiguous_mutation_blocked_scenario(tmp_path: Path) -> None:
    cycle, summary = _run_scenario(
        tmp_path=tmp_path,
        scenario_name="ambiguous_blocked",
        payloads=(
            {
                "e": "executionReport",
                "E": 1773360000000,
                "s": "BTCUSDT",
                "c": "client-bad",
                "S": "BUY",
            },
        ),
        lookup_results=(),
        expected_order_ids=("bad-order",),
        expected_mutation_applied=False,
    )

    assert cycle.success is False
    assert "restricted-live portfolio mutation blocked by mandatory safeguard gate" in cycle.alerts
    assert summary.scenario_passed is True
    assert summary.blocked_reasons


def test_restricted_live_rehearsal_unreconciled_blocked_scenario(tmp_path: Path) -> None:
    cycle, summary = _run_scenario(
        tmp_path=tmp_path,
        scenario_name="unreconciled_blocked",
        payloads=(_terminated_payload(),),
        lookup_results=(
            _lookup_failure("9101"),
            _lookup_failure("9101"),
            _lookup_failure("9101"),
        ),
        expected_order_ids=("9101", "9101", "9101"),
        expected_mutation_applied=False,
    )

    assert cycle.success is False
    assert "unreconciled_manual_attention" in summary.reconciliation_states
    assert summary.scenario_passed is True
    assert any("canonical private confirmation" in reason for reason in summary.blocked_reasons)


def test_restricted_live_rehearsal_mid_run_interruption_preserves_state_artifacts(tmp_path: Path) -> None:
    _, summary = _run_interrupted_scenario(
        tmp_path=tmp_path,
        scenario_name="mid_run_interruption",
        payloads=(_terminated_payload(),),
        lookup_results=(
            _lookup_failure("9201"),
            _lookup_failure("9201"),
            _lookup_failure("9201"),
        ),
        expected_order_ids=("9201", "9201", "9201"),
        expected_mutation_applied=False,
    )

    assert summary.scenario_passed is True
    assert summary.restart_count == 0
    assert summary.interruption_reason == "mid_run_interruption"
    assert summary.restored_unresolved_order_ids == ("9201",)
    artifact = json.loads(
        (
            tmp_path
            / "restricted_live_scenarios"
            / "mid_run_interruption"
            / "scenario_summary.json"
        ).read_text(encoding="utf-8")
    )
    markdown = (
        tmp_path
        / "restricted_live_scenarios"
        / "mid_run_interruption"
        / "scenario_summary.md"
    ).read_text(encoding="utf-8")
    assert artifact["interruption_reason"] == "mid_run_interruption"
    assert artifact["restored_unresolved_order_ids"] == ["9201"]
    assert "- interruption_reason: mid_run_interruption" in markdown
    assert "- restored_unresolved_order_ids: 9201" in markdown


def test_restricted_live_rehearsal_restart_with_unresolved_reconciliation_state(tmp_path: Path) -> None:
    _, summary = _run_restart_scenario(
        tmp_path=tmp_path,
        scenario_name="restart_unresolved_recovery",
        initial_payloads=(_terminated_payload(),),
        initial_lookup_results=(
            _lookup_failure("9301"),
            _lookup_failure("9301"),
            _lookup_failure("9301"),
        ),
        restart_payloads=(_filled_trade_payload(order_id=9301),),
        restart_lookup_results=(),
        expected_order_ids=("9301", "9301", "9301"),
        expected_mutation_applied=True,
        interruption_reason="restart_with_unresolved_reconciliation_state",
    )

    assert summary.scenario_passed is True
    assert summary.restart_count == 1
    assert summary.restored_unresolved_order_ids == ("9301",)
    assert summary.interruption_reason == "restart_with_unresolved_reconciliation_state"
    assert summary.mutation_applied is True
    artifact = json.loads(
        (
            tmp_path
            / "restricted_live_scenarios"
            / "restart_unresolved_recovery"
            / "scenario_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert artifact["restart_count"] == 1
    assert artifact["restored_unresolved_order_ids"] == ["9301"]
    assert artifact["mutation_applied"] is True


def test_restricted_live_rehearsal_restart_with_degraded_private_stream_state(tmp_path: Path) -> None:
    _, summary = _run_restart_scenario(
        tmp_path=tmp_path,
        scenario_name="restart_degraded_private_stream",
        initial_payloads=(),
        initial_lookup_results=(),
        restart_payloads=(_terminated_payload(),),
        restart_lookup_results=(
            _lookup_failure("9401"),
            _lookup_failure("9401"),
            _lookup_failure("9401"),
        ),
        expected_order_ids=("9401", "9401", "9401"),
        expected_mutation_applied=False,
        interruption_reason="restart_with_degraded_private_stream_state",
        initial_gap_active=True,
    )

    assert summary.scenario_passed is True
    assert summary.restored_gap_active is True
    assert summary.interruption_reason == "restart_with_degraded_private_stream_state"
    assert any("canonical private confirmation" in reason for reason in summary.blocked_reasons)
    markdown = (
        tmp_path
        / "restricted_live_scenarios"
        / "restart_degraded_private_stream"
        / "scenario_summary.md"
    ).read_text(encoding="utf-8")
    assert "- restored_gap_active: true" in markdown


def test_restricted_live_rehearsal_restart_with_blocked_portfolio_mutation_state(tmp_path: Path) -> None:
    _, summary = _run_restart_scenario(
        tmp_path=tmp_path,
        scenario_name="restart_blocked_mutation",
        initial_payloads=(_terminated_payload(),),
        initial_lookup_results=(
            _lookup_failure("9501"),
            _lookup_failure("9501"),
            _lookup_failure("9501"),
        ),
        restart_payloads=(
            {
                "e": "executionReport",
                "E": 1773360000000,
                "s": "BTCUSDT",
                "c": "client-bad",
                "S": "BUY",
            },
        ),
        restart_lookup_results=(),
        expected_order_ids=("9501", "9501", "9501"),
        expected_mutation_applied=False,
        interruption_reason="restart_with_blocked_portfolio_mutation_state",
    )

    assert summary.scenario_passed is True
    assert summary.restart_count == 1
    assert summary.interruption_reason == "restart_with_blocked_portfolio_mutation_state"
    assert summary.blocked_reasons
    artifact = json.loads(
        (
            tmp_path
            / "restricted_live_scenarios"
            / "restart_blocked_mutation"
            / "scenario_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert artifact["mutation_applied"] is False
    assert artifact["scenario_passed"] is True


@dataclass
class _RecordingGate:
    delegate: BinanceRestrictedLivePortfolioGate

    def __post_init__(self) -> None:
        self.last_outcome = None

    def apply(self, *, portfolio_state, expected_order_ids=(), already_applied_fill_ids=()):
        self.last_outcome = self.delegate.apply(
            portfolio_state=portfolio_state,
            expected_order_ids=expected_order_ids,
            already_applied_fill_ids=already_applied_fill_ids,
        )
        return self.last_outcome


@dataclass(frozen=True)
class _PayloadSource:
    payloads: tuple[dict[str, object], ...]

    def poll_private_payloads(self) -> tuple[dict[str, object], ...]:
        return self.payloads


class _LookupTransport:
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
        if self._results:
            result = self._results.pop(0)
        else:
            result = _lookup_failure(lookup_value)
        self._last_health = BinanceStatusQueryHealth(
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            state=BinanceStatusQueryState.SUCCESS if result.found else BinanceStatusQueryState.FAILED,
            checked_at=_dt(0, 2),
            transport="scenario_lookup_transport",
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
                rationale="restricted-live rehearsal scenario",
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
                reasons=("scenario allow",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class _PersistenceGateway:
    def __init__(self) -> None:
        self.cycles = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.cycles.append(cycle_result)


def _run_scenario(
    *,
    tmp_path: Path,
    scenario_name: str,
    payloads: tuple[dict[str, object], ...],
    lookup_results: tuple[BinanceOrderLookupResult, ...],
    expected_order_ids: tuple[str, ...],
    expected_mutation_applied: bool,
):
    persistence = _PersistenceGateway()
    gate = _RecordingGate(
        BinanceRestrictedLivePortfolioGate(
            payload_source=_PayloadSource(payloads=payloads),
            private_stream_client=BinancePrivateStreamClient(config=_config()),
            private_payload_translator=BinancePrivatePayloadTranslator(
                symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
            ),
            reconciliation_service=BinanceReconciliationService(),
            order_client=BinanceOrderClient(config=_config(), clock_sync=BinanceClockSync(_config())),
            lookup_transport=_LookupTransport(lookup_results),
        )
    )
    context = RuntimeContext(
        mode=RunnerMode.RESTRICTED_LIVE,
        feature_builder=_FeatureBuilder(),
        strategy_evaluator=_StrategyEvaluator(),
        risk_evaluator=_RiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence,
        venue_profile=_venue_profile(),
        execution_venue="binance",
        live_portfolio_mutation_gate=gate,
    )
    runner = RestrictedLiveRunner(context)
    cycle = runner.run_cycle(
        cycle_id=f"{scenario_name}-cycle",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        portfolio_state=_portfolio(),
        expected_live_order_ids=expected_order_ids,
    )

    reporting = RestrictedLiveScenarioReportingService()
    summary = reporting.build_summary(
        scenario_name=scenario_name,
        expected_mutation_applied=expected_mutation_applied,
        cycle_result=cycle,
        mutation_outcome=gate.last_outcome,
        recorded_at=_dt(0, 3),
    )
    writer = RestrictedLiveScenarioArtifactWriter(
        output_dir=tmp_path / "restricted_live_scenarios" / scenario_name,
    )
    json_path, markdown_path = writer.persist(
        summary=summary,
        markdown=reporting.render_markdown(summary=summary),
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["scenario_name"] == scenario_name
    assert payload["scenario_passed"] is True
    assert "# Restricted-Live Rehearsal Scenario" in markdown
    assert persistence.cycles[-1].cycle_id == cycle.cycle_id
    return cycle, summary


def _run_interrupted_scenario(
    *,
    tmp_path: Path,
    scenario_name: str,
    payloads: tuple[dict[str, object], ...],
    lookup_results: tuple[BinanceOrderLookupResult, ...],
    expected_order_ids: tuple[str, ...],
    expected_mutation_applied: bool,
):
    state_store = JsonBinanceReconciliationStateStore(
        state_path=tmp_path / "restricted_live_scenarios" / scenario_name / "reconciliation_state.json",
    )
    cycle, outcome = _run_cycle_with_gate(
        payloads=payloads,
        lookup_results=lookup_results,
        expected_order_ids=expected_order_ids,
        reconciliation_state_store=state_store,
    )
    snapshot = state_store.load_snapshot()
    summary, scenario_dir = _persist_summary(
        tmp_path=tmp_path,
        scenario_name=scenario_name,
        cycle=cycle,
        outcome=outcome,
        expected_mutation_applied=expected_mutation_applied,
        interruption_reason="mid_run_interruption",
        restored_unresolved_order_ids=snapshot.unresolved_order_ids,
        restored_gap_active=snapshot.gap_active,
    )
    state_payload = json.loads((scenario_dir / "reconciliation_state.json").read_text(encoding="utf-8"))
    assert state_payload["unresolved_order_ids"] == ["9201"]
    return cycle, summary


def _run_restart_scenario(
    *,
    tmp_path: Path,
    scenario_name: str,
    initial_payloads: tuple[dict[str, object], ...],
    initial_lookup_results: tuple[BinanceOrderLookupResult, ...],
    restart_payloads: tuple[dict[str, object], ...],
    restart_lookup_results: tuple[BinanceOrderLookupResult, ...],
    expected_order_ids: tuple[str, ...],
    expected_mutation_applied: bool,
    interruption_reason: str,
    initial_gap_active: bool = False,
):
    scenario_dir = tmp_path / "restricted_live_scenarios" / scenario_name
    state_store = JsonBinanceReconciliationStateStore(state_path=scenario_dir / "reconciliation_state.json")
    if initial_payloads or initial_lookup_results:
        _run_cycle_with_gate(
            payloads=initial_payloads,
            lookup_results=initial_lookup_results,
            expected_order_ids=expected_order_ids,
            reconciliation_state_store=state_store,
        )
    if initial_gap_active:
        state_store.persist_workflow_state(
            workflow=BinanceReconciliationService().coordinate_recovery(
                reconciliation_result=BinanceReconciliationService().reconcile(
                    expected_order_ids=("9401",),
                    private_events=(),
                ),
            ),
            occurred_at=_dt(0, 2),
            cursor_token="restart-gap",
            has_gap=True,
        )
    restored_snapshot = state_store.load_snapshot()
    cycle, outcome = _run_cycle_with_gate(
        payloads=restart_payloads,
        lookup_results=restart_lookup_results,
        expected_order_ids=expected_order_ids,
        reconciliation_state_store=state_store,
    )
    summary, _ = _persist_summary(
        tmp_path=tmp_path,
        scenario_name=scenario_name,
        cycle=cycle,
        outcome=outcome,
        expected_mutation_applied=expected_mutation_applied,
        restart_count=1,
        interruption_reason=interruption_reason,
        restored_unresolved_order_ids=restored_snapshot.unresolved_order_ids,
        restored_gap_active=restored_snapshot.gap_active,
    )
    return cycle, summary


def _run_cycle_with_gate(
    *,
    payloads: tuple[dict[str, object], ...],
    lookup_results: tuple[BinanceOrderLookupResult, ...],
    expected_order_ids: tuple[str, ...],
    reconciliation_state_store,
):
    persistence = _PersistenceGateway()
    gate = _RecordingGate(
        BinanceRestrictedLivePortfolioGate(
            payload_source=_PayloadSource(payloads=payloads),
            private_stream_client=BinancePrivateStreamClient(config=_config()),
            private_payload_translator=BinancePrivatePayloadTranslator(
                symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
            ),
            reconciliation_service=BinanceReconciliationService(),
            order_client=BinanceOrderClient(config=_config(), clock_sync=BinanceClockSync(_config())),
            lookup_transport=_LookupTransport(lookup_results),
            reconciliation_state_store=reconciliation_state_store,
        )
    )
    context = RuntimeContext(
        mode=RunnerMode.RESTRICTED_LIVE,
        feature_builder=_FeatureBuilder(),
        strategy_evaluator=_StrategyEvaluator(),
        risk_evaluator=_RiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=persistence,
        venue_profile=_venue_profile(),
        execution_venue="binance",
        live_portfolio_mutation_gate=gate,
    )
    cycle = RestrictedLiveRunner(context).run_cycle(
        cycle_id="restart-cycle",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        portfolio_state=_portfolio(),
        expected_live_order_ids=expected_order_ids,
    )
    assert persistence.cycles[-1].cycle_id == cycle.cycle_id
    return cycle, gate.last_outcome


def _persist_summary(
    *,
    tmp_path: Path,
    scenario_name: str,
    cycle,
    outcome,
    expected_mutation_applied: bool,
    restart_count: int = 0,
    interruption_reason: str | None = None,
    restored_unresolved_order_ids: tuple[str, ...] = (),
    restored_gap_active: bool = False,
):
    reporting = RestrictedLiveScenarioReportingService()
    summary = reporting.build_summary(
        scenario_name=scenario_name,
        expected_mutation_applied=expected_mutation_applied,
        cycle_result=cycle,
        mutation_outcome=outcome,
        recorded_at=_dt(0, 3),
        restart_count=restart_count,
        interruption_reason=interruption_reason,
        restored_unresolved_order_ids=restored_unresolved_order_ids,
        restored_gap_active=restored_gap_active,
    )
    scenario_dir = tmp_path / "restricted_live_scenarios" / scenario_name
    writer = RestrictedLiveScenarioArtifactWriter(output_dir=scenario_dir)
    json_path, markdown_path = writer.persist(
        summary=summary,
        markdown=reporting.render_markdown(summary=summary),
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["scenario_name"] == scenario_name
    assert payload["scenario_passed"] is True
    assert "# Restricted-Live Rehearsal Scenario" in markdown
    return summary, scenario_dir


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


def _filled_trade_payload(*, order_id: int) -> dict[str, object]:
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
        "t": order_id + 1000,
        "m": False,
    }


def _terminated_payload() -> dict[str, object]:
    return {
        "e": "listenKeyExpired",
        "E": 1773360000000,
    }


def _lookup_failure(order_id: str) -> BinanceOrderLookupResult:
    return BinanceOrderLookupResult(
        found=False,
        lookup_field="exchange_order_id",
        lookup_value=order_id,
        source="signed_rest_order_lookup",
        status_summary=None,
        alert="lookup unresolved",
    )


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
