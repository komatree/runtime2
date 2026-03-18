"""Live portfolio translation safeguard scenarios."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import OrderSide
from app.contracts import AccountSnapshot
from app.contracts import AssetBalanceSnapshot
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import OrderType
from app.contracts import PortfolioState
from app.contracts import ReconciliationState
from app.portfolio import LivePortfolioTranslator
from app.portfolio import LiveTranslationStatus
from app.portfolio import build_portfolio_baseline_from_account_snapshot


def test_partial_fill_applies_known_fill_and_keeps_order_pending() -> None:
    translator = LivePortfolioTranslator()

    result = translator.translate(
        portfolio_state=_portfolio(),
        order_states=(
            _order_state(
                order_id="order-1",
                status=OrderStatus.PARTIALLY_FILLED,
                requested="2",
                filled="1",
                remaining="1",
                average_fill_price="100",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-1",
                fill_id="fill-1",
                quantity="1",
                price="100",
                fee="1",
            ),
        ),
    )

    assert result.status is LiveTranslationStatus.APPLIED_WITH_PENDING
    assert result.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert result.portfolio_state.cash_by_asset["USDT"] == Decimal("899")
    assert result.pending_order_ids == ("order-1",)


def test_delayed_fill_is_applied_once_and_duplicate_fill_is_ignored() -> None:
    translator = LivePortfolioTranslator()
    base_portfolio = _portfolio()

    first = translator.translate(
        portfolio_state=base_portfolio,
        order_states=(
            _order_state(
                order_id="order-2",
                status=OrderStatus.PARTIALLY_FILLED,
                requested="2",
                filled="1",
                remaining="1",
                average_fill_price="101",
            ),
        ),
        fill_events=(),
    )
    second = translator.translate(
        portfolio_state=first.portfolio_state,
        order_states=(
            _order_state(
                order_id="order-2",
                status=OrderStatus.PARTIALLY_FILLED,
                requested="2",
                filled="1",
                remaining="1",
                average_fill_price="101",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-2",
                fill_id="fill-2",
                quantity="1",
                price="101",
                fee="1",
            ),
        ),
    )
    third = translator.translate(
        portfolio_state=second.portfolio_state,
        order_states=(
            _order_state(
                order_id="order-2",
                status=OrderStatus.PARTIALLY_FILLED,
                requested="2",
                filled="1",
                remaining="1",
                average_fill_price="101",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-2",
                fill_id="fill-2",
                quantity="1",
                price="101",
                fee="1",
            ),
        ),
        already_applied_fill_ids=("fill-2",),
    )

    assert first.status is LiveTranslationStatus.APPLIED_WITH_PENDING
    assert first.portfolio_state == base_portfolio
    assert second.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert second.applied_fill_ids == ("fill-2",)
    assert third.portfolio_state == second.portfolio_state
    assert third.ignored_fill_ids == ("fill-2",)


def test_recovery_path_blocks_portfolio_mutation_until_resolution() -> None:
    translator = LivePortfolioTranslator()

    result = translator.translate(
        portfolio_state=_portfolio(),
        order_states=(
            _order_state(
                order_id="order-3",
                status=OrderStatus.RECOVERING,
                requested="1",
                filled="1",
                remaining="0",
                average_fill_price="102",
                reconciliation_state=ReconciliationState.STATUS_QUERY_PENDING,
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-3",
                fill_id="fill-3",
                quantity="1",
                price="102",
                fee="1",
            ),
        ),
    )

    assert result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert result.requires_manual_attention is True
    assert result.portfolio_state == _portfolio()
    assert "portfolio mutation blocked" in result.alerts[0]


def test_account_snapshot_mismatch_stays_explicit_and_non_mutating() -> None:
    translator = LivePortfolioTranslator()

    result = translator.translate(
        portfolio_state=_portfolio(),
        order_states=(
            _order_state(
                order_id="order-4",
                status=OrderStatus.FILLED,
                requested="1",
                filled="1",
                remaining="0",
                average_fill_price="100",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-4",
                fill_id="fill-4",
                quantity="1",
                price="100",
                fee="1",
            ),
        ),
        account_cash_snapshot={"USDT": Decimal("850")},
        updated_assets=("USDT",),
    )

    assert result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert result.requires_manual_attention is True
    assert result.portfolio_state == _portfolio()
    assert "account snapshot mismatch" in result.alerts[-1]


def test_private_fill_takes_precedence_over_recovered_synthetic_fill_for_same_order() -> None:
    translator = LivePortfolioTranslator()

    result = translator.translate(
        portfolio_state=_portfolio(),
        order_states=(
            _order_state(
                order_id="order-5",
                status=OrderStatus.FILLED,
                requested="1",
                filled="1",
                remaining="0",
                average_fill_price="100",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-5",
                fill_id="order-5:9001",
                quantity="1",
                price="100",
                fee="1",
            ),
            _fill(
                order_id="order-5",
                fill_id="order-5:recovered:9001",
                quantity="1",
                price="100",
                fee="0",
            ),
        ),
    )

    assert result.status is LiveTranslationStatus.APPLIED
    assert result.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert result.portfolio_state.cash_by_asset["USDT"] == Decimal("899")
    assert result.applied_fill_ids == ("order-5:9001",)
    assert result.ignored_fill_ids == ("order-5:recovered:9001",)
    assert not any("exceeds order_state.filled_quantity" in alert for alert in result.alerts)


def test_later_private_fill_is_treated_as_enrichment_after_recovered_fill_was_applied() -> None:
    translator = LivePortfolioTranslator()
    portfolio_after_recovered_fill = PortfolioState(
        as_of=_ts(),
        cash_by_asset={"USDT": Decimal("900")},
        position_qty_by_instrument={"BTC-USDT": Decimal("1")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("100")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("100"),
        net_exposure=Decimal("100"),
    )

    result = translator.translate(
        portfolio_state=portfolio_after_recovered_fill,
        order_states=(
            _order_state(
                order_id="order-6",
                status=OrderStatus.FILLED,
                requested="1",
                filled="1",
                remaining="0",
                average_fill_price="100",
            ),
        ),
        fill_events=(
            _fill(
                order_id="order-6",
                fill_id="order-6:9002",
                quantity="1",
                price="100",
                fee="1",
            ),
        ),
        already_applied_fill_ids=("order-6:recovered:order-6",),
    )

    assert result.status is LiveTranslationStatus.APPLIED
    assert result.portfolio_state == portfolio_after_recovered_fill
    assert result.applied_fill_ids == ()
    assert result.ignored_fill_ids == ("order-6:9002",)
    assert not any("account snapshot mismatch" in alert for alert in result.alerts)


def test_account_snapshot_bootstrap_builds_baseline_from_live_balances() -> None:
    snapshot = AccountSnapshot(
        venue="binance",
        account_scope="spot",
        as_of=_ts(),
        balances=(
            AssetBalanceSnapshot(asset="BTC", free=Decimal("1.25"), locked=Decimal("0")),
            AssetBalanceSnapshot(asset="USDT", free=Decimal("900"), locked=Decimal("25")),
        ),
        source_event_type="restAccountSnapshot",
        translation_version="binance.account.bootstrap.v1",
    )

    portfolio = build_portfolio_baseline_from_account_snapshot(
        snapshot=snapshot,
        instrument_id="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
    )

    assert portfolio.position_qty_by_instrument["BTC-USDT"] == Decimal("1.25")
    assert portfolio.cash_by_asset["USDT"] == Decimal("925")


def test_account_snapshot_alignment_uses_position_quantity_for_base_asset() -> None:
    translator = LivePortfolioTranslator()
    baseline = PortfolioState(
        as_of=_ts(),
        cash_by_asset={"USDT": Decimal("889")},
        position_qty_by_instrument={"BTC-USDT": Decimal("1.1")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )

    result = translator.translate(
        portfolio_state=baseline,
        order_states=(),
        fill_events=(),
        account_cash_snapshot={"BTC": Decimal("1.1"), "USDT": Decimal("889")},
        updated_assets=("BTC", "USDT"),
    )

    assert result.status is LiveTranslationStatus.APPLIED
    assert result.portfolio_state == baseline
    assert not any("account snapshot mismatch" in alert for alert in result.alerts)


def _portfolio() -> PortfolioState:
    return PortfolioState(
        as_of=_ts(),
        cash_by_asset={"USDT": Decimal("1000")},
        position_qty_by_instrument={"BTC-USDT": Decimal("0")},
        average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        gross_exposure=Decimal("0"),
        net_exposure=Decimal("0"),
    )


def _order_state(
    *,
    order_id: str,
    status: OrderStatus,
    requested: str,
    filled: str,
    remaining: str,
    average_fill_price: str,
    reconciliation_state: ReconciliationState | None = None,
) -> OrderState:
    return OrderState(
        venue="binance",
        order_id=order_id,
        client_order_id=order_id,
        instrument_id="BTC-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        status=status,
        requested_quantity=Decimal(requested),
        filled_quantity=Decimal(filled),
        remaining_quantity=Decimal(remaining),
        last_update_time=_ts(),
        average_fill_price=Decimal(average_fill_price),
        reconciliation_state=reconciliation_state,
        reconciliation_detail="test",
    )


def _fill(
    *,
    order_id: str,
    fill_id: str,
    quantity: str,
    price: str,
    fee: str,
):
    from app.contracts import FillEvent
    from app.contracts import LiquidityRole

    return FillEvent(
        venue="binance",
        order_id=order_id,
        fill_id=fill_id,
        instrument_id="BTC-USDT",
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fee=Decimal(fee),
        fee_asset="USDT",
        occurred_at=_ts(),
        liquidity_role=LiquidityRole.TAKER,
    )


def _ts() -> datetime:
    return datetime(2026, 3, 13, 0, 0, tzinfo=UTC)
