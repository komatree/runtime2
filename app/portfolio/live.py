"""Portfolio-safe live order/fill translation safeguards."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.contracts import AccountSnapshot
from app.contracts import FillEvent
from app.contracts import ReconciliationEvent
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import PortfolioState

from .paper import PaperPortfolioUpdater


def _is_recovered_fill(fill: FillEvent) -> bool:
    return ":recovered:" in fill.fill_id


def _recovered_fill_order_id(fill_id: str) -> str | None:
    if ":recovered:" not in fill_id:
        return None
    return fill_id.split(":", 1)[0]


def build_portfolio_baseline_from_account_snapshot(
    *,
    snapshot: AccountSnapshot,
    instrument_id: str,
    base_asset: str,
    quote_asset: str,
) -> PortfolioState:
    """Return a rehearsal-safe portfolio baseline aligned to a live account snapshot."""

    cash_by_asset: dict[str, Decimal] = {}
    for balance in snapshot.balances:
        free = balance.free or Decimal("0")
        locked = balance.locked or Decimal("0")
        total = free + locked
        if balance.asset == base_asset:
            continue
        if total > Decimal("0"):
            cash_by_asset[balance.asset] = total

    base_balance = next(
        (
            (balance.free or Decimal("0")) + (balance.locked or Decimal("0"))
            for balance in snapshot.balances
            if balance.asset == base_asset
        ),
        Decimal("0"),
    )
    quote_balance = next(
        (
            (balance.free or Decimal("0")) + (balance.locked or Decimal("0"))
            for balance in snapshot.balances
            if balance.asset == quote_asset
        ),
        Decimal("0"),
    )
    cash_by_asset.setdefault(quote_asset, quote_balance)
    position_qty = {instrument_id: base_balance}
    average_entry = {instrument_id: Decimal("0")}
    return PortfolioState(
        as_of=snapshot.as_of,
        cash_by_asset=cash_by_asset,
        position_qty_by_instrument=position_qty,
        average_entry_price_by_instrument=average_entry,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


class LiveTranslationStatus(str, Enum):
    """Outcome of one live portfolio translation pass."""

    APPLIED = "applied"
    APPLIED_WITH_PENDING = "applied_with_pending"
    AMBIGUOUS_REVIEW_REQUIRED = "ambiguous_review_required"


@dataclass(frozen=True)
class LiveFillAggregation:
    """Inspectable fill aggregation for one order within a translation pass."""

    order_id: str
    fill_ids: tuple[str, ...]
    total_quantity: Decimal
    average_price: Decimal


@dataclass(frozen=True)
class LivePortfolioTranslationResult:
    """Result of one safeguarded live portfolio translation pass."""

    status: LiveTranslationStatus
    portfolio_state: PortfolioState
    applied_fill_ids: tuple[str, ...]
    ignored_fill_ids: tuple[str, ...]
    pending_order_ids: tuple[str, ...]
    alerts: tuple[str, ...]
    aggregations: tuple[LiveFillAggregation, ...]
    requires_manual_attention: bool


@dataclass(frozen=True)
class LivePortfolioMutationOutcome:
    """Runtime-facing outcome after guarded live portfolio mutation handling."""

    mutation_attempted: bool
    mutation_applied: bool
    portfolio_state: PortfolioState
    translation_result: LivePortfolioTranslationResult
    reconciliation_events: tuple[ReconciliationEvent, ...] = ()
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class LivePortfolioTranslator:
    """Safely translates live order/fill state into canonical portfolio state.

    Principles:
    - only apply fills that are known, non-duplicated, and consistent with order state
    - keep unresolved or ambiguous live state explicit
    - never infer missing fills for terminal orders
    - treat account snapshot mismatches as operator-review events, not silent corrections
    """

    quote_asset: str = "USDT"
    paper_updater: PaperPortfolioUpdater = PaperPortfolioUpdater()

    def translate(
        self,
        *,
        portfolio_state: PortfolioState,
        order_states: tuple[OrderState, ...],
        fill_events: tuple[FillEvent, ...],
        already_applied_fill_ids: tuple[str, ...] = (),
        account_cash_snapshot: dict[str, Decimal] | None = None,
        updated_assets: tuple[str, ...] = (),
    ) -> LivePortfolioTranslationResult:
        """Return a safeguarded portfolio translation result."""

        order_map = {order.order_id: order for order in order_states}
        alerts: list[str] = []
        pending_order_ids: list[str] = []
        ambiguous = False
        ignored_fill_ids: list[str] = []
        applied_fills: list[FillEvent] = []
        fill_ids_seen: dict[str, FillEvent] = {}
        orders_with_applied_recovered_fills = {
            order_id
            for fill_id in already_applied_fill_ids
            for order_id in (_recovered_fill_order_id(fill_id),)
            if order_id is not None
        }

        for fill in fill_events:
            if fill.fill_id in already_applied_fill_ids:
                ignored_fill_ids.append(fill.fill_id)
                continue
            existing = fill_ids_seen.get(fill.fill_id)
            if existing is None:
                fill_ids_seen[fill.fill_id] = fill
                continue
            if existing != fill:
                ambiguous = True
                alerts.append(f"conflicting duplicate fill_id observed: {fill.fill_id}")
            else:
                ignored_fill_ids.append(fill.fill_id)

        grouped_fills: dict[str, list[FillEvent]] = {}
        aggregations: list[LiveFillAggregation] = []
        for fill in fill_ids_seen.values():
            grouped_fills.setdefault(fill.order_id, []).append(fill)

        for order_id, fills in grouped_fills.items():
            order_state = order_map.get(order_id)
            if order_state is None:
                ambiguous = True
                alerts.append(f"fill received without matching order state: {order_id}")
                continue
            if order_state.status in {OrderStatus.RECOVERING, OrderStatus.UNRECONCILED}:
                ambiguous = True
                alerts.append(f"portfolio mutation blocked for ambiguous order state: {order_id}")
                continue

            private_fills = [fill for fill in fills if not _is_recovered_fill(fill)]
            recovered_fills = [fill for fill in fills if _is_recovered_fill(fill)]

            if (
                private_fills
                and not recovered_fills
                and order_state.status is OrderStatus.FILLED
                and order_id in orders_with_applied_recovered_fills
            ):
                private_total_quantity = sum(fill.quantity for fill in private_fills)
                if private_total_quantity <= order_state.filled_quantity:
                    ignored_fill_ids.extend(fill.fill_id for fill in private_fills)
                    continue

            effective_fills = fills
            if private_fills and recovered_fills:
                private_total_quantity = sum(fill.quantity for fill in private_fills)
                if private_total_quantity <= order_state.filled_quantity:
                    effective_fills = private_fills
                    ignored_fill_ids.extend(fill.fill_id for fill in recovered_fills)

            total_quantity = sum(fill.quantity for fill in effective_fills)
            total_notional = sum(fill.quantity * fill.price for fill in effective_fills)
            average_price = total_notional / total_quantity
            aggregations.append(
                LiveFillAggregation(
                    order_id=order_id,
                    fill_ids=tuple(fill.fill_id for fill in effective_fills),
                    total_quantity=total_quantity,
                    average_price=average_price,
                )
            )

            if total_quantity > order_state.filled_quantity:
                ambiguous = True
                alerts.append(f"fill quantity exceeds order_state.filled_quantity for {order_id}")
                continue
            if total_quantity > order_state.requested_quantity:
                ambiguous = True
                alerts.append(f"fill quantity exceeds order_state.requested_quantity for {order_id}")
                continue
            if total_quantity < order_state.filled_quantity:
                if order_state.status is OrderStatus.FILLED:
                    ambiguous = True
                    alerts.append(f"terminal filled order missing fill details: {order_id}")
                    continue
                pending_order_ids.append(order_id)
                alerts.append(f"fill aggregation still pending for order: {order_id}")

            if order_state.status is OrderStatus.PARTIALLY_FILLED and order_id not in pending_order_ids:
                pending_order_ids.append(order_id)
                alerts.append(f"partial order remains open after applied fills: {order_id}")

            applied_fills.extend(sorted(effective_fills, key=lambda fill: (fill.occurred_at, fill.fill_id)))

        for order_state in order_states:
            if order_state.status is OrderStatus.PARTIALLY_FILLED and order_state.order_id not in grouped_fills:
                pending_order_ids.append(order_state.order_id)
                alerts.append(f"partially filled order has no new fill events yet: {order_state.order_id}")
            if order_state.status is OrderStatus.FILLED and order_state.filled_quantity > Decimal("0") and order_state.order_id not in grouped_fills:
                ambiguous = True
                alerts.append(f"filled order missing fill events: {order_state.order_id}")

        if ambiguous:
            return LivePortfolioTranslationResult(
                status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                portfolio_state=portfolio_state,
                applied_fill_ids=(),
                ignored_fill_ids=tuple(sorted(set(ignored_fill_ids))),
                pending_order_ids=tuple(dict.fromkeys(pending_order_ids)),
                alerts=tuple(dict.fromkeys(alerts)),
                aggregations=tuple(aggregations),
                requires_manual_attention=True,
            )

        translated_state = self.paper_updater.apply_fills(
            portfolio_state=portfolio_state,
            fill_events=tuple(applied_fills),
        )

        if account_cash_snapshot is not None and updated_assets:
            mismatch_assets: list[str] = []
            for asset in updated_assets:
                projected = self._projected_asset_balance(
                    portfolio_state=translated_state,
                    asset=asset,
                )
                snapshot = account_cash_snapshot.get(asset)
                if snapshot is None or snapshot != projected:
                    mismatch_assets.append(asset)
            if mismatch_assets:
                return LivePortfolioTranslationResult(
                    status=LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED,
                    portfolio_state=portfolio_state,
                    applied_fill_ids=(),
                    ignored_fill_ids=tuple(sorted(set(ignored_fill_ids))),
                    pending_order_ids=tuple(dict.fromkeys(pending_order_ids)),
                    alerts=tuple(
                        dict.fromkeys(
                            [
                                *alerts,
                                "account snapshot mismatch after projected portfolio translation: "
                                + ",".join(mismatch_assets),
                            ]
                        )
                    ),
                    aggregations=tuple(aggregations),
                    requires_manual_attention=True,
                )

        return LivePortfolioTranslationResult(
            status=(
                LiveTranslationStatus.APPLIED_WITH_PENDING
                if pending_order_ids
                else LiveTranslationStatus.APPLIED
            ),
            portfolio_state=translated_state,
            applied_fill_ids=tuple(fill.fill_id for fill in applied_fills),
            ignored_fill_ids=tuple(sorted(set(ignored_fill_ids))),
            pending_order_ids=tuple(dict.fromkeys(pending_order_ids)),
            alerts=tuple(dict.fromkeys(alerts)),
            aggregations=tuple(aggregations),
            requires_manual_attention=False,
        )

    def _projected_asset_balance(
        self,
        *,
        portfolio_state: PortfolioState,
        asset: str,
    ) -> Decimal:
        direct_cash = portfolio_state.cash_by_asset.get(asset)
        if direct_cash is not None:
            return direct_cash
        matching_instruments = [
            instrument_id
            for instrument_id in portfolio_state.position_qty_by_instrument
            if instrument_id.split("-")[0] == asset
        ]
        if len(matching_instruments) == 1:
            return portfolio_state.position_qty_by_instrument[matching_instruments[0]]
        return Decimal("0")
