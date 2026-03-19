"""Paper-mode runtime runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from app.contracts import BarSlice
from app.contracts import DataQualityState
from app.contracts import DecisionContext
from app.contracts import FillEvent
from app.contracts import Instrument
from app.contracts import OrderState
from app.contracts import PositionState
from app.contracts import PortfolioState
from app.contracts import RuntimeCycleResult
from app.execution import PaperExecutionSimulator
from app.monitoring import current_or_unknown_exchange_health
from app.portfolio import PaperPortfolioUpdater
from app.storage import JsonlPaperStatePersistenceGateway

from .bar_close_validator import BarCloseValidator
from .data_quality import RuntimeDataQualityGate
from .runtime_context import RuntimeContext
from .runtime_context import RunnerMode


def _exchange_health(context: RuntimeContext):
    venue = context.execution_venue or (context.venue_profile.venue if context.venue_profile is not None else None)
    return current_or_unknown_exchange_health(
        venue=venue,
        provider=context.exchange_health_provider,
    )


@dataclass(frozen=True)
class PaperCycleOutcome:
    """Paper-mode cycle output including simulated state transitions."""

    cycle_result: RuntimeCycleResult
    starting_portfolio_state: PortfolioState
    ending_portfolio_state: PortfolioState
    ending_position_states: tuple[PositionState, ...]
    order_states: tuple[OrderState, ...]
    fill_events: tuple[FillEvent, ...]


@dataclass(frozen=True)
class PaperSessionResult:
    """Summary of a sequential paper-mode session."""

    session_id: str
    cycle_outcomes: tuple[PaperCycleOutcome, ...]
    final_portfolio_state: PortfolioState
    final_position_states: tuple[PositionState, ...]


@dataclass(frozen=True)
class PaperRunner:
    """Simulates order lifecycle and portfolio transitions without real exchanges."""

    context: RuntimeContext
    bar_close_validator: BarCloseValidator = BarCloseValidator()
    execution_simulator: PaperExecutionSimulator = PaperExecutionSimulator()
    portfolio_updater: PaperPortfolioUpdater = PaperPortfolioUpdater()
    state_persistence_gateway: JsonlPaperStatePersistenceGateway | None = None
    data_quality_gate: RuntimeDataQualityGate = RuntimeDataQualityGate()

    def __post_init__(self) -> None:
        if self.context.mode is not RunnerMode.PAPER:
            raise ValueError("PaperRunner requires paper mode")
        if not self.context.execution_venue:
            raise ValueError("PaperRunner requires execution_venue")

    def run_cycle(
        self,
        *,
        cycle_id: str,
        instrument: Instrument,
        bar_slice: BarSlice,
        portfolio_state: PortfolioState,
        context_bar_slice: BarSlice | None = None,
    ) -> PaperCycleOutcome:
        """Run paper-mode analysis, simulate fills, and return updated state."""

        validation = self.bar_close_validator.validate(bar_slice)
        started_at = datetime.now(UTC)
        if not validation.is_valid:
            cycle_result = RuntimeCycleResult(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                processed_instruments=(instrument.instrument_id,),
                signals=(),
                risk_decisions=(),
                execution_intents=(),
                quality_states=(DataQualityState.INCOMPLETE_BAR,),
                quality_details=validation.reasons,
                alerts=validation.reasons,
                success=False,
            )
            return PaperCycleOutcome(
                cycle_result=cycle_result,
                starting_portfolio_state=portfolio_state,
                ending_portfolio_state=portfolio_state,
                ending_position_states=self.portfolio_updater.derive_position_states(
                    portfolio_state=portfolio_state,
                ),
                order_states=(),
                fill_events=(),
            )

        features = self.context.feature_builder.build(bar_slice, context_bar_slice=context_bar_slice)
        decision_context = self._build_context(
            cycle_id=cycle_id,
            instrument=instrument,
            bar_slice=bar_slice,
            portfolio_state=portfolio_state,
            features=features,
        )
        quality_evaluation = self.data_quality_gate.evaluate(
            mode=self.context.mode,
            runtime_context=self.context,
            decision_context=decision_context,
            context_bar_slice=context_bar_slice,
        )
        if quality_evaluation.states:
            decision_context = DecisionContext(
                cycle_id=decision_context.cycle_id,
                as_of=decision_context.as_of,
                instrument=decision_context.instrument,
                latest_candle=decision_context.latest_candle,
                bar_slice=decision_context.bar_slice,
                features=decision_context.features,
                portfolio_state=decision_context.portfolio_state,
                index_snapshot=decision_context.index_snapshot,
                stablecoin_snapshot=decision_context.stablecoin_snapshot,
                index_snapshot_status=decision_context.index_snapshot_status,
                index_snapshot_detail=decision_context.index_snapshot_detail,
                index_snapshot_requested_version=decision_context.index_snapshot_requested_version,
                stablecoin_snapshot_status=decision_context.stablecoin_snapshot_status,
                stablecoin_snapshot_detail=decision_context.stablecoin_snapshot_detail,
                quality_states=quality_evaluation.states,
                quality_details=quality_evaluation.details,
            )
        signals = self.context.strategy_evaluator.evaluate(decision_context)
        risk_decisions = self.context.risk_evaluator.evaluate(
            signals,
            portfolio_state,
            self.context.venue_profile,
        )
        execution_intents = self.context.execution_intent_builder.build(
            risk_decisions=risk_decisions,
            venue=self.context.execution_venue or "paper",
            submitted_at=bar_slice.end_time,
        )
        order_states, fill_events = self.execution_simulator.simulate(
            intents=execution_intents,
            fill_price=bar_slice.candles[-1].close,
            occurred_at=bar_slice.end_time,
        )
        ending_portfolio_state = self.portfolio_updater.apply_fills(
            portfolio_state=portfolio_state,
            fill_events=fill_events,
        )
        ending_position_states = self.portfolio_updater.derive_position_states(
            portfolio_state=ending_portfolio_state,
            mark_prices_by_instrument={instrument.instrument_id: bar_slice.candles[-1].close},
        )
        cycle_result = RuntimeCycleResult(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            processed_instruments=(instrument.instrument_id,),
            signals=signals,
            risk_decisions=risk_decisions,
            execution_intents=execution_intents,
            alerts=(
                "paper mode simulated order acceptance and fill only",
                "paper portfolio state transition persisted",
                *quality_evaluation.details,
            ),
            quality_states=quality_evaluation.states,
            quality_details=quality_evaluation.details,
            success=True,
        )
        self.context.persistence_gateway.persist_cycle(
            cycle_result,
            features=features,
            context=decision_context,
            exchange_health=_exchange_health(self.context),
        )
        if self.state_persistence_gateway is not None:
            self.state_persistence_gateway.persist_transition(
                cycle_id=cycle_id,
                starting_portfolio_state=portfolio_state,
                ending_portfolio_state=ending_portfolio_state,
                order_states=order_states,
                fill_events=fill_events,
            )
        return PaperCycleOutcome(
            cycle_result=cycle_result,
            starting_portfolio_state=portfolio_state,
            ending_portfolio_state=ending_portfolio_state,
            ending_position_states=ending_position_states,
            order_states=order_states,
            fill_events=fill_events,
        )

    def run_cycles(
        self,
        *,
        session_id: str,
        instrument: Instrument,
        cycle_inputs: tuple[tuple[str, BarSlice], ...],
        initial_portfolio_state: PortfolioState,
    ) -> PaperSessionResult:
        """Run sequential bars while preserving paper portfolio continuity internally."""

        portfolio_state = initial_portfolio_state
        outcomes: list[PaperCycleOutcome] = []
        for cycle_id, bar_slice in cycle_inputs:
            outcome = self.run_cycle(
                cycle_id=cycle_id,
                instrument=instrument,
                bar_slice=bar_slice,
                portfolio_state=portfolio_state,
            )
            outcomes.append(outcome)
            portfolio_state = outcome.ending_portfolio_state

        final_position_states = (
            outcomes[-1].ending_position_states
            if outcomes
            else self.portfolio_updater.derive_position_states(portfolio_state=portfolio_state)
        )
        if self.state_persistence_gateway is not None:
            self.state_persistence_gateway.persist_session_summary(
                session_id=session_id,
                cycle_ids=tuple(cycle_id for cycle_id, _ in cycle_inputs),
                final_portfolio_state=portfolio_state,
                final_position_states=final_position_states,
                total_cycles=len(outcomes),
                action_cycle_count=sum(1 for outcome in outcomes if outcome.order_states),
            )
        return PaperSessionResult(
            session_id=session_id,
            cycle_outcomes=tuple(outcomes),
            final_portfolio_state=portfolio_state,
            final_position_states=final_position_states,
        )

    def _build_context(self, *, cycle_id, instrument, bar_slice, portfolio_state, features) -> DecisionContext:
        index_snapshot = None
        index_snapshot_status = None
        index_snapshot_detail = None
        index_snapshot_requested_version = None
        if self.context.index_snapshot_provider is not None:
            if hasattr(self.context.index_snapshot_provider, "resolve_snapshot"):
                lookup_result = self.context.index_snapshot_provider.resolve_snapshot(
                    instrument_id=instrument.instrument_id,
                    as_of=bar_slice.end_time,
                )
                index_snapshot_status = lookup_result.status.value
                index_snapshot_detail = lookup_result.detail
                index_snapshot_requested_version = lookup_result.requested_index_version
                index_snapshot = lookup_result.snapshot if lookup_result.status.value == "ok" else None
            else:
                index_snapshot = self.context.index_snapshot_provider.get_snapshot(
                    instrument_id=instrument.instrument_id,
                    as_of=bar_slice.end_time,
                )
        stablecoin_snapshot = None
        stablecoin_snapshot_status = None
        stablecoin_snapshot_detail = None
        if self.context.stablecoin_snapshot_provider is not None:
            if hasattr(self.context.stablecoin_snapshot_provider, "resolve_snapshot"):
                stablecoin_lookup = self.context.stablecoin_snapshot_provider.resolve_snapshot(as_of=bar_slice.end_time)
                stablecoin_snapshot_status = stablecoin_lookup.status.value
                stablecoin_snapshot_detail = stablecoin_lookup.detail
                stablecoin_snapshot = stablecoin_lookup.snapshot if stablecoin_lookup.status.value == "ok" else None
            else:
                stablecoin_snapshot = self.context.stablecoin_snapshot_provider.get_snapshot(as_of=bar_slice.end_time)
        return DecisionContext(
            cycle_id=cycle_id,
            as_of=bar_slice.end_time,
            instrument=instrument,
            latest_candle=bar_slice.candles[-1],
            bar_slice=bar_slice,
            features=features,
            portfolio_state=portfolio_state,
            index_snapshot=index_snapshot,
            stablecoin_snapshot=stablecoin_snapshot,
            index_snapshot_status=index_snapshot_status,
            index_snapshot_detail=index_snapshot_detail,
            index_snapshot_requested_version=index_snapshot_requested_version,
            stablecoin_snapshot_status=stablecoin_snapshot_status,
            stablecoin_snapshot_detail=stablecoin_snapshot_detail,
        )
