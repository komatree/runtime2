"""Replay harness for backtest-live parity diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from app.contracts import BarSlice
from app.contracts import DecisionContext
from app.contracts import IndexSnapshot
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RuntimeCycleResult
from app.contracts import StablecoinSnapshot
from app.storage import JsonlParityComparisonGateway
from app.storage import ParityComparisonRecord

from .paper_runner import PaperCycleOutcome
from .paper_runner import PaperRunner
from .report_only_runner import ReportOnlyRunner
from .runtime_context import RuntimeContext


@dataclass(frozen=True)
class ReplayCycleInput:
    """Closed-bar replay input for one runtime cycle."""

    cycle_id: str
    instrument: Instrument
    execution_bar_slice: BarSlice
    portfolio_state: PortfolioState
    context_bar_slice: BarSlice | None = None
    index_snapshot: IndexSnapshot | None = None
    stablecoin_snapshot: StablecoinSnapshot | None = None


@dataclass(frozen=True)
class ReferenceEvaluationResult:
    """Reference backtest-style evaluation output for one replayed cycle."""

    context: DecisionContext
    cycle_result: RuntimeCycleResult


@dataclass(frozen=True)
class ReplayParitySessionResult:
    """Replay session summary including runtime and reference artifacts."""

    report_only_cycles: tuple[RuntimeCycleResult, ...]
    paper_cycles: tuple[PaperCycleOutcome, ...]
    reference_cycles: tuple[ReferenceEvaluationResult, ...]
    parity_records: tuple[ParityComparisonRecord, ...]


@dataclass(frozen=True)
class _StaticIndexProvider:
    snapshot: IndexSnapshot | None

    def get_snapshot(self, *, instrument_id: str, as_of) -> IndexSnapshot | None:
        return self.snapshot


@dataclass(frozen=True)
class _StaticStablecoinProvider:
    snapshot: StablecoinSnapshot | None

    def get_snapshot(self, *, as_of) -> StablecoinSnapshot | None:
        return self.snapshot


@dataclass(frozen=True)
class ReferenceBacktestEvaluator:
    """Reference path that evaluates the same inputs outside runner orchestration."""

    context: RuntimeContext

    def evaluate(
        self,
        replay_input: ReplayCycleInput,
        *,
        portfolio_state: PortfolioState | None = None,
        execution_venue: str | None = None,
    ) -> ReferenceEvaluationResult:
        """Evaluate one cycle as a backtest-style deterministic reference."""

        bound_context = _bind_replay_context(self.context, replay_input)
        effective_portfolio_state = portfolio_state or replay_input.portfolio_state
        runner = ReportOnlyRunner(bound_context)
        features = bound_context.feature_builder.build(
            replay_input.execution_bar_slice,
            context_bar_slice=replay_input.context_bar_slice,
        )
        decision_context = runner._build_context(
            cycle_id=replay_input.cycle_id,
            instrument=replay_input.instrument,
            bar_slice=replay_input.execution_bar_slice,
            portfolio_state=effective_portfolio_state,
            features=features,
        )
        signals = bound_context.strategy_evaluator.evaluate(decision_context)
        risk_decisions = bound_context.risk_evaluator.evaluate(
            signals,
            effective_portfolio_state,
            bound_context.venue_profile,
        )
        execution_intents = bound_context.execution_intent_builder.build(
            risk_decisions=risk_decisions,
            venue=execution_venue or bound_context.execution_venue or "unassigned_venue",
            submitted_at=replay_input.execution_bar_slice.end_time,
        )
        cycle_result = RuntimeCycleResult(
            cycle_id=replay_input.cycle_id,
            started_at=replay_input.execution_bar_slice.end_time,
            completed_at=replay_input.execution_bar_slice.end_time,
            processed_instruments=(replay_input.instrument.instrument_id,),
            signals=signals,
            risk_decisions=risk_decisions,
            execution_intents=execution_intents,
            alerts=("reference backtest-style evaluation",),
            success=True,
        )
        return ReferenceEvaluationResult(context=decision_context, cycle_result=cycle_result)


@dataclass(frozen=True)
class RuntimeReplayHarness:
    """Replays historical bars through runtime2 and records parity drift."""

    report_only_context: RuntimeContext
    paper_context: RuntimeContext
    reference_evaluator: ReferenceBacktestEvaluator
    parity_gateway: JsonlParityComparisonGateway | None = None

    def replay(self, cycle_inputs: tuple[ReplayCycleInput, ...]) -> ReplayParitySessionResult:
        """Replay closed bars cycle-by-cycle for report-only and paper parity checks."""

        report_cycles: list[RuntimeCycleResult] = []
        paper_cycles: list[PaperCycleOutcome] = []
        reference_cycles: list[ReferenceEvaluationResult] = []
        parity_records: list[ParityComparisonRecord] = []
        current_paper_portfolio: PortfolioState | None = None

        for replay_input in cycle_inputs:
            bound_report_context = _bind_replay_context(self.report_only_context, replay_input)
            bound_paper_context = _bind_replay_context(self.paper_context, replay_input)

            report_cycle = ReportOnlyRunner(bound_report_context).run_cycle(
                cycle_id=replay_input.cycle_id,
                instrument=replay_input.instrument,
                bar_slice=replay_input.execution_bar_slice,
                portfolio_state=replay_input.portfolio_state,
                context_bar_slice=replay_input.context_bar_slice,
            )
            paper_cycle = PaperRunner(bound_paper_context).run_cycle(
                cycle_id=replay_input.cycle_id,
                instrument=replay_input.instrument,
                bar_slice=replay_input.execution_bar_slice,
                portfolio_state=current_paper_portfolio or replay_input.portfolio_state,
                context_bar_slice=replay_input.context_bar_slice,
            )
            report_reference_cycle = self.reference_evaluator.evaluate(
                replay_input,
                portfolio_state=replay_input.portfolio_state,
                execution_venue=bound_report_context.execution_venue,
            )
            paper_reference_cycle = self.reference_evaluator.evaluate(
                replay_input,
                portfolio_state=current_paper_portfolio or replay_input.portfolio_state,
                execution_venue=bound_paper_context.execution_venue,
            )

            report_record = self._build_parity_record(
                runtime_mode="report_only",
                runtime_cycle=report_cycle,
                reference_cycle=report_reference_cycle.cycle_result,
                context=report_reference_cycle.context,
            )
            paper_record = self._build_parity_record(
                runtime_mode="paper",
                runtime_cycle=paper_cycle.cycle_result,
                reference_cycle=paper_reference_cycle.cycle_result,
                context=paper_reference_cycle.context,
            )
            if self.parity_gateway is not None:
                self.parity_gateway.persist_record(report_record)
                self.parity_gateway.persist_record(paper_record)

            report_cycles.append(report_cycle)
            paper_cycles.append(paper_cycle)
            reference_cycles.append(report_reference_cycle)
            parity_records.extend((report_record, paper_record))
            current_paper_portfolio = paper_cycle.ending_portfolio_state

        return ReplayParitySessionResult(
            report_only_cycles=tuple(report_cycles),
            paper_cycles=tuple(paper_cycles),
            reference_cycles=tuple(reference_cycles),
            parity_records=tuple(parity_records),
        )

    def _build_parity_record(
        self,
        *,
        runtime_mode: str,
        runtime_cycle: RuntimeCycleResult,
        reference_cycle: RuntimeCycleResult,
        context: DecisionContext,
    ) -> ParityComparisonRecord:
        runtime_output = _cycle_summary(runtime_cycle)
        reference_output = _cycle_summary(reference_cycle)
        mismatches = tuple(
            key
            for key in ("signal_sides", "actionable", "risk_posture", "execution_intent_shape")
            if runtime_output[key] != reference_output[key]
        )
        return ParityComparisonRecord(
            schema_version="parity_cycle.v1",
            recorded_at=context.latest_candle.close_time,
            runtime_mode=runtime_mode,
            cycle_id=runtime_cycle.cycle_id,
            instrument_id=context.instrument.instrument_id,
            timeframe=context.features.timeframe,
            bar_close_time=context.latest_candle.close_time,
            matches=not mismatches,
            mismatches=mismatches,
            key_context={
                "instrument_id": context.instrument.instrument_id,
                "timeframe": context.features.timeframe,
                "bar_close_time": context.latest_candle.close_time.isoformat(),
                "has_index_snapshot": context.index_snapshot is not None,
                "has_stablecoin_snapshot": context.stablecoin_snapshot is not None,
            },
            runtime_output=runtime_output,
            reference_output=reference_output,
        )


def _bind_replay_context(base_context: RuntimeContext, replay_input: ReplayCycleInput) -> RuntimeContext:
    feature_builder = base_context.feature_builder
    if hasattr(feature_builder, "index_snapshot_provider") and hasattr(feature_builder, "stablecoin_snapshot_provider"):
        feature_builder = replace(
            feature_builder,
            index_snapshot_provider=_StaticIndexProvider(replay_input.index_snapshot),
            stablecoin_snapshot_provider=_StaticStablecoinProvider(replay_input.stablecoin_snapshot),
        )
    return replace(
        base_context,
        feature_builder=feature_builder,
        index_snapshot_provider=_StaticIndexProvider(replay_input.index_snapshot),
        stablecoin_snapshot_provider=_StaticStablecoinProvider(replay_input.stablecoin_snapshot),
    )


def _cycle_summary(cycle_result: RuntimeCycleResult) -> dict[str, object]:
    return {
        "signal_sides": tuple(signal.side.value for signal in cycle_result.signals),
        "actionable": bool(cycle_result.execution_intents),
        "risk_posture": tuple(decision.status.value for decision in cycle_result.risk_decisions),
        "execution_intent_shape": tuple(
            {
                "venue": intent.venue,
                "side": intent.side.value,
                "order_type": intent.order_type.value,
                "time_in_force": intent.time_in_force.value,
                "quantity": str(intent.quantity),
            }
            for intent in cycle_result.execution_intents
        ),
    }
