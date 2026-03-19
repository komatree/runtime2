"""Binance order submission skeleton."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen
from typing import Callable
from typing import Protocol

from app.contracts import ExecutionIntent
from app.contracts import FillEvent
from app.contracts import LiquidityRole
from app.contracts import OrderSide
from app.contracts import OrderState
from app.contracts import OrderStatus
from app.contracts import OrderType

from .clock_sync import BinanceClockSync
from .endpoint_profiles import validate_endpoint_profile
from .models import BinanceAdapterConfig
from .models import BinanceClientError
from .models import BinanceErrorCategory
from .models import BinanceOrderLookupResult
from .models import BinanceRecoveryAction
from .models import BinanceRecoveryPlan
from .models import BinanceStatusQueryHealth
from .models import BinanceStatusQueryState
from .private_payload_translator import infer_binance_instrument_id
from .throttling import BinanceRequestWeightTracker


class BinanceOrderStatusLookupTransport(Protocol):
    """Signed REST lookup boundary for Binance order status recovery."""

    def lookup_by_client_order_id(self, *, client_order_id: str) -> BinanceOrderLookupResult:
        """Return canonical lookup result by client order id."""

    def lookup_by_exchange_order_id(self, *, exchange_order_id: str) -> BinanceOrderLookupResult:
        """Return canonical lookup result by exchange order id."""

    def last_health(self) -> BinanceStatusQueryHealth | None:
        """Return the latest operator-visible status query health."""


@dataclass
class BinanceSignedRestOrderStatusTransport:
    """Signed REST transport for Binance order-status recovery.

    This transport keeps signing, headers, and response parsing inside the
    adapter boundary. It returns canonical lookup results only.
    """

    config: BinanceAdapterConfig
    venue_symbol: str
    time_provider: Callable[[], int]
    urlopen_fn: object = urlopen
    request_weight_tracker: BinanceRequestWeightTracker | None = None
    request_weight_cost: int = 4

    def __post_init__(self) -> None:
        validate_endpoint_profile(self.config)
        self._last_health: BinanceStatusQueryHealth | None = None

    def lookup_by_client_order_id(self, *, client_order_id: str) -> BinanceOrderLookupResult:
        return self._perform_lookup(
            lookup_field="client_order_id",
            lookup_value=client_order_id,
            query={"symbol": self.venue_symbol, "origClientOrderId": client_order_id},
        )

    def lookup_by_exchange_order_id(self, *, exchange_order_id: str) -> BinanceOrderLookupResult:
        return self._perform_lookup(
            lookup_field="exchange_order_id",
            lookup_value=exchange_order_id,
            query={"symbol": self.venue_symbol, "orderId": exchange_order_id},
        )

    def last_health(self) -> BinanceStatusQueryHealth | None:
        return self._last_health

    def _perform_lookup(
        self,
        *,
        lookup_field: str,
        lookup_value: str,
        query: dict[str, str],
    ) -> BinanceOrderLookupResult:
        checked_at = datetime.now(UTC)
        weight_snapshot = None
        if self.request_weight_tracker is not None:
            weight_snapshot = self.request_weight_tracker.consume(
                endpoint="/api/v3/order",
                weight=self.request_weight_cost,
                occurred_at=checked_at,
            )
            if weight_snapshot.is_throttled:
                self._last_health = BinanceStatusQueryHealth(
                    lookup_field=lookup_field,
                    lookup_value=lookup_value,
                    state=BinanceStatusQueryState.BLOCKED,
                    checked_at=checked_at,
                    transport="signed_rest_order_lookup",
                    alert=weight_snapshot.alert,
                    request_weight_used=weight_snapshot.used_weight,
                    request_weight_limit=weight_snapshot.max_weight,
                    endpoint_profile_name=self.config.endpoint_profile_name,
                )
                return BinanceOrderLookupResult(
                    found=False,
                    lookup_field=lookup_field,
                    lookup_value=lookup_value,
                    source="signed_rest_order_lookup",
                    status_summary=None,
                    alert=weight_snapshot.alert,
                )
        timestamp_ms = int(self.time_provider())
        signed_query = {
            **query,
            "timestamp": str(timestamp_ms),
            "recvWindow": str(self.config.recv_window_ms),
        }
        query_string = urlencode(signed_query)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            url=f"{self.config.rest_base_url.rstrip('/')}/api/v3/order?{query_string}&signature={signature}",
            method="GET",
            headers={"X-MBX-APIKEY": self.config.api_key},
        )
        try:
            with self.urlopen_fn(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
                http_status = getattr(response, "status", None)
                headers = _response_headers(response)
        except Exception as exc:
            self._last_health = BinanceStatusQueryHealth(
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                state=BinanceStatusQueryState.FAILED,
                checked_at=checked_at,
                transport="signed_rest_order_lookup",
                alert=str(exc),
                request_weight_used=(
                    weight_snapshot.used_weight if weight_snapshot is not None else None
                ),
                request_weight_limit=(
                    weight_snapshot.max_weight if weight_snapshot is not None else None
                ),
                endpoint_profile_name=self.config.endpoint_profile_name,
            )
            return BinanceOrderLookupResult(
                found=False,
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                source="signed_rest_order_lookup",
                status_summary=None,
                alert=str(exc),
            )

        if self.request_weight_tracker is not None:
            observed_snapshot = self.request_weight_tracker.observe_response_headers(
                headers=headers,
                endpoint="/api/v3/order",
                occurred_at=checked_at,
            )
            if observed_snapshot is not None:
                weight_snapshot = observed_snapshot
        if not isinstance(payload, dict):
            self._last_health = BinanceStatusQueryHealth(
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                state=BinanceStatusQueryState.FAILED,
                checked_at=checked_at,
                transport="signed_rest_order_lookup",
                http_status=http_status,
                alert="non-object lookup payload",
                request_weight_used=(
                    weight_snapshot.used_weight if weight_snapshot is not None else None
                ),
                request_weight_limit=(
                    weight_snapshot.max_weight if weight_snapshot is not None else None
                ),
                endpoint_profile_name=self.config.endpoint_profile_name,
            )
            return BinanceOrderLookupResult(
                found=False,
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                source="signed_rest_order_lookup",
                status_summary=None,
                alert="non-object lookup payload",
            )
        if "code" in payload and "msg" in payload and payload.get("status") is None:
            alert = f"binance lookup error {payload.get('code')}: {payload.get('msg')}"
            self._last_health = BinanceStatusQueryHealth(
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                state=BinanceStatusQueryState.FAILED,
                checked_at=checked_at,
                transport="signed_rest_order_lookup",
                http_status=http_status,
                alert=alert,
                request_weight_used=(
                    weight_snapshot.used_weight if weight_snapshot is not None else None
                ),
                request_weight_limit=(
                    weight_snapshot.max_weight if weight_snapshot is not None else None
                ),
                endpoint_profile_name=self.config.endpoint_profile_name,
            )
            return BinanceOrderLookupResult(
                found=False,
                lookup_field=lookup_field,
                lookup_value=lookup_value,
                source="signed_rest_order_lookup",
                status_summary=None,
                alert=alert,
            )
        status_summary = self._normalize_status(str(payload.get("status", "")))
        found = bool(payload) and payload.get("orderId") is not None
        recovered_order_state = (
            self._build_recovered_order_state(payload=payload, checked_at=checked_at)
            if found
            else None
        )
        recovered_fill_events = (
            self._build_recovered_fill_events(
                payload=payload,
                order_state=recovered_order_state,
                checked_at=checked_at,
            )
            if recovered_order_state is not None
            else ()
        )
        self._last_health = BinanceStatusQueryHealth(
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            state=BinanceStatusQueryState.SUCCESS if found else BinanceStatusQueryState.FAILED,
            checked_at=checked_at,
            transport="signed_rest_order_lookup",
            http_status=http_status,
            alert=None if found else "empty lookup payload",
            request_weight_used=(
                weight_snapshot.used_weight if weight_snapshot is not None else None
            ),
            request_weight_limit=(
                weight_snapshot.max_weight if weight_snapshot is not None else None
            ),
            endpoint_profile_name=self.config.endpoint_profile_name,
        )
        return BinanceOrderLookupResult(
            found=found,
            lookup_field=lookup_field,
            lookup_value=lookup_value,
            source="signed_rest_order_lookup",
            status_summary=status_summary if found else None,
            alert=None if found else "empty lookup payload",
            recovered_order_state=recovered_order_state,
            recovered_fill_events=recovered_fill_events,
        )

    def _normalize_status(self, value: str) -> str:
        mapping = {
            "NEW": "acknowledged",
            "PARTIALLY_FILLED": "partially_filled",
            "FILLED": "filled",
            "CANCELED": "cancelled",
            "CANCELLED": "cancelled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }
        if value not in mapping:
            return value.lower() if value else "unknown"
        return mapping[value]

    def _build_recovered_order_state(
        self,
        *,
        payload: dict[str, object],
        checked_at: datetime,
    ) -> OrderState | None:
        try:
            venue_symbol = str(payload["symbol"])
            instrument_id = infer_binance_instrument_id(venue_symbol)
            side = self._map_side(str(payload["side"]))
            order_type = self._map_order_type(str(payload["type"]))
            status = self._map_status(str(payload["status"]))
            requested_quantity = Decimal(str(payload["origQty"]))
            filled_quantity = Decimal(str(payload["executedQty"]))
            remaining_quantity = requested_quantity - filled_quantity
            price = self._parse_optional_decimal(payload.get("price"))
            limit_price = None if price in (None, Decimal("0")) else price
            cumulative_quote_quantity = self._parse_optional_decimal(payload.get("cummulativeQuoteQty"))
            average_fill_price = None
            if filled_quantity > Decimal("0") and cumulative_quote_quantity is not None:
                average_fill_price = cumulative_quote_quantity / filled_quantity
            updated_at = self._parse_event_time(payload.get("updateTime")) or checked_at
            return OrderState(
                venue="binance",
                order_id=str(payload.get("orderId") or payload.get("origClientOrderId")),
                client_order_id=str(payload.get("origClientOrderId") or payload.get("orderId")),
                instrument_id=instrument_id,
                side=side,
                order_type=order_type,
                status=status,
                requested_quantity=requested_quantity,
                filled_quantity=filled_quantity,
                remaining_quantity=remaining_quantity,
                last_update_time=updated_at,
                limit_price=limit_price,
                average_fill_price=average_fill_price,
            )
        except (ArithmeticError, KeyError, TypeError, ValueError):
            return None

    def _build_recovered_fill_events(
        self,
        *,
        payload: dict[str, object],
        order_state: OrderState,
        checked_at: datetime,
    ) -> tuple[FillEvent, ...]:
        if order_state.status is not OrderStatus.FILLED:
            return ()
        if order_state.filled_quantity <= Decimal("0"):
            return ()
        fill_price = order_state.average_fill_price
        if fill_price is None or fill_price <= Decimal("0"):
            return ()
        occurred_at = self._parse_event_time(payload.get("updateTime")) or checked_at
        fee_asset = order_state.instrument_id.split("-")[-1]
        trade_id = payload.get("orderId")
        fill_id = f"{order_state.order_id}:recovered:{trade_id}"
        return (
            FillEvent(
                venue="binance",
                order_id=order_state.order_id,
                fill_id=fill_id,
                instrument_id=order_state.instrument_id,
                side=order_state.side,
                quantity=order_state.filled_quantity,
                price=fill_price,
                fee=Decimal("0"),
                fee_asset=fee_asset,
                occurred_at=occurred_at,
                liquidity_role=LiquidityRole.UNKNOWN,
            ),
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

    def _map_status(self, value: str) -> OrderStatus:
        mapping = {
            "NEW": OrderStatus.NEW,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELED,
            "CANCELLED": OrderStatus.CANCELED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        if value not in mapping:
            raise ValueError(f"unsupported order status: {value}")
        return mapping[value]

    def _parse_optional_decimal(self, raw_value: object) -> Decimal | None:
        if raw_value in (None, ""):
            return None
        return Decimal(str(raw_value))

    def _parse_event_time(self, raw_value: object) -> datetime | None:
        try:
            if raw_value in (None, ""):
                return None
            return datetime.fromtimestamp(int(raw_value) / 1000, tz=UTC)
        except (TypeError, ValueError):
            return None


def _response_headers(response: object) -> Mapping[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key): str(value) for key, value in headers.items()}
    return {}


@dataclass(frozen=True)
class BinanceOrderClient:
    """Stub for order submission and cancel/amend responsibilities.

    Responsibilities:
    - validate order-intent readiness for Binance submission
    - enforce clock-sync safety before signed requests
    - own error classification hooks for rejects and transport failures

    Pre-live blockers:
    - signed REST submission is not implemented
    - cancel/replace semantics are not implemented
    - idempotency and retry policy are not implemented
    - client-id and exchange-id status lookup transport is not implemented
    """

    config: BinanceAdapterConfig
    clock_sync: BinanceClockSync

    def can_submit_orders(self) -> bool:
        """Return whether this adapter is allowed to submit real orders."""

        return self.config.allow_order_submission

    def validate_submission_readiness(self, intent: ExecutionIntent) -> BinanceClientError | None:
        """Validate the minimal preconditions for future live order submission."""

        if not self.config.allow_order_submission:
            return BinanceClientError(
                category=BinanceErrorCategory.UNKNOWN,
                message="order submission disabled by configuration",
                retryable=False,
            )
        clock_status = self.clock_sync.check()
        if not clock_status.is_within_tolerance:
            return BinanceClientError(
                category=BinanceErrorCategory.CLOCK_SKEW,
                message="clock skew outside configured tolerance",
                retryable=True,
            )
        if intent.venue != "binance":
            return BinanceClientError(
                category=BinanceErrorCategory.ORDER_REJECT,
                message="execution intent venue does not match binance",
                retryable=False,
            )
        return None

    def lookup_order_by_client_id(
        self,
        client_order_id: str,
        *,
        transport: BinanceOrderStatusLookupTransport | None = None,
    ) -> BinanceOrderLookupResult:
        """Lookup order status by client id using signed transport when available."""

        if transport is None:
            return BinanceOrderLookupResult(
                found=False,
                lookup_field="client_order_id",
                lookup_value=client_order_id,
                source="order_client_placeholder",
                status_summary=None,
                alert="client-order-id lookup transport not implemented",
            )
        return transport.lookup_by_client_order_id(client_order_id=client_order_id)

    def lookup_order_by_exchange_id(
        self,
        exchange_order_id: str,
        *,
        transport: BinanceOrderStatusLookupTransport | None = None,
    ) -> BinanceOrderLookupResult:
        """Lookup order status by exchange id using signed transport when available."""

        if transport is None:
            return BinanceOrderLookupResult(
                found=False,
                lookup_field="exchange_order_id",
                lookup_value=exchange_order_id,
                source="order_client_placeholder",
                status_summary=None,
                alert="exchange-order-id lookup transport not implemented",
            )
        return transport.lookup_by_exchange_order_id(exchange_order_id=exchange_order_id)

    def plan_unknown_execution_recovery(
        self,
        *,
        client_order_id: str | None = None,
        exchange_order_id: str | None = None,
    ) -> BinanceRecoveryPlan:
        """Return a conservative placeholder recovery plan for unknown execution."""

        lookup_requests: list[tuple[str, str]] = []
        if client_order_id:
            lookup_requests.append(("client_order_id", client_order_id))
        if exchange_order_id:
            lookup_requests.append(("exchange_order_id", exchange_order_id))
        if not lookup_requests:
            lookup_requests.append(("open_orders", "all"))
        return BinanceRecoveryPlan(
            reason="unknown execution requires order-status recovery",
            actions=(
                BinanceRecoveryAction.QUERY_ORDER_STATUS,
                BinanceRecoveryAction.HOLD_PORTFOLIO_MUTATION,
                BinanceRecoveryAction.ESCALATE_OPERATOR,
            ),
            order_lookup_requests=tuple(lookup_requests),
            alerts=("unknown execution recovery is scaffolded only; no transport implemented",),
        )
