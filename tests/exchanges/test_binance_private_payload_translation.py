"""Canonical Binance private payload translation tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import LiquidityRole
from app.contracts import OrderStatus
from app.exchanges.binance import BinancePrivatePayloadTranslator
from app.exchanges.binance import BinancePrivateTranslationStatus
from app.exchanges.binance import BinancePrivateStreamClient
from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceSymbolMapping


def test_normal_fill_progression_translates_into_order_state_and_fill_event() -> None:
    translator = _translator()

    translated = translator.translate_order_execution_update(payload=_filled_trade_payload())

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.order_state is not None
    assert translated.order_state.status is OrderStatus.FILLED
    assert translated.order_state.instrument_id == "BTC-USDT"
    assert translated.order_state.filled_quantity == Decimal("2")
    assert translated.order_state.remaining_quantity == Decimal("0")
    assert translated.fill_event is not None
    assert translated.fill_event.fill_id == "777:9001"
    assert translated.fill_event.quantity == Decimal("2")
    assert translated.fill_event.liquidity_role is LiquidityRole.TAKER


def test_partial_fill_progression_keeps_non_terminal_order_state() -> None:
    translator = _translator()

    translated = translator.translate_order_execution_update(payload=_partial_trade_payload())

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.order_state is not None
    assert translated.order_state.status is OrderStatus.PARTIALLY_FILLED
    assert translated.order_state.filled_quantity == Decimal("0.4")
    assert translated.order_state.remaining_quantity == Decimal("0.6")
    assert translated.fill_event is not None
    assert translated.fill_event.quantity == Decimal("0.1")
    assert translated.fill_event.price == Decimal("101500")


def test_execution_report_without_expiry_reason_translates_normally() -> None:
    translator = _translator()

    translated = translator.translate_order_execution_update(payload=_filled_trade_payload())

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.order_state is not None
    assert translated.order_state.status is OrderStatus.FILLED
    assert translated.alerts == ()


def test_execution_report_with_expiry_reason_fields_is_tolerated_and_ignored() -> None:
    translator = _translator()
    payload = {
        **_expired_payload(),
        "eR": "2",
        "expiryReason": "MARKET_ORDER_EXPIRED",
    }

    translated = translator.translate_order_execution_update(payload=payload)

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.order_state is not None
    assert translated.order_state.status is OrderStatus.EXPIRED
    assert translated.fill_event is None
    assert translated.alerts == ()


def test_execution_report_with_unexpected_extra_fields_remains_non_crashing() -> None:
    translator = _translator()
    payload = {
        **_partial_trade_payload(),
        "foo": "bar",
        "nested": {"surprise": True},
        "listValue": [1, 2, 3],
    }

    translated = translator.translate_order_execution_update(payload=payload)

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.order_state is not None
    assert translated.order_state.status is OrderStatus.PARTIALLY_FILLED
    assert translated.fill_event is not None


def test_duplicate_trade_payloads_produce_deterministic_fill_ids() -> None:
    translator = _translator()
    client = _client()
    payload = _partial_trade_payload()

    first = translator.translate_order_execution_update(payload=payload)
    second = client.translate_payloads(payloads=(payload, payload), translator=translator)

    assert first.fill_event is not None
    assert second[0].fill_event is not None
    assert second[1].fill_event is not None
    assert first.fill_event.fill_id == second[0].fill_event.fill_id
    assert second[0].fill_event.fill_id == second[1].fill_event.fill_id


def test_account_and_balance_updates_translate_into_canonical_account_snapshots() -> None:
    translator = _translator()

    account_update = translator.translate_balance_account_update(payload=_account_update_payload())
    balance_update = translator.translate_balance_account_update(payload=_balance_update_payload())

    assert account_update.account_snapshot is not None
    assert account_update.account_snapshot.is_partial is False
    assert account_update.account_snapshot.balances[0].asset == "USDT"
    assert account_update.account_snapshot.balances[0].free == Decimal("1000")
    assert balance_update.account_snapshot is not None
    assert balance_update.account_snapshot.is_partial is True
    assert balance_update.account_snapshot.balances[0].delta == Decimal("-12.5")


def test_malformed_payload_handling_is_explicit_and_non_translating() -> None:
    translator = _translator()

    malformed = translator.translate_order_execution_update(
        payload={
            "e": "executionReport",
            "E": 1773360000000,
            "s": "BTCUSDT",
            "c": "client-1",
            "S": "BUY",
        }
    )

    assert malformed.status is BinancePrivateTranslationStatus.MALFORMED
    assert malformed.order_state is None
    assert malformed.fill_event is None
    assert "missing required executionReport fields" in malformed.alerts[0]


def test_stream_invalidation_translation_stays_operator_visible() -> None:
    translator = _translator()

    translated = translator.translate_stream_status(payload=_terminated_payload())

    assert translated.status is BinancePrivateTranslationStatus.TRANSLATED
    assert translated.stream_invalidated is True
    assert "listenKeyExpired" in translated.alerts[0]


def _translator() -> BinancePrivatePayloadTranslator:
    return BinancePrivatePayloadTranslator(
        symbol_mappings=(BinanceSymbolMapping(instrument_id="BTC-USDT", venue_symbol="BTCUSDT"),),
    )


def _client() -> BinancePrivateStreamClient:
    return BinancePrivateStreamClient(
        config=BinanceAdapterConfig(
            rest_base_url="https://api.binance.com",
            websocket_base_url="wss://stream.binance.com:9443",
        )
    )


def _filled_trade_payload() -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360000000,
        "s": "BTCUSDT",
        "c": "client-777",
        "S": "BUY",
        "o": "MARKET",
        "X": "FILLED",
        "x": "TRADE",
        "q": "2",
        "z": "2",
        "l": "2",
        "L": "101000",
        "Z": "202000",
        "n": "1.5",
        "N": "USDT",
        "i": 777,
        "t": 9001,
        "m": False,
    }


def _partial_trade_payload() -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360005000,
        "s": "BTCUSDT",
        "c": "client-888",
        "S": "BUY",
        "o": "LIMIT",
        "X": "PARTIALLY_FILLED",
        "x": "TRADE",
        "q": "1.0",
        "z": "0.4",
        "l": "0.1",
        "L": "101500",
        "Z": "40600",
        "n": "0.05",
        "N": "USDT",
        "i": 888,
        "t": 9002,
        "p": "101500",
        "m": True,
    }


def _account_update_payload() -> dict[str, object]:
    return {
        "e": "outboundAccountPosition",
        "E": 1773360010000,
        "B": [
            {"a": "USDT", "f": "1000", "l": "25"},
            {"a": "BTC", "f": "0.25", "l": "0"},
        ],
    }


def _expired_payload() -> dict[str, object]:
    return {
        "e": "executionReport",
        "E": 1773360020000,
        "s": "BTCUSDT",
        "c": "client-expired-1",
        "S": "SELL",
        "o": "LIMIT",
        "X": "EXPIRED",
        "x": "EXPIRED",
        "q": "0.5",
        "z": "0",
        "l": "0",
        "L": "0",
        "Z": "0",
        "i": 999,
        "p": "102000",
        "m": False,
    }


def _balance_update_payload() -> dict[str, object]:
    return {
        "e": "balanceUpdate",
        "E": 1773360015000,
        "a": "USDT",
        "d": "-12.5",
    }


def _terminated_payload() -> dict[str, object]:
    return {
        "e": "listenKeyExpired",
        "E": int(datetime(2026, 3, 13, 0, 0, tzinfo=UTC).timestamp() * 1000),
    }
