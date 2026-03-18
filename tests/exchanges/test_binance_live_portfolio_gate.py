"""Restricted-live Binance portfolio mutation gate tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import OrderSide
from app.contracts import OrderStatus
from app.contracts import OrderType
from app.contracts import PortfolioState
from app.contracts import FillEvent
from app.contracts import LiquidityRole
from app.contracts import OrderState
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
from app.portfolio import LiveTranslationStatus


def test_mutation_allowed_after_safe_canonical_translation() -> None:
    gate = _gate(
        payloads=(
            _filled_trade_payload(order_id=3001),
        ),
        lookup_results=(),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("3001",),
    )

    assert outcome.mutation_attempted is True
    assert outcome.mutation_applied is True
    assert outcome.translation_result.status is LiveTranslationStatus.APPLIED
    assert outcome.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert outcome.portfolio_state.cash_by_asset["USDT"] == Decimal("899")


def test_mutation_blocked_on_ambiguity() -> None:
    gate = _gate(
        payloads=(
            {
                "e": "executionReport",
                "E": 1773360000000,
                "s": "BTCUSDT",
                "c": "client-ambiguous",
                "S": "BUY",
            },
        ),
        lookup_results=(),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("ambiguous",),
    )

    assert outcome.mutation_applied is False
    assert outcome.translation_result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert "malformed Binance private payload blocked portfolio mutation" in outcome.alerts[0]


def test_mutation_blocked_on_unreconciled_state() -> None:
    gate = _gate(
        payloads=(
            _terminated_payload(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value="5001",
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="lookup unresolved",
            ),
            BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value="5001",
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="lookup unresolved",
            ),
            BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value="5001",
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="lookup unresolved",
            ),
        ),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("5001", "5001", "5001"),
    )

    assert outcome.mutation_applied is False
    assert outcome.translation_result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert outcome.reconciliation_events[-1].reconciliation_state.value == "unreconciled_manual_attention"
    assert any(
        "until canonical private confirmation for order: 5001" in alert
        for alert in outcome.alerts
    )


def test_expiry_driven_recovery_does_not_allow_premature_mutation_without_private_confirmation() -> None:
    gate = _gate(
        payloads=(
            _terminated_payload(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="5201",
                source="signed_rest_order_lookup",
                status_summary="filled",
                alert=None,
            ),
        ),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("5201",),
    )

    assert outcome.mutation_applied is False
    assert outcome.translation_result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert outcome.translation_result.pending_order_ids == ("5201",)
    assert any(
        "until canonical private confirmation for order: 5201" in alert
        for alert in outcome.alerts
    )


def test_mutation_blocked_on_snapshot_mismatch() -> None:
    gate = _gate(
        payloads=(
            _filled_trade_payload(order_id=4001),
            _account_update_payload(usdt_free="850"),
        ),
        lookup_results=(),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("4001",),
    )

    assert outcome.mutation_applied is False
    assert outcome.translation_result.status is LiveTranslationStatus.AMBIGUOUS_REVIEW_REQUIRED
    assert any("account snapshot mismatch" in alert for alert in outcome.alerts)


def test_bootstrapped_portfolio_does_not_block_on_matching_account_snapshot() -> None:
    gate = _gate(
        payloads=(
            _account_update_payload(usdt_free="850"),
        ),
        lookup_results=(),
    )

    outcome = gate.apply(
        portfolio_state=PortfolioState(
            as_of=_ts(),
            cash_by_asset={"USDT": Decimal("850")},
            position_qty_by_instrument={"BTC-USDT": Decimal("1")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
        expected_order_ids=(),
    )

    assert outcome.mutation_applied is True
    assert not any("account snapshot mismatch" in alert for alert in outcome.alerts)


def test_bootstrapped_portfolio_allows_locked_quote_balance_when_total_matches() -> None:
    gate = _gate(
        payloads=(
            {
                "e": "outboundAccountPosition",
                "E": 1773360001000,
                "B": [
                    {"a": "USDT", "f": "850", "l": "25"},
                    {"a": "BTC", "f": "1", "l": "0"},
                ],
            },
        ),
        lookup_results=(),
    )

    outcome = gate.apply(
        portfolio_state=PortfolioState(
            as_of=_ts(),
            cash_by_asset={"USDT": Decimal("875")},
            position_qty_by_instrument={"BTC-USDT": Decimal("1")},
            average_entry_price_by_instrument={"BTC-USDT": Decimal("0")},
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
        expected_order_ids=(),
    )

    assert outcome.mutation_applied is True
    assert not any("account snapshot mismatch" in alert for alert in outcome.alerts)


def test_recovered_filled_lookup_can_supply_fill_events_for_mutation_readiness() -> None:
    gate = _gate(
        payloads=(
            _balance_delta_payload(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value="5202",
                source="signed_rest_order_lookup",
                status_summary="filled",
                recovered_order_state=OrderState(
                    venue="binance",
                    order_id="5202",
                    client_order_id="client-5202",
                    instrument_id="BTC-USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.FILLED,
                    requested_quantity=Decimal("1"),
                    filled_quantity=Decimal("1"),
                    remaining_quantity=Decimal("0"),
                    last_update_time=_ts(),
                    average_fill_price=Decimal("100"),
                ),
                recovered_fill_events=(
                    FillEvent(
                        venue="binance",
                        order_id="5202",
                        fill_id="5202:recovered:5202",
                        instrument_id="BTC-USDT",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("100"),
                        fee=Decimal("0"),
                        fee_asset="USDT",
                        occurred_at=_ts(),
                        liquidity_role=LiquidityRole.UNKNOWN,
                    ),
                ),
            ),
        ),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=("5202",),
    )

    assert outcome.mutation_attempted is True
    assert outcome.mutation_applied is True
    assert outcome.translation_result.status is LiveTranslationStatus.APPLIED
    assert outcome.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert outcome.portfolio_state.cash_by_asset["USDT"] == Decimal("900")
    assert not any("missing fill details" in alert for alert in outcome.alerts)


def test_private_fill_and_recovered_fill_do_not_double_count_same_order() -> None:
    order_id = 5302
    gate = _gate(
        payloads=(
            _filled_trade_payload(order_id=order_id),
            _terminated_payload(),
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value=str(order_id),
                source="signed_rest_order_lookup",
                status_summary="filled",
                recovered_order_state=OrderState(
                    venue="binance",
                    order_id=str(order_id),
                    client_order_id=f"client-{order_id}",
                    instrument_id="BTC-USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.FILLED,
                    requested_quantity=Decimal("1"),
                    filled_quantity=Decimal("1"),
                    remaining_quantity=Decimal("0"),
                    last_update_time=_ts(),
                    average_fill_price=Decimal("100"),
                ),
                recovered_fill_events=(
                    FillEvent(
                        venue="binance",
                        order_id=str(order_id),
                        fill_id=f"{order_id}:recovered:{order_id}",
                        instrument_id="BTC-USDT",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("100"),
                        fee=Decimal("0"),
                        fee_asset="USDT",
                        occurred_at=_ts(),
                        liquidity_role=LiquidityRole.UNKNOWN,
                    ),
                ),
            ),
        ),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=(str(order_id),),
    )

    assert outcome.mutation_applied is True
    assert outcome.translation_result.status is LiveTranslationStatus.APPLIED
    assert not any("exceeds order_state.filled_quantity" in alert for alert in outcome.alerts)
    assert outcome.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert outcome.portfolio_state.cash_by_asset["USDT"] == Decimal("899")


def test_same_cycle_private_fill_and_recovered_terminal_state_use_richer_reconciled_quantity() -> None:
    order_id = 5401
    gate = _gate(
        payloads=(
            {
                "e": "executionReport",
                "E": 1773360000000,
                "s": "BTCUSDT",
                "c": f"client-{order_id}",
                "S": "BUY",
                "o": "MARKET",
                "X": "NEW",
                "x": "TRADE",
                "q": "1",
                "z": "0",
                "l": "1",
                "L": "100",
                "Z": "100",
                "n": "1",
                "N": "USDT",
                "i": order_id,
                "t": order_id + 1000,
                "m": False,
            },
        ),
        lookup_results=(
            BinanceOrderLookupResult(
                found=True,
                lookup_field="exchange_order_id",
                lookup_value=str(order_id),
                source="signed_rest_order_lookup",
                status_summary="filled",
                recovered_order_state=OrderState(
                    venue="binance",
                    order_id=str(order_id),
                    client_order_id=f"client-{order_id}",
                    instrument_id="BTC-USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.FILLED,
                    requested_quantity=Decimal("1"),
                    filled_quantity=Decimal("1"),
                    remaining_quantity=Decimal("0"),
                    last_update_time=_ts(),
                    average_fill_price=Decimal("100"),
                ),
                recovered_fill_events=(
                    FillEvent(
                        venue="binance",
                        order_id=str(order_id),
                        fill_id=f"{order_id}:recovered:{order_id}",
                        instrument_id="BTC-USDT",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("100"),
                        fee=Decimal("0"),
                        fee_asset="USDT",
                        occurred_at=_ts(),
                        liquidity_role=LiquidityRole.UNKNOWN,
                    ),
                ),
            ),
        ),
    )

    outcome = gate.apply(
        portfolio_state=_portfolio(),
        expected_order_ids=(),
    )

    assert outcome.mutation_applied is True
    assert outcome.translation_result.status is LiveTranslationStatus.APPLIED
    assert not any("exceeds order_state.filled_quantity" in alert for alert in outcome.alerts)
    assert outcome.portfolio_state.position_qty_by_instrument["BTC-USDT"] == Decimal("1")
    assert outcome.portfolio_state.cash_by_asset["USDT"] == Decimal("899")


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
        return self._next_result("client_order_id", client_order_id)

    def lookup_by_exchange_order_id(self, *, exchange_order_id: str) -> BinanceOrderLookupResult:
        return self._next_result("exchange_order_id", exchange_order_id)

    def last_health(self) -> BinanceStatusQueryHealth | None:
        return self._last_health

    def _next_result(self, lookup_field: str, lookup_value: str) -> BinanceOrderLookupResult:
        if self._results:
            result = self._results.pop(0)
        else:
            result = BinanceOrderLookupResult(
                found=False,
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="lookup unresolved",
            )
        self._last_health = BinanceStatusQueryHealth(
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            state=BinanceStatusQueryState.SUCCESS if result.found else BinanceStatusQueryState.FAILED,
            checked_at=_ts(),
            transport="test_lookup_transport",
            alert=result.alert,
        )
        return result


def _gate(
    *,
    payloads: tuple[dict[str, object], ...],
    lookup_results: tuple[BinanceOrderLookupResult, ...],
) -> BinanceRestrictedLivePortfolioGate:
    return BinanceRestrictedLivePortfolioGate(
        payload_source=_PayloadSource(payloads=payloads),
        private_stream_client=BinancePrivateStreamClient(config=_config()),
        private_payload_translator=BinancePrivatePayloadTranslator(
            symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
        ),
        reconciliation_service=BinanceReconciliationService(),
        order_client=BinanceOrderClient(config=_config(), clock_sync=BinanceClockSync(_config())),
        lookup_transport=_LookupTransport(lookup_results),
    )


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        api_key="key",
        api_secret="secret",
    )


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


def _account_update_payload(*, usdt_free: str) -> dict[str, object]:
    return {
        "e": "outboundAccountPosition",
        "E": 1773360001000,
        "B": [
            {"a": "USDT", "f": usdt_free, "l": "0"},
            {"a": "BTC", "f": "1", "l": "0"},
        ],
    }


def _balance_delta_payload() -> dict[str, object]:
    return {
        "e": "balanceUpdate",
        "E": 1773360001500,
        "a": "USDT",
        "d": "-100",
    }


def _terminated_payload() -> dict[str, object]:
    return {
        "e": "listenKeyExpired",
        "E": 1773360002000,
    }


def _ts() -> datetime:
    return datetime(2026, 3, 13, 0, 0, tzinfo=UTC)
