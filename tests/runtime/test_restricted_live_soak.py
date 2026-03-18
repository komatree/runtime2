from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.contracts import BarSlice
from app.contracts import AccountSnapshot
from app.contracts import AssetBalanceSnapshot
from app.contracts import Candle
from app.contracts import FeatureSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import ReconciliationEvent
from app.contracts import ReconciliationState
from app.contracts import RiskDecision
from app.contracts import RiskDecisionStatus
from app.contracts import SignalDecision
from app.contracts import SignalSide
from app.contracts import TimeInForce
from app.contracts import VenueProfile
from app.execution import ReportOnlyExecutionIntentBuilder
from app.monitoring import BinanceExchangeHealthService
from app.monitoring import RecordingRestrictedLiveGate
from app.monitoring import RestrictedLiveSoakArtifactWriter
from app.monitoring import RestrictedLiveSoakExchangeHealthProvider
from app.monitoring import RestrictedLiveSoakReportingService
from app.monitoring import RestrictedLiveSoakRunner
from app.monitoring import RestrictedLiveSoakStopCriteria
from app.portfolio import LivePortfolioMutationOutcome
from app.portfolio import LivePortfolioTranslationResult
from app.portfolio import LiveTranslationStatus
from app.runtime import RestrictedLiveRunner
from app.runtime import RunnerMode
from app.runtime import RuntimeContext
from app.exchanges.binance import BinancePrivateStreamHealth
from app.exchanges.binance import BinancePrivateStreamState
from app.exchanges.binance import BinanceRestrictedLiveGateResult
from app.exchanges.binance import BinanceStatusQueryHealth
from app.exchanges.binance import BinanceStatusQueryState
from scripts.binance_restricted_live_soak_campaign import build_campaign_sessions


def test_restricted_live_soak_persists_artifacts_and_aborts_on_block_threshold(tmp_path: Path) -> None:
    payload_source = _SequencePayloadSource(
        healths=(
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
        ),
        stats=(
            _stats(reconnect_count=0),
            _stats(reconnect_count=1, heartbeat_overdue_events=1),
        ),
    )
    gate = RecordingRestrictedLiveGate(
        _SequenceGateDelegate(
            payload_source=payload_source,
            plans=(
                _gate_result(mutation_applied=False, status_query_count=1),
                _gate_result(mutation_applied=False, status_query_count=1),
            ),
        )
    )
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )
    runner = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    )

    run = runner.run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=5, max_blocked_mutations=2),
        cycle_id_prefix="soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )
    writer = RestrictedLiveSoakArtifactWriter(output_dir=tmp_path)
    artifact_paths = writer.persist(
        run=run,
        markdown=RestrictedLiveSoakReportingService().render_markdown(run=run),
    )

    assert run.summary.aborted is True
    assert run.summary.stop_reason == "max_blocked_mutations"
    assert run.summary.completed_cycles == 2
    assert json.loads(artifact_paths.summary_json_path.read_text(encoding="utf-8"))["blocked_mutation_count"] == 2
    assert "stop_reason: max_blocked_mutations" in artifact_paths.summary_markdown_path.read_text(encoding="utf-8")
    assert len(artifact_paths.health_transitions_path.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert artifact_paths.reconnect_events_path.exists()
    assert artifact_paths.listen_key_refresh_path.exists()
    assert artifact_paths.reconciliation_events_path.exists()
    assert len(artifact_paths.reconnect_events_path.read_text(encoding="utf-8").strip().splitlines()) == 1
    assert len(artifact_paths.listen_key_refresh_path.read_text(encoding="utf-8").splitlines()) == 0
    assert len(artifact_paths.reconciliation_events_path.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert run.summary.reconciliation_recovery_attempts == 2
    assert run.summary.reconciliation_recovery_success_rate == 0.0


def test_restricted_live_soak_aborts_on_fatal_exchange_health(tmp_path: Path) -> None:
    payload_source = _SequencePayloadSource(
        healths=(_private_health(BinancePrivateStreamState.TERMINATED),),
        stats=(_stats(),),
    )
    gate = RecordingRestrictedLiveGate(
        _SequenceGateDelegate(
            payload_source=payload_source,
            plans=(
                _gate_result(mutation_applied=False, status_query_count=0),
            ),
        )
    )
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )
    runner = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    )

    run = runner.run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=3),
        cycle_id_prefix="fatal-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )

    assert run.summary.aborted is True
    assert run.summary.stop_reason == "fatal_exchange_health"
    assert run.summary.completed_cycles == 1
    assert run.transitions[0].exchange_health_state == "fatal"


def test_restricted_live_soak_records_refresh_events_and_success_rate(tmp_path: Path) -> None:
    payload_source = _SequencePayloadSource(
        healths=(_private_health(BinancePrivateStreamState.STREAMING),),
        stats=(_stats(refresh_attempts=1, last_refresh_result="success"),),
    )
    gate = RecordingRestrictedLiveGate(
        _SequenceGateDelegate(
            payload_source=payload_source,
            plans=(_gate_result(mutation_applied=True, status_query_count=1),),
        )
    )
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )
    run = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=1),
        cycle_id_prefix="refresh-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )
    artifact_paths = RestrictedLiveSoakArtifactWriter(output_dir=tmp_path).persist(
        run=run,
        markdown=RestrictedLiveSoakReportingService().render_markdown(run=run),
    )

    refresh_rows = [
        json.loads(line)
        for line in artifact_paths.listen_key_refresh_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    reconciliation_rows = [
        json.loads(line)
        for line in artifact_paths.reconciliation_events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert refresh_rows[0]["result"] == "success"
    assert reconciliation_rows[0]["convergence_state"] == "converged_terminal"
    assert run.summary.reconciliation_recovery_success_rate == 1.0


def test_restricted_live_soak_persists_account_update_events(tmp_path: Path) -> None:
    payload_source = _SequencePayloadSource(
        healths=(_private_health(BinancePrivateStreamState.STREAMING),),
        stats=(_stats(),),
    )
    gate = RecordingRestrictedLiveGate(
        _SequenceGateDelegate(
            payload_source=payload_source,
            plans=(
                _gate_result(
                    mutation_applied=True,
                    status_query_count=1,
                    account_snapshot=_account_snapshot(),
                ),
            ),
        )
    )
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )
    run = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=1),
        cycle_id_prefix="account-update-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )
    artifact_paths = RestrictedLiveSoakArtifactWriter(output_dir=tmp_path).persist(
        run=run,
        markdown=RestrictedLiveSoakReportingService().render_markdown(run=run),
    )

    account_rows = [
        json.loads(line)
        for line in artifact_paths.account_update_events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert run.summary.account_update_event_count == 1
    assert run.summary.account_update_full_count == 1
    assert run.summary.account_update_partial_count == 0
    assert account_rows[0]["source_event_type"] == "outboundAccountPosition"
    assert account_rows[0]["updated_assets"] == ["BTC", "USDT"]
    assert account_rows[0]["balance_rows"][0]["asset"] == "BTC"
    assert "account_update_event_count: 1" in artifact_paths.summary_markdown_path.read_text(encoding="utf-8")


def test_default_soak_campaign_builds_6h_12h_24h_sessions() -> None:
    sessions = build_campaign_sessions(campaign_id="campaign-001")

    assert tuple(session.duration_hours for session in sessions) == (6, 12, 24)
    assert tuple(session.session_id for session in sessions) == (
        "campaign-001-6h",
        "campaign-001-12h",
        "campaign-001-24h",
    )


def test_restricted_live_soak_supports_duration_based_stop() -> None:
    clock = _FakeClock()
    payload_source = _SequencePayloadSource(
        healths=(
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
        ),
        stats=(_stats(), _stats(), _stats()),
    )
    gate = RecordingRestrictedLiveGate(
        _SequenceGateDelegate(
            payload_source=payload_source,
            plans=(
                _gate_result(mutation_applied=True, status_query_count=0),
                _gate_result(mutation_applied=True, status_query_count=0),
                _gate_result(mutation_applied=True, status_query_count=0),
            ),
        )
    )
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )

    run = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
        time_provider=clock.now,
        sleep_fn=clock.sleep,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(
            max_cycles=None,
            max_duration=timedelta(hours=6),
            poll_interval_seconds=3 * 60 * 60,
        ),
        cycle_id_prefix="duration-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )

    assert run.summary.aborted is False
    assert run.summary.completed_cycles == 2
    assert run.summary.stop_reason == "completed"


def test_restricted_live_soak_carries_applied_fill_ids_across_cycles() -> None:
    payload_source = _SequencePayloadSource(
        healths=(
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
        ),
        stats=(_stats(), _stats(), _stats()),
    )
    gate_delegate = _SequenceGateDelegate(
        payload_source=payload_source,
        plans=(
            _gate_result_with_fill_ids(mutation_applied=True, applied_fill_ids=("fill-1",)),
            _gate_result_with_fill_ids(mutation_applied=False, applied_fill_ids=()),
            _gate_result_with_fill_ids(mutation_applied=True, applied_fill_ids=("fill-1", "fill-2")),
        ),
    )
    gate = RecordingRestrictedLiveGate(gate_delegate)
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )

    run = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=3),
        cycle_id_prefix="fill-memory-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )

    assert run.summary.completed_cycles == 3
    assert gate_delegate.already_applied_fill_id_calls == [
        (),
        ("fill-1",),
        ("fill-1",),
    ]


def test_restricted_live_soak_carries_ignored_fill_ids_across_cycles() -> None:
    payload_source = _SequencePayloadSource(
        healths=(
            _private_health(BinancePrivateStreamState.STREAMING),
            _private_health(BinancePrivateStreamState.STREAMING),
        ),
        stats=(_stats(), _stats()),
    )
    gate_delegate = _SequenceGateDelegate(
        payload_source=payload_source,
        plans=(
            _gate_result_with_fill_memory(
                mutation_applied=True,
                applied_fill_ids=("private-fill-1",),
                ignored_fill_ids=("18350704:recovered:18350704",),
            ),
            _gate_result_with_fill_memory(
                mutation_applied=True,
                applied_fill_ids=(),
                ignored_fill_ids=(),
            ),
        ),
    )
    gate = RecordingRestrictedLiveGate(gate_delegate)
    provider = RestrictedLiveSoakExchangeHealthProvider(
        health_service=BinanceExchangeHealthService(),
        payload_source=payload_source,
        recording_gate=gate,
    )

    run = RestrictedLiveSoakRunner(
        runner=RestrictedLiveRunner(_context(gate=gate, provider=provider)),
        recording_gate=gate,
        exchange_health_provider=provider,
        payload_source=payload_source,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(max_cycles=2),
        cycle_id_prefix="ignored-fill-memory-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )

    assert run.summary.completed_cycles == 2
    assert gate_delegate.already_applied_fill_id_calls == [
        (),
        ("private-fill-1", "18350704:recovered:18350704"),
    ]


def test_restricted_live_soak_stops_after_cycle_that_overruns_duration() -> None:
    clock = _FakeClock()
    runner = _BlockingCycleRunner(clock=clock)

    run = RestrictedLiveSoakRunner(
        runner=runner,
        recording_gate=SimpleNamespace(last_result=None),
        exchange_health_provider=SimpleNamespace(current_health=lambda: None),
        payload_source=SimpleNamespace(stats_snapshot=lambda: _stats()),
        time_provider=clock.now,
        sleep_fn=clock.sleep,
    ).run(
        criteria=RestrictedLiveSoakStopCriteria(
            max_cycles=20,
            max_duration=timedelta(hours=1),
            poll_interval_seconds=30,
        ),
        cycle_id_prefix="blocking-duration-soak",
        instrument=_instrument(),
        bar_slice=_bar_slice(),
        context_bar_slice=None,
        portfolio_state=_portfolio(),
    )

    assert run.summary.aborted is False
    assert run.summary.completed_cycles == 1
    assert run.summary.stop_reason == "completed"


@dataclass
class _SequencePayloadSource:
    healths: tuple[BinancePrivateStreamHealth, ...]
    stats: tuple[object, ...]

    def __post_init__(self) -> None:
        self._index = 0

    def current_health(self):
        return self.healths[min(self._index, len(self.healths) - 1)]

    def stats_snapshot(self):
        return self.stats[min(self._index, len(self.stats) - 1)]

    def advance(self) -> None:
        self._index += 1


@dataclass
class _SequenceGateDelegate:
    payload_source: _SequencePayloadSource
    plans: tuple[BinanceRestrictedLiveGateResult, ...]

    def __post_init__(self) -> None:
        self._index = 0
        self.already_applied_fill_id_calls: list[tuple[str, ...]] = []

    def apply_with_details(self, *, portfolio_state, expected_order_ids=(), already_applied_fill_ids=()):
        self.already_applied_fill_id_calls.append(tuple(already_applied_fill_ids))
        result = self.plans[min(self._index, len(self.plans) - 1)]
        self._index += 1
        self.payload_source.advance()
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
                rationale="restricted-live soak",
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
                reasons=("allow",),
                approved_quantity=signal.target_quantity,
            )
            for signal in signals
        )


class _PersistenceGateway:
    def __init__(self) -> None:
        self.cycles = []

    def persist_cycle(self, cycle_result, *, features, context, exchange_health=None) -> None:
        self.cycles.append((cycle_result, exchange_health))


def _context(*, gate, provider) -> RuntimeContext:
    return RuntimeContext(
        mode=RunnerMode.RESTRICTED_LIVE,
        feature_builder=_FeatureBuilder(),
        strategy_evaluator=_StrategyEvaluator(),
        risk_evaluator=_RiskEvaluator(),
        execution_intent_builder=ReportOnlyExecutionIntentBuilder(),
        persistence_gateway=_PersistenceGateway(),
        venue_profile=_venue_profile(),
        execution_venue="binance",
        live_portfolio_mutation_gate=gate,
        exchange_health_provider=provider,
    )


def _gate_result(
    *,
    mutation_applied: bool,
    status_query_count: int,
    account_snapshot: AccountSnapshot | None = None,
) -> BinanceRestrictedLiveGateResult:
    outcome = LivePortfolioMutationOutcome(
        mutation_attempted=True,
        mutation_applied=mutation_applied,
        portfolio_state=_portfolio(),
        translation_result=LivePortfolioTranslationResult(
            status=LiveTranslationStatus.APPLIED if mutation_applied else LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
            portfolio_state=_portfolio(),
            applied_fill_ids=("fill-1",) if mutation_applied else (),
            ignored_fill_ids=(),
            pending_order_ids=(),
            alerts=(() if mutation_applied else ("blocked by soak test",)),
            aggregations=(),
            requires_manual_attention=not mutation_applied,
        ),
        reconciliation_events=(
            ReconciliationEvent(
                    venue="binance",
                    order_id="order-1",
                    reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING if not mutation_applied else ReconciliationState.RECOVERED_TERMINAL_STATE,
                    detail="soak test reconciliation",
                occurred_at=_dt(0, 2),
            ),
        ),
        alerts=(() if mutation_applied else ("restricted-live portfolio mutation blocked by mandatory safeguard gate",)),
    )
    status_query_health = tuple(
        BinanceStatusQueryHealth(
            lookup_field="exchange_order_id",
            lookup_value=f"order-{index}",
            state=BinanceStatusQueryState.SUCCESS if mutation_applied else BinanceStatusQueryState.FAILED,
            checked_at=_dt(0, 2),
            transport="signed_rest_order_lookup",
        )
        for index in range(status_query_count)
    )
    transport_result = SimpleNamespace(
        workflow_result=SimpleNamespace(
            reconciliation_events=outcome.reconciliation_events,
            alerts=outcome.alerts,
            recovery_trigger_reason=None,
            recovery_automatic=False,
            gap_detected=not mutation_applied,
            resumed_from_snapshot=False,
            convergence_state=("converged_terminal" if mutation_applied else "pending"),
        ),
        status_query_health=status_query_health,
        cursor_snapshot=SimpleNamespace(
            unresolved_order_ids=(() if mutation_applied else ("order-1",)),
            manual_attention_order_ids=(),
            gap_active=not mutation_applied,
        ),
        translations=(
            ()
            if account_snapshot is None
            else (SimpleNamespace(account_snapshot=account_snapshot),)
        ),
    )
    return BinanceRestrictedLiveGateResult(
        mutation_outcome=outcome,
        transport_result=transport_result,
    )


def _gate_result_with_fill_ids(
    *,
    mutation_applied: bool,
    applied_fill_ids: tuple[str, ...],
) -> BinanceRestrictedLiveGateResult:
    return _gate_result_with_fill_memory(
        mutation_applied=mutation_applied,
        applied_fill_ids=applied_fill_ids,
        ignored_fill_ids=(),
    )


def _gate_result_with_fill_memory(
    *,
    mutation_applied: bool,
    applied_fill_ids: tuple[str, ...],
    ignored_fill_ids: tuple[str, ...],
) -> BinanceRestrictedLiveGateResult:
    outcome = LivePortfolioMutationOutcome(
        mutation_attempted=True,
        mutation_applied=mutation_applied,
        portfolio_state=_portfolio(),
        translation_result=LivePortfolioTranslationResult(
            status=LiveTranslationStatus.APPLIED if mutation_applied else LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
            portfolio_state=_portfolio(),
            applied_fill_ids=applied_fill_ids,
            ignored_fill_ids=ignored_fill_ids,
            pending_order_ids=(),
            alerts=(() if mutation_applied else ("blocked by soak test",)),
            aggregations=(),
            requires_manual_attention=not mutation_applied,
        ),
        reconciliation_events=(),
        alerts=(() if mutation_applied else ("restricted-live portfolio mutation blocked by mandatory safeguard gate",)),
    )
    transport_result = SimpleNamespace(
        workflow_result=SimpleNamespace(
            reconciliation_events=(),
            alerts=outcome.alerts,
            recovery_trigger_reason=None,
            recovery_automatic=False,
            gap_detected=not mutation_applied,
            resumed_from_snapshot=False,
            convergence_state="not_required",
        ),
        status_query_health=(),
        cursor_snapshot=SimpleNamespace(
            unresolved_order_ids=(),
            manual_attention_order_ids=(),
            gap_active=not mutation_applied,
        ),
        translations=(),
    )
    return BinanceRestrictedLiveGateResult(
        mutation_outcome=outcome,
        transport_result=transport_result,
    )


def _account_snapshot() -> AccountSnapshot:
    return AccountSnapshot(
        venue="binance",
        account_scope="spot",
        as_of=_dt(0, 2),
        balances=(
            AssetBalanceSnapshot(
                asset="BTC",
                free=Decimal("0.010"),
                locked=Decimal("0"),
                delta=Decimal("0.010"),
                updated_at=_dt(0, 2),
            ),
            AssetBalanceSnapshot(
                asset="USDT",
                free=Decimal("900"),
                locked=Decimal("0"),
                delta=Decimal("-100"),
                updated_at=_dt(0, 2),
            ),
        ),
        source_event_type="outboundAccountPosition",
        translation_version="binance_private_v1",
        is_partial=False,
        alerts=(),
    )


def _stats(
    *,
    reconnect_count: int = 0,
    refresh_attempts: int = 0,
    refresh_failures: int = 0,
    heartbeat_overdue_events: int = 0,
    last_refresh_result: str | None = None,
):
    return SimpleNamespace(
        reconnect_count=reconnect_count,
        refresh_attempts=refresh_attempts,
        refresh_failures=refresh_failures,
        heartbeat_overdue_events=heartbeat_overdue_events,
        last_refresh_result=last_refresh_result,
        last_transport_error=None,
    )


@dataclass
class _FakeClock:
    current: datetime = datetime(2026, 3, 13, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


@dataclass
class _BlockingCycleRunner:
    clock: _FakeClock

    def __post_init__(self) -> None:
        self._cycle_index = 0

    def run_cycle(
        self,
        *,
        cycle_id: str,
        instrument,
        bar_slice,
        portfolio_state,
        context_bar_slice=None,
        already_applied_fill_ids=(),
    ):
        self._cycle_index += 1
        started_at = self.clock.now()
        self.clock.current = self.clock.current + timedelta(minutes=61)
        completed_at = self.clock.now()
        return SimpleNamespace(
            cycle_id=cycle_id,
            completed_at=completed_at,
            success=True,
            alerts=("blocking cycle completed",),
        )


def _private_health(state: BinancePrivateStreamState) -> BinancePrivateStreamHealth:
    return BinancePrivateStreamHealth(
        state=state,
        reconnect_attempts=0,
        last_message_at=_dt(0, 1),
        session_expires_at=_dt(1, 0),
        is_authoritative=state is BinancePrivateStreamState.STREAMING,
        alerts=(state.value,),
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


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 13, hour, minute, tzinfo=UTC)
