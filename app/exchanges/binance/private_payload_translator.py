"""Canonical Binance private payload translator.

The translator is the authoritative bridge from Binance-native authenticated
payloads into internal runtime2 models. Raw Binance field names must not cross
this boundary into strategy, risk, or portfolio-facing code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal

from app.contracts import AccountSnapshot
from app.contracts import AssetBalanceSnapshot
from app.contracts import FillEvent
from app.contracts import LiquidityRole
from app.contracts import OrderSide
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import OrderType

from .models import BinancePrivateEventFamily
from .models import BinancePrivatePayloadTranslation
from .models import BinancePrivateTranslationStatus
from .models import BinanceSymbolMapping


def infer_binance_instrument_id(
    venue_symbol: str,
    *,
    symbol_mappings: tuple[BinanceSymbolMapping, ...] = (),
) -> str:
    """Return canonical instrument id for one Binance venue symbol."""

    for mapping in symbol_mappings:
        if mapping.venue_symbol == venue_symbol:
            return mapping.instrument_id
    known_quotes = ("USDT", "USDC", "BTC", "ETH", "BNB", "KRW", "USD")
    for quote in known_quotes:
        if venue_symbol.endswith(quote) and len(venue_symbol) > len(quote):
            return f"{venue_symbol[:-len(quote)]}-{quote}"
    raise ValueError(f"unable to infer instrument_id for symbol: {venue_symbol}")


@dataclass(frozen=True)
class BinancePrivatePayloadTranslator:
    """Translate Binance private payloads into canonical runtime contracts.

    Design rules:
    - use explicit field mapping, not implicit exchange-shape propagation
    - fail malformed payloads visibly with operator-readable alerts
    - keep deterministic fill ids so downstream deduplication remains inspectable
    """

    translation_version: str = "binance.private.v1"
    venue: str = "binance"
    account_scope: str = "spot"
    symbol_mappings: tuple[BinanceSymbolMapping, ...] = ()

    def translate_payload(self, *, payload: dict[str, object]) -> BinancePrivatePayloadTranslation:
        """Translate one raw Binance private payload into canonical models."""

        event_type = str(payload.get("e", ""))
        if event_type == "executionReport":
            return self.translate_order_execution_update(payload=payload)
        if event_type in {"outboundAccountPosition", "balanceUpdate"}:
            return self.translate_balance_account_update(payload=payload)
        if event_type in {"listenKeyExpired", "eventStreamTerminated"}:
            return self.translate_stream_status(payload=payload)
        return BinancePrivatePayloadTranslation(
            translation_version=self.translation_version,
            status=BinancePrivateTranslationStatus.IGNORED,
            source_event_type=event_type or "unknown",
            event_family=BinancePrivateEventFamily.STREAM_STATUS,
            occurred_at=self._parse_event_time(payload.get("E")),
            alerts=(f"unsupported private payload type: {event_type or 'unknown'}",),
        )

    def translate_payloads(
        self,
        *,
        payloads: tuple[dict[str, object], ...],
    ) -> tuple[BinancePrivatePayloadTranslation, ...]:
        """Translate a batch of raw Binance private payloads."""

        return tuple(self.translate_payload(payload=payload) for payload in payloads)

    def translate_order_execution_update(
        self,
        *,
        payload: dict[str, object],
    ) -> BinancePrivatePayloadTranslation:
        """Translate order/execution payloads into `OrderState` and optional `FillEvent`."""

        event_time = self._parse_event_time(payload.get("E"))
        if event_time is None:
            return self._malformed(
                source_event_type="executionReport",
                event_family=BinancePrivateEventFamily.ORDER_UPDATE,
                message="missing or invalid event time",
            )

        required = ("s", "S", "o", "X", "q", "z", "c")
        missing = tuple(name for name in required if payload.get(name) in (None, ""))
        if missing:
            return self._malformed(
                source_event_type="executionReport",
                event_family=BinancePrivateEventFamily.ORDER_UPDATE,
                occurred_at=event_time,
                message=f"missing required executionReport fields: {','.join(missing)}",
            )

        try:
            instrument_id = self._to_instrument_id(str(payload["s"]))
            side = self._map_side(str(payload["S"]))
            order_type = self._map_order_type(str(payload["o"]))
            status = self._map_order_status(str(payload["X"]))
            requested_quantity = Decimal(str(payload["q"]))
            filled_quantity = Decimal(str(payload["z"]))
            remaining_quantity = requested_quantity - filled_quantity
            average_fill_price = self._parse_optional_decimal(payload.get("Z"))
            if average_fill_price is not None and filled_quantity > Decimal("0"):
                average_fill_price = average_fill_price / filled_quantity
            elif payload.get("ap") not in (None, ""):
                average_fill_price = Decimal(str(payload["ap"]))
            limit_price = self._parse_optional_decimal(payload.get("p"))
            if limit_price == Decimal("0"):
                limit_price = None
            order_id = str(payload.get("i") or payload["c"])
            client_order_id = str(payload["c"])
            order_state = OrderState(
                venue=self.venue,
                order_id=order_id,
                client_order_id=client_order_id,
                instrument_id=instrument_id,
                side=side,
                order_type=order_type,
                status=status,
                requested_quantity=requested_quantity,
                filled_quantity=filled_quantity,
                remaining_quantity=remaining_quantity,
                last_update_time=event_time,
                limit_price=limit_price,
                average_fill_price=average_fill_price,
            )
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            return self._malformed(
                source_event_type="executionReport",
                event_family=BinancePrivateEventFamily.ORDER_UPDATE,
                occurred_at=event_time,
                message=f"invalid executionReport payload: {exc}",
            )

        fill_event = self._build_fill_event(
            payload=payload,
            order_state=order_state,
            event_time=event_time,
        )
        alerts: list[str] = []
        if fill_event is None and str(payload.get("x", "")) == "TRADE":
            alerts.append("trade execution payload did not yield a valid fill event")

        return BinancePrivatePayloadTranslation(
            translation_version=self.translation_version,
            status=BinancePrivateTranslationStatus.TRANSLATED,
            source_event_type="executionReport",
            event_family=BinancePrivateEventFamily.ORDER_UPDATE,
            occurred_at=event_time,
            order_state=order_state,
            fill_event=fill_event,
            alerts=tuple(alerts),
        )

    def translate_balance_account_update(
        self,
        *,
        payload: dict[str, object],
    ) -> BinancePrivatePayloadTranslation:
        """Translate account/balance payloads into canonical `AccountSnapshot`."""

        event_type = str(payload.get("e", "unknown"))
        event_time = self._parse_event_time(payload.get("E"))
        if event_time is None:
            return self._malformed(
                source_event_type=event_type,
                event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
                message="missing or invalid account event time",
            )

        try:
            if event_type == "outboundAccountPosition":
                balances = payload.get("B")
                if not isinstance(balances, list) or not balances:
                    raise ValueError("account update balances must be a non-empty list")
                snapshot_balances = tuple(
                    AssetBalanceSnapshot(
                        asset=str(balance["a"]),
                        free=Decimal(str(balance["f"])),
                        locked=Decimal(str(balance["l"])),
                        updated_at=event_time,
                    )
                    for balance in balances
                    if isinstance(balance, dict)
                )
                if not snapshot_balances:
                    raise ValueError("account update contains no valid balances")
                account_snapshot = AccountSnapshot(
                    venue=self.venue,
                    account_scope=self.account_scope,
                    as_of=event_time,
                    balances=snapshot_balances,
                    source_event_type=event_type,
                    translation_version=self.translation_version,
                    is_partial=False,
                )
            elif event_type == "balanceUpdate":
                asset = str(payload["a"])
                delta = Decimal(str(payload["d"]))
                account_snapshot = AccountSnapshot(
                    venue=self.venue,
                    account_scope=self.account_scope,
                    as_of=event_time,
                    balances=(
                        AssetBalanceSnapshot(
                            asset=asset,
                            delta=delta,
                            updated_at=event_time,
                        ),
                    ),
                    source_event_type=event_type,
                    translation_version=self.translation_version,
                    is_partial=True,
                )
            else:
                return self._malformed(
                    source_event_type=event_type,
                    event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
                    occurred_at=event_time,
                    message=f"unsupported account payload type: {event_type}",
                )
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            return self._malformed(
                source_event_type=event_type,
                event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
                occurred_at=event_time,
                message=f"invalid {event_type} payload: {exc}",
            )

        return BinancePrivatePayloadTranslation(
            translation_version=self.translation_version,
            status=BinancePrivateTranslationStatus.TRANSLATED,
            source_event_type=event_type,
            event_family=BinancePrivateEventFamily.ACCOUNT_UPDATE,
            occurred_at=event_time,
            account_snapshot=account_snapshot,
        )

    def translate_stream_status(
        self,
        *,
        payload: dict[str, object],
    ) -> BinancePrivatePayloadTranslation:
        """Translate stream invalidation signals into operator-visible internal state."""

        event_type = str(payload.get("e", "unknown"))
        event_time = self._parse_event_time(payload.get("E"))
        return BinancePrivatePayloadTranslation(
            translation_version=self.translation_version,
            status=BinancePrivateTranslationStatus.TRANSLATED,
            source_event_type=event_type,
            event_family=BinancePrivateEventFamily.STREAM_STATUS,
            occurred_at=event_time,
            stream_invalidated=True,
            alerts=(f"private stream invalidated by {event_type}",),
        )

    def _build_fill_event(
        self,
        *,
        payload: dict[str, object],
        order_state: OrderState,
        event_time: datetime,
    ) -> FillEvent | None:
        execution_type = str(payload.get("x", ""))
        last_quantity = self._parse_optional_decimal(payload.get("l"))
        if execution_type != "TRADE" or last_quantity is None or last_quantity <= Decimal("0"):
            return None
        last_price = self._parse_optional_decimal(payload.get("L"))
        if last_price is None or last_price <= Decimal("0"):
            return None
        fee = self._parse_optional_decimal(payload.get("n")) or Decimal("0")
        fee_asset = str(payload.get("N") or order_state.instrument_id.split("-")[-1])
        trade_id = payload.get("t")
        fill_id = (
            f"{order_state.order_id}:{trade_id}"
            if trade_id not in (None, "", -1)
            else f"{order_state.order_id}:{int(event_time.timestamp() * 1000)}:{last_quantity}:{last_price}"
        )
        liquidity_role = LiquidityRole.MAKER if bool(payload.get("m")) else LiquidityRole.TAKER
        return FillEvent(
            venue=self.venue,
            order_id=order_state.order_id,
            fill_id=fill_id,
            instrument_id=order_state.instrument_id,
            side=order_state.side,
            quantity=last_quantity,
            price=last_price,
            fee=fee,
            fee_asset=fee_asset,
            occurred_at=event_time,
            liquidity_role=liquidity_role,
        )

    def _map_side(self, value: str) -> OrderSide:
        mapping = {
            "BUY": OrderSide.BUY,
            "SELL": OrderSide.SELL,
        }
        if value not in mapping:
            raise ValueError(f"unsupported order side: {value}")
        return mapping[value]

    def _map_order_type(self, value: str) -> OrderType:
        mapping = {
            "MARKET": OrderType.MARKET,
            "LIMIT": OrderType.LIMIT,
        }
        if value not in mapping:
            raise ValueError(f"unsupported order type: {value}")
        return mapping[value]

    def _map_order_status(self, value: str) -> OrderStatus:
        mapping = {
            "NEW": OrderStatus.NEW,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELED,
            "CANCELLED": OrderStatus.CANCELED,
            "EXPIRED": OrderStatus.EXPIRED,
            "REJECTED": OrderStatus.REJECTED,
        }
        if value not in mapping:
            raise ValueError(f"unsupported order status: {value}")
        return mapping[value]

    def _to_instrument_id(self, venue_symbol: str) -> str:
        return infer_binance_instrument_id(
            venue_symbol,
            symbol_mappings=self.symbol_mappings,
        )

    def _parse_event_time(self, raw_value: object) -> datetime | None:
        try:
            if raw_value in (None, ""):
                return None
            return datetime.fromtimestamp(int(raw_value) / 1000, tz=UTC)
        except (TypeError, ValueError):
            return None

    def _parse_optional_decimal(self, raw_value: object) -> Decimal | None:
        if raw_value in (None, ""):
            return None
        return Decimal(str(raw_value))

    def _malformed(
        self,
        *,
        source_event_type: str,
        event_family: BinancePrivateEventFamily,
        message: str,
        occurred_at: datetime | None = None,
    ) -> BinancePrivatePayloadTranslation:
        return BinancePrivatePayloadTranslation(
            translation_version=self.translation_version,
            status=BinancePrivateTranslationStatus.MALFORMED,
            source_event_type=source_event_type,
            event_family=event_family,
            occurred_at=occurred_at,
            alerts=(message,),
        )
