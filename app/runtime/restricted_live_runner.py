"""Restricted live-mode runtime runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import BarSlice
from app.contracts import DataQualityState
from app.contracts import ExecutionIntent
from app.contracts import Instrument
from app.contracts import OrderSide
from app.contracts import OrderType
from app.contracts import PortfolioState
from app.contracts import RiskDecisionStatus
from app.contracts import RuntimeCycleResult
from app.contracts import SignalSide
from app.contracts import TimeInForce
from app.monitoring import current_or_unknown_exchange_health

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
class RestrictedLiveRunner:
    """Prepares live-capable intents while deferring actual exchange execution."""

    context: RuntimeContext
    bar_close_validator: BarCloseValidator = BarCloseValidator()
    data_quality_gate: RuntimeDataQualityGate = RuntimeDataQualityGate()

    def __post_init__(self) -> None:
        if self.context.mode is not RunnerMode.RESTRICTED_LIVE:
            raise ValueError("RestrictedLiveRunner requires restricted_live mode")
        if not self.context.execution_venue:
            raise ValueError("RestrictedLiveRunner requires execution_venue")
        if self.context.venue_profile is None:
            raise ValueError("RestrictedLiveRunner requires venue_profile")

    def run_cycle(
        self,
        *,
        cycle_id: str,
        instrument: Instrument,
        bar_slice: BarSlice,
        portfolio_state: PortfolioState,
        context_bar_slice: BarSlice | None = None,
        expected_live_order_ids: tuple[str, ...] = (),
        already_applied_fill_ids: tuple[str, ...] = (),
    ) -> RuntimeCycleResult:
        """Run live-mode preparation without exchange submission or reconciliation."""

        validation = self.bar_close_validator.validate(bar_slice)
        started_at = datetime.now(UTC)
        if not validation.is_valid:
            return RuntimeCycleResult(
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

        from app.contracts import DecisionContext

        features = self.context.feature_builder.build(bar_slice, context_bar_slice=context_bar_slice)
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
        decision_context = DecisionContext(
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
        quality_evaluation = self.data_quality_gate.evaluate(
            mode=self.context.mode,
            runtime_context=self.context,
            decision_context=decision_context,
            context_bar_slice=context_bar_slice,
        )
        if quality_evaluation.should_fail_closed:
            cycle_result = RuntimeCycleResult(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                processed_instruments=(instrument.instrument_id,),
                signals=(),
                risk_decisions=(),
                execution_intents=(),
                quality_states=quality_evaluation.states,
                quality_details=quality_evaluation.details,
                alerts=quality_evaluation.details or ("restricted-live quality gate failed closed",),
                success=False,
            )
            self.context.persistence_gateway.persist_cycle(
                cycle_result,
                features=features,
                context=DecisionContext(
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
                ),
                exchange_health=_exchange_health(self.context),
            )
            return cycle_result
        signals = self.context.strategy_evaluator.evaluate(decision_context)
        risk_decisions = self.context.risk_evaluator.evaluate(
            signals,
            portfolio_state,
            self.context.venue_profile,
        )
        execution_intents = tuple(
            ExecutionIntent(
                intent_id=f"{cycle_id}:{decision.signal.strategy_name}",
                venue=self.context.execution_venue,
                instrument_id=instrument.instrument_id,
                side=OrderSide.BUY if decision.signal.side.value == "buy" else OrderSide.SELL,
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.IOC,
                quantity=decision.approved_quantity
                or decision.approved_notional
                or decision.signal.target_quantity
                or decision.signal.target_notional
                or Decimal("1"),
                submitted_at=bar_slice.end_time,
                source_strategy=decision.signal.strategy_name,
                rationale="restricted-live prepared intent pending future exchange execution",
            )
            for decision in risk_decisions
            if decision.status in {RiskDecisionStatus.ALLOW, RiskDecisionStatus.ADJUST}
            and decision.signal.side is not SignalSide.FLAT
        )
        reconciliation_events = ()
        alerts = [
            "restricted-live mode prepared intents only",
            "exchange execution remains future work",
            *quality_evaluation.details,
        ]
        success = True
        if self.context.live_portfolio_mutation_gate is not None:
            mutation_outcome = self.context.live_portfolio_mutation_gate.apply(
                portfolio_state=portfolio_state,
                expected_order_ids=expected_live_order_ids,
                already_applied_fill_ids=already_applied_fill_ids,
            )
            reconciliation_events = mutation_outcome.reconciliation_events
            alerts.extend(mutation_outcome.alerts)
            if mutation_outcome.mutation_attempted:
                if mutation_outcome.mutation_applied:
                    alerts.append("restricted-live portfolio mutation passed mandatory safeguard gate")
                else:
                    alerts.append("restricted-live portfolio mutation blocked by mandatory safeguard gate")
                    success = False
            else:
                alerts.append("restricted-live portfolio mutation gate observed no live updates")
        else:
            alerts.append("restricted-live has no live portfolio mutation gate configured")
        cycle_result = RuntimeCycleResult(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            processed_instruments=(instrument.instrument_id,),
            signals=signals,
            risk_decisions=risk_decisions,
            execution_intents=execution_intents,
            reconciliation_events=reconciliation_events,
            quality_states=quality_evaluation.states,
            quality_details=quality_evaluation.details,
            alerts=tuple(dict.fromkeys(alerts)),
            success=success,
        )
        self.context.persistence_gateway.persist_cycle(
            cycle_result,
            features=features,
            context=decision_context,
            exchange_health=_exchange_health(self.context),
        )
        return cycle_result
