"""Report-only runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from app.contracts import BarSlice
from app.contracts import DataQualityState
from app.contracts import DecisionContext
from app.contracts import ExecutionIntent
from app.contracts import Instrument
from app.contracts import PortfolioState
from app.contracts import RuntimeCycleResult
from app.exchanges.binance import BinanceMarketDataClient
from app.monitoring import current_or_unknown_exchange_health

from .bar_close_validator import BarCloseValidator
from .data_quality import RuntimeDataQualityGate
from .runtime_context import RuntimeContext
from .runtime_context import RunnerMode
from .state_machine import RuntimeStage
from .state_machine import RuntimeStateMachine


def _exchange_health(context: RuntimeContext):
    venue = context.execution_venue or (context.venue_profile.venue if context.venue_profile is not None else None)
    return current_or_unknown_exchange_health(
        venue=venue,
        provider=context.exchange_health_provider,
    )


@dataclass(frozen=True)
class ReportOnlyRunner:
    """Executes the first complete vertical slice without exchange side effects."""

    context: RuntimeContext
    bar_close_validator: BarCloseValidator = BarCloseValidator()
    data_quality_gate: RuntimeDataQualityGate = RuntimeDataQualityGate()

    def __post_init__(self) -> None:
        if self.context.mode is not RunnerMode.REPORT_ONLY:
            raise ValueError("ReportOnlyRunner requires report_only mode")

    def run_cycle(
        self,
        *,
        cycle_id: str,
        instrument: Instrument,
        bar_slice: BarSlice,
        portfolio_state: PortfolioState,
        context_bar_slice: BarSlice | None = None,
    ) -> RuntimeCycleResult:
        """Run the report-only decision pipeline for one closed-bar trigger."""

        state_machine = RuntimeStateMachine()
        started_at = datetime.now(UTC)
        alerts: list[str] = []

        validation = self.bar_close_validator.validate(bar_slice)
        if not validation.is_valid:
            state_machine.fail(RuntimeStage.BAR_CLOSE_TRIGGER)
            features = self.context.feature_builder.build(bar_slice, context_bar_slice=context_bar_slice)
            decision_context = self._build_context(
                cycle_id=cycle_id,
                instrument=instrument,
                bar_slice=bar_slice,
                portfolio_state=portfolio_state,
                features=features,
            )
            completed_at = datetime.now(UTC)
            cycle_result = RuntimeCycleResult(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=completed_at,
                processed_instruments=(instrument.instrument_id,),
                signals=(),
                risk_decisions=(),
                execution_intents=(),
                quality_states=(DataQualityState.INCOMPLETE_BAR,),
                quality_details=validation.reasons,
                alerts=validation.reasons,
                success=False,
            )
            self.context.persistence_gateway.persist_cycle(
                cycle_result,
                features=features,
                context=decision_context,
                exchange_health=_exchange_health(self.context),
            )
            return cycle_result

        state_machine.advance(RuntimeStage.NORMALIZED_SLICE)
        features = self.context.feature_builder.build(bar_slice, context_bar_slice=context_bar_slice)
        state_machine.advance(RuntimeStage.FEATURE_SNAPSHOT)

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
        state_machine.advance(RuntimeStage.STRATEGY_EVALUATION)

        risk_decisions = self.context.risk_evaluator.evaluate(
            signals,
            portfolio_state,
            self.context.venue_profile,
        )
        state_machine.advance(RuntimeStage.RISK_EVALUATION)

        execution_intents: tuple[ExecutionIntent, ...] = self.context.execution_intent_builder.build(
            risk_decisions=risk_decisions,
            venue=self.context.execution_venue or "unassigned_venue",
            submitted_at=bar_slice.end_time,
        )
        state_machine.advance(RuntimeStage.EXECUTION_INTENT)
        if execution_intents:
            alerts.append("report-only generated intents were persisted only; no exchange submission")
        else:
            alerts.append("report-only cycle produced no executable intents")
        alerts.extend(quality_evaluation.details)

        state_machine.advance(RuntimeStage.PERSISTENCE_REPORTING)
        completed_at = datetime.now(UTC)
        cycle_result = RuntimeCycleResult(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            processed_instruments=(instrument.instrument_id,),
            signals=signals,
            risk_decisions=risk_decisions,
            execution_intents=execution_intents,
            quality_states=quality_evaluation.states,
            quality_details=quality_evaluation.details,
            alerts=tuple(alerts),
            success=True,
        )
        self.context.persistence_gateway.persist_cycle(
            cycle_result,
            features=features,
            context=decision_context,
            exchange_health=_exchange_health(self.context),
        )
        state_machine.advance(RuntimeStage.EXCHANGE_RECONCILIATION)
        return cycle_result

    def run_real_data_cycle(
        self,
        *,
        cycle_id: str,
        instrument: Instrument,
        portfolio_state: PortfolioState,
        market_data_client: BinanceMarketDataClient,
        execution_klines,
        context_klines,
        reference_time: datetime | None = None,
        execution_timeframe: str = "4h",
        context_timeframe: str = "1d",
    ) -> RuntimeCycleResult:
        """Run the report-only path from real Binance kline schema inputs."""

        market_context = market_data_client.build_report_only_market_context(
            instrument_id=instrument.instrument_id,
            execution_timeframe=execution_timeframe,
            context_timeframe=context_timeframe,
            execution_klines=execution_klines,
            context_klines=context_klines,
            reference_time=reference_time,
        )
        return self.run_cycle(
            cycle_id=cycle_id,
            instrument=instrument,
            bar_slice=market_context.execution_bar_slice,
            context_bar_slice=market_context.context_bar_slice,
            portfolio_state=portfolio_state,
        )

    def _build_context(
        self,
        *,
        cycle_id: str,
        instrument: Instrument,
        bar_slice: BarSlice,
        portfolio_state: PortfolioState,
        features=None,
    ) -> DecisionContext:
        feature_snapshot = features if features is not None else self.context.feature_builder.build(bar_slice)
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
            features=feature_snapshot,
            portfolio_state=portfolio_state,
            index_snapshot=index_snapshot,
            stablecoin_snapshot=stablecoin_snapshot,
            index_snapshot_status=index_snapshot_status,
            index_snapshot_detail=index_snapshot_detail,
            index_snapshot_requested_version=index_snapshot_requested_version,
            stablecoin_snapshot_status=stablecoin_snapshot_status,
            stablecoin_snapshot_detail=stablecoin_snapshot_detail,
        )
