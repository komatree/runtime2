"""Restricted-live Binance portfolio mutation gate.

This module keeps Binance-specific payload ingestion, canonical translation,
reconciliation, and guarded portfolio mutation inside the exchange boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from typing import Protocol
from typing import TYPE_CHECKING

from app.contracts import AccountSnapshot
from app.contracts import ReconciliationState
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import PortfolioState
from app.portfolio import LivePortfolioMutationOutcome
from app.portfolio import LivePortfolioTranslationResult
from app.portfolio import LivePortfolioTranslator
from app.portfolio import LiveTranslationStatus

from .order_client import BinanceOrderClient
from .order_client import BinanceOrderStatusLookupTransport
from .private_payload_translator import BinancePrivatePayloadTranslator
from .private_stream_client import BinancePrivateStreamClient
from .reconciliation import BinanceReconciliationService
from .reconciliation import BinanceReconciliationStateStore

if TYPE_CHECKING:
    from .reconciliation import BinanceTransportReconciliationResult


class BinancePrivatePayloadSource(Protocol):
    """Provides raw Binance private payload batches without leaking transport details upstream."""

    def poll_private_payloads(self) -> tuple[dict[str, object], ...]:
        """Return the next batch of raw private payloads."""


@dataclass(frozen=True)
class BinanceRestrictedLiveGateResult:
    """Detailed restricted-live gate result for monitoring and soak workflows."""

    mutation_outcome: LivePortfolioMutationOutcome
    transport_result: BinanceTransportReconciliationResult | None = None

@dataclass(frozen=True)
class BinanceRestrictedLivePortfolioGate:
    """Adapter-local gate for any restricted-live portfolio mutation attempt."""

    payload_source: BinancePrivatePayloadSource
    private_stream_client: BinancePrivateStreamClient
    private_payload_translator: BinancePrivatePayloadTranslator
    reconciliation_service: BinanceReconciliationService
    order_client: BinanceOrderClient
    lookup_transport: BinanceOrderStatusLookupTransport
    reconciliation_state_store: BinanceReconciliationStateStore | None = None
    live_portfolio_translator: LivePortfolioTranslator = LivePortfolioTranslator()
    private_session: object | Callable[[], object | None] | None = None

    def apply(
        self,
        *,
        portfolio_state: PortfolioState,
        expected_order_ids: tuple[str, ...] = (),
        already_applied_fill_ids: tuple[str, ...] = (),
    ) -> LivePortfolioMutationOutcome:
        """Translate and apply live Binance updates only when the safety gate allows it."""

        return self.apply_with_details(
            portfolio_state=portfolio_state,
            expected_order_ids=expected_order_ids,
            already_applied_fill_ids=already_applied_fill_ids,
        ).mutation_outcome

    def apply_with_details(
        self,
        *,
        portfolio_state: PortfolioState,
        expected_order_ids: tuple[str, ...] = (),
        already_applied_fill_ids: tuple[str, ...] = (),
    ) -> BinanceRestrictedLiveGateResult:
        """Return guarded mutation plus transport-backed reconciliation details."""

        private_payloads = self.payload_source.poll_private_payloads()
        if not private_payloads:
            translation_result = LivePortfolioTranslationResult(
                status=LiveTranslationStatus.APPLIED,
                portfolio_state=portfolio_state,
                applied_fill_ids=(),
                ignored_fill_ids=(),
                pending_order_ids=(),
                alerts=("no private payloads available for restricted-live mutation gate",),
                aggregations=(),
                requires_manual_attention=False,
            )
            return BinanceRestrictedLiveGateResult(
                mutation_outcome=LivePortfolioMutationOutcome(
                    mutation_attempted=False,
                    mutation_applied=False,
                    portfolio_state=portfolio_state,
                    translation_result=translation_result,
                    alerts=translation_result.alerts,
                ),
                transport_result=None,
            )

        transport_result = self.reconciliation_service.reconcile_with_transports(
            expected_order_ids=expected_order_ids,
            private_payloads=private_payloads,
            private_stream_client=self.private_stream_client,
            translator=self.private_payload_translator,
            order_client=self.order_client,
            lookup_transport=self.lookup_transport,
            state_store=self.reconciliation_state_store,
            session=self._resolved_private_session(),
        )

        translation_alerts = [
            alert
            for translation in transport_result.translations
            for alert in translation.alerts
        ]
        malformed = tuple(
            translation
            for translation in transport_result.translations
            if translation.status.value == "malformed"
        )
        if malformed:
            blocked_translation = LivePortfolioTranslationResult(
                status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                portfolio_state=portfolio_state,
                applied_fill_ids=(),
                ignored_fill_ids=(),
                pending_order_ids=(),
                alerts=tuple(dict.fromkeys(("malformed Binance private payload blocked portfolio mutation", *translation_alerts))),
                aggregations=(),
                requires_manual_attention=True,
            )
            return BinanceRestrictedLiveGateResult(
                mutation_outcome=LivePortfolioMutationOutcome(
                    mutation_attempted=True,
                    mutation_applied=False,
                    portfolio_state=portfolio_state,
                    translation_result=blocked_translation,
                    reconciliation_events=transport_result.workflow_result.reconciliation_events,
                    alerts=tuple(
                        dict.fromkeys(
                            (
                                *blocked_translation.alerts,
                                *transport_result.workflow_result.alerts,
                                *(alert for health in transport_result.status_query_health for alert in ((health.alert,) if health.alert else ())),
                            )
                        )
                    ),
                ),
                transport_result=transport_result,
            )

        translated_order_states = tuple(
            translation.order_state
            for translation in transport_result.translations
            if translation.order_state is not None
        )
        translated_fill_events = tuple(
            translation.fill_event
            for translation in transport_result.translations
            if translation.fill_event is not None
        )
        translated_fill_events = (
            *translated_fill_events,
            *transport_result.workflow_result.recovered_fill_events,
        )
        stream_invalidated = any(
            translation.stream_invalidated for translation in transport_result.translations
        )
        merged_order_states = self._merge_order_states(
            translated_order_states=translated_order_states,
            reconciled_order_states=transport_result.workflow_result.order_states,
        )
        confirmed_order_ids = tuple(
            dict.fromkeys(
                (
                    *(state.order_id for state in translated_order_states),
                    *(fill.order_id for fill in translated_fill_events),
                )
            )
        )
        if stream_invalidated:
            blocked_order_ids = tuple(
                order_id
                for order_id in expected_order_ids
                if order_id not in confirmed_order_ids
            )
            if blocked_order_ids:
                blocked_translation = LivePortfolioTranslationResult(
                    status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                    portfolio_state=portfolio_state,
                    applied_fill_ids=(),
                    ignored_fill_ids=(),
                    pending_order_ids=blocked_order_ids,
                    alerts=tuple(
                        dict.fromkeys(
                            (
                                *translation_alerts,
                                *(
                                    "portfolio mutation blocked after private-stream invalidation "
                                    f"until canonical private confirmation for order: {order_id}"
                                    for order_id in blocked_order_ids
                                ),
                            )
                        )
                    ),
                    aggregations=(),
                    requires_manual_attention=True,
                )
                return BinanceRestrictedLiveGateResult(
                    mutation_outcome=LivePortfolioMutationOutcome(
                        mutation_attempted=True,
                        mutation_applied=False,
                        portfolio_state=portfolio_state,
                        translation_result=blocked_translation,
                        reconciliation_events=transport_result.workflow_result.reconciliation_events,
                        alerts=tuple(
                            dict.fromkeys(
                                (
                                    *blocked_translation.alerts,
                                    *transport_result.workflow_result.alerts,
                                    *(alert for health in transport_result.status_query_health for alert in ((health.alert,) if health.alert else ())),
                                )
                            )
                        ),
                    ),
                    transport_result=transport_result,
                )
        unresolved_order_ids = tuple(
            state.order_id
            for state in merged_order_states
            if state.status in {OrderStatus.RECOVERING, OrderStatus.UNRECONCILED}
            or state.reconciliation_state
            in {
                ReconciliationState.UNKNOWN_EXECUTION,
                ReconciliationState.STATUS_QUERY_PENDING,
                ReconciliationState.UNRECONCILED_MANUAL_ATTENTION,
            }
        )
        if unresolved_order_ids:
            blocked_translation = LivePortfolioTranslationResult(
                status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                portfolio_state=portfolio_state,
                applied_fill_ids=(),
                ignored_fill_ids=(),
                pending_order_ids=unresolved_order_ids,
                alerts=tuple(
                    dict.fromkeys(
                        (
                            *translation_alerts,
                            *(
                                f"portfolio mutation blocked pending reconciliation for order: {order_id}"
                                for order_id in unresolved_order_ids
                            ),
                        )
                    )
                ),
                aggregations=(),
                requires_manual_attention=True,
            )
            return BinanceRestrictedLiveGateResult(
                mutation_outcome=LivePortfolioMutationOutcome(
                    mutation_attempted=True,
                    mutation_applied=False,
                    portfolio_state=portfolio_state,
                    translation_result=blocked_translation,
                    reconciliation_events=transport_result.workflow_result.reconciliation_events,
                    alerts=tuple(
                        dict.fromkeys(
                            (
                                *blocked_translation.alerts,
                                *transport_result.workflow_result.alerts,
                                *(alert for health in transport_result.status_query_health for alert in ((health.alert,) if health.alert else ())),
                            )
                        )
                    ),
                ),
                transport_result=transport_result,
            )
        if self.order_client.can_submit_orders():
            clock_status = self.order_client.clock_sync.check()
            if not clock_status.is_within_tolerance:
                blocked_translation = LivePortfolioTranslationResult(
                    status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                    portfolio_state=portfolio_state,
                    applied_fill_ids=(),
                    ignored_fill_ids=(),
                    pending_order_ids=(),
                    alerts=tuple(
                        dict.fromkeys(
                            (
                                *translation_alerts,
                                "portfolio mutation blocked pending clock sync readiness after reconnect or restart",
                            )
                        )
                    ),
                    aggregations=(),
                    requires_manual_attention=True,
                )
                return BinanceRestrictedLiveGateResult(
                    mutation_outcome=LivePortfolioMutationOutcome(
                        mutation_attempted=True,
                        mutation_applied=False,
                        portfolio_state=portfolio_state,
                        translation_result=blocked_translation,
                        reconciliation_events=transport_result.workflow_result.reconciliation_events,
                        alerts=tuple(
                            dict.fromkeys(
                                (
                                    *blocked_translation.alerts,
                                    *transport_result.workflow_result.alerts,
                                    *(alert for health in transport_result.status_query_health for alert in ((health.alert,) if health.alert else ())),
                                    *(transport_result.batch_health.alerts if transport_result.batch_health is not None else ()),
                                    *((clock_status.alert,) if clock_status.alert else ()),
                                )
                            )
                        ),
                    ),
                    transport_result=transport_result,
                )
        latest_snapshot = self._latest_full_account_snapshot(
            tuple(
                translation.account_snapshot
                for translation in transport_result.translations
                if translation.account_snapshot is not None
            )
        )
        translation_result = self.live_portfolio_translator.translate(
            portfolio_state=portfolio_state,
            order_states=merged_order_states,
            fill_events=translated_fill_events,
            already_applied_fill_ids=already_applied_fill_ids,
            account_cash_snapshot=self._cash_snapshot(latest_snapshot),
            updated_assets=self._updated_assets(latest_snapshot),
        )
        extra_alerts = []
        if not translation_result.requires_manual_attention and latest_snapshot is not None:
            extra_alerts.append(
                f"restricted-live portfolio mutation passed canonical translation gate using {latest_snapshot.source_event_type}"
            )
        if translation_result.requires_manual_attention:
            extra_alerts.append("restricted-live portfolio mutation blocked by safety gate")
        if transport_result.batch_health is not None:
            extra_alerts.extend(transport_result.batch_health.alerts)
        extra_alerts.extend(transport_result.workflow_result.alerts)
        for health in transport_result.status_query_health:
            if health.alert:
                extra_alerts.append(health.alert)

        return BinanceRestrictedLiveGateResult(
            mutation_outcome=LivePortfolioMutationOutcome(
                mutation_attempted=True,
                mutation_applied=not translation_result.requires_manual_attention,
                portfolio_state=translation_result.portfolio_state,
                translation_result=translation_result,
                reconciliation_events=transport_result.workflow_result.reconciliation_events,
                alerts=tuple(dict.fromkeys((*translation_result.alerts, *translation_alerts, *extra_alerts))),
            ),
            transport_result=transport_result,
        )

    def _merge_order_states(
        self,
        *,
        translated_order_states: tuple[OrderState, ...],
        reconciled_order_states: tuple[OrderState, ...],
    ) -> tuple[OrderState, ...]:
        by_id: dict[str, OrderState] = {state.order_id: state for state in translated_order_states}
        for state in reconciled_order_states:
            existing = by_id.get(state.order_id)
            if existing is None:
                by_id[state.order_id] = state
                continue
            prefer_reconciled_shape = (
                existing.instrument_id == "UNKNOWN"
                or existing.requested_quantity == Decimal("0")
            )
            richer_reconciled_quantities = (
                state.filled_quantity > existing.filled_quantity
                or state.remaining_quantity < existing.remaining_quantity
                or (
                    state.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
                    and existing.status not in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
                )
            )
            resolved_status = (
                existing.status
                if state.reconciliation_state is ReconciliationState.SUBMIT_SENT
                else state.status
            )
            by_id[state.order_id] = OrderState(
                venue=state.venue if prefer_reconciled_shape else existing.venue,
                order_id=existing.order_id,
                client_order_id=(
                    state.client_order_id
                    if prefer_reconciled_shape and state.client_order_id
                    else existing.client_order_id
                ),
                instrument_id=state.instrument_id if prefer_reconciled_shape else existing.instrument_id,
                side=state.side if prefer_reconciled_shape else existing.side,
                order_type=state.order_type if prefer_reconciled_shape else existing.order_type,
                status=resolved_status,
                requested_quantity=(
                    state.requested_quantity
                    if prefer_reconciled_shape
                    or richer_reconciled_quantities
                    or (
                        existing.requested_quantity == Decimal("0")
                        and state.requested_quantity > Decimal("0")
                    )
                    else existing.requested_quantity
                ),
                filled_quantity=(
                    state.filled_quantity
                    if prefer_reconciled_shape or richer_reconciled_quantities
                    else existing.filled_quantity
                ),
                remaining_quantity=(
                    state.remaining_quantity
                    if prefer_reconciled_shape or richer_reconciled_quantities
                    else existing.remaining_quantity
                ),
                last_update_time=max(existing.last_update_time, state.last_update_time),
                limit_price=state.limit_price if prefer_reconciled_shape else existing.limit_price,
                average_fill_price=(
                    state.average_fill_price
                    if prefer_reconciled_shape
                    or (
                        richer_reconciled_quantities
                        and state.average_fill_price is not None
                    )
                    else existing.average_fill_price
                ),
                reconciliation_state=state.reconciliation_state,
                reconciliation_detail=state.reconciliation_detail,
            )
        return tuple(by_id.values())

    def _latest_full_account_snapshot(
        self,
        snapshots: tuple[AccountSnapshot, ...],
    ) -> AccountSnapshot | None:
        full_snapshots = [snapshot for snapshot in snapshots if not snapshot.is_partial]
        return full_snapshots[-1] if full_snapshots else None

    def _resolved_private_session(self) -> object | None:
        if callable(self.private_session):
            return self.private_session()
        return self.private_session

    def _cash_snapshot(
        self,
        snapshot: AccountSnapshot | None,
    ) -> dict[str, Decimal] | None:
        if snapshot is None:
            return None
        return {
            balance.asset: (balance.free or Decimal("0")) + (balance.locked or Decimal("0"))
            for balance in snapshot.balances
            if balance.free is not None or balance.locked is not None
        }

    def _updated_assets(
        self,
        snapshot: AccountSnapshot | None,
    ) -> tuple[str, ...]:
        if snapshot is None:
            return ()
        return tuple(balance.asset for balance in snapshot.balances)
