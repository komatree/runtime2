"""Paper-mode portfolio transition helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.contracts import FillEvent
from app.contracts import OrderSide
from app.contracts import PositionState
from app.contracts import PortfolioState


@dataclass(frozen=True)
class PaperPortfolioUpdater:
    """Applies synthetic fills to a canonical portfolio state."""

    quote_asset: str = "USDT"

    def apply_fills(
        self,
        *,
        portfolio_state: PortfolioState,
        fill_events: tuple[FillEvent, ...],
    ) -> PortfolioState:
        """Return a new portfolio state after applying paper fills."""

        cash_by_asset = dict(portfolio_state.cash_by_asset)
        position_qty_by_instrument = dict(portfolio_state.position_qty_by_instrument)
        average_entry_price_by_instrument = dict(portfolio_state.average_entry_price_by_instrument)
        realized_pnl = portfolio_state.realized_pnl
        last_mark_price_by_instrument: dict[str, Decimal] = {}

        for fill in fill_events:
            instrument_id = fill.instrument_id
            qty = fill.quantity
            price = fill.price
            fee = fill.fee
            existing_qty = position_qty_by_instrument.get(instrument_id, Decimal("0"))
            existing_avg = average_entry_price_by_instrument.get(instrument_id, Decimal("0"))
            quote_cash = cash_by_asset.get(self.quote_asset, Decimal("0"))
            last_mark_price_by_instrument[instrument_id] = price

            if fill.side is OrderSide.BUY:
                new_qty = existing_qty + qty
                new_avg = price if new_qty == qty else ((existing_qty * existing_avg) + (qty * price)) / new_qty
                position_qty_by_instrument[instrument_id] = new_qty
                average_entry_price_by_instrument[instrument_id] = new_avg
                cash_by_asset[self.quote_asset] = quote_cash - (qty * price) - fee
            else:
                new_qty = existing_qty - qty
                realized_pnl += (price - existing_avg) * qty - fee
                position_qty_by_instrument[instrument_id] = new_qty
                average_entry_price_by_instrument[instrument_id] = existing_avg if new_qty != 0 else Decimal("0")
                cash_by_asset[self.quote_asset] = quote_cash + (qty * price) - fee

        gross_exposure = Decimal("0")
        net_exposure = Decimal("0")
        unrealized_pnl = Decimal("0")
        for instrument_id, qty in position_qty_by_instrument.items():
            mark_price = last_mark_price_by_instrument.get(
                instrument_id,
                average_entry_price_by_instrument.get(instrument_id, Decimal("0")),
            )
            exposure = qty * mark_price
            gross_exposure += abs(exposure)
            net_exposure += exposure
            avg_entry = average_entry_price_by_instrument.get(instrument_id, Decimal("0"))
            unrealized_pnl += (mark_price - avg_entry) * qty

        return PortfolioState(
            as_of=fill_events[-1].occurred_at if fill_events else portfolio_state.as_of,
            cash_by_asset=cash_by_asset,
            position_qty_by_instrument=position_qty_by_instrument,
            average_entry_price_by_instrument=average_entry_price_by_instrument,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
        )

    def derive_position_states(
        self,
        *,
        portfolio_state: PortfolioState,
        mark_prices_by_instrument: dict[str, Decimal] | None = None,
    ) -> tuple[PositionState, ...]:
        """Return explicit per-instrument position states for paper-session tracing."""

        prices = mark_prices_by_instrument or {}
        positions: list[PositionState] = []
        for instrument_id in sorted(portfolio_state.position_qty_by_instrument):
            quantity = portfolio_state.position_qty_by_instrument[instrument_id]
            average_entry_price = portfolio_state.average_entry_price_by_instrument.get(
                instrument_id,
                Decimal("0"),
            )
            mark_price = prices.get(instrument_id, average_entry_price)
            positions.append(
                PositionState(
                    instrument_id=instrument_id,
                    quantity=quantity,
                    average_entry_price=average_entry_price,
                    mark_price=mark_price,
                    market_value=quantity * mark_price,
                    unrealized_pnl=(mark_price - average_entry_price) * quantity,
                )
            )
        return tuple(positions)
