#!/usr/bin/env python3
"""Generate bounded Binance Spot testnet private-event actions with evidence artifacts.

This helper is intentionally narrow:
- Spot testnet only
- create + cancel are the mandatory core flow
- optional fill attempt is explicitly opt-in
- signed request logic stays local to this evidence harness
- secrets and raw private payloads are never written to artifacts
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import tomllib
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from decimal import ROUND_DOWN
from decimal import ROUND_UP
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.exchanges.binance import BinanceAdapterConfig


@dataclass(frozen=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal | None


@dataclass(frozen=True)
class ActionDriverEvent:
    timestamp: str
    action_type: str
    symbol: str
    side: str
    order_type: str
    qty: str
    exchange_response_class: str
    success: bool
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    price: str | None = None
    http_status: int | None = None
    detail: str | None = None


SUCCESS = "SUCCESS"
PARTIAL_SUCCESS_NONBLOCKING = "PARTIAL_SUCCESS_NONBLOCKING"
FATAL_FAILURE = "FATAL_FAILURE"


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _mask(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def _build_client_order_id(*, run_id: str, action_suffix: str) -> str:
    """Return a Binance-safe client order id.

    Binance Spot requires `newClientOrderId` to match `^[a-zA-Z0-9-_]{1,36}$`.
    Keep ids short, deterministic, and still reviewable enough to correlate
    create / cancel / fill actions within one run.
    """

    sanitized = "".join(char if char.isalnum() or char in "-_" else "-" for char in run_id)
    digest = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:8]
    prefix_budget = 36 - len(action_suffix) - len(digest) - 2
    prefix = sanitized[:prefix_budget].strip("-_") or "rt2"
    return f"{prefix}-{digest}-{action_suffix}"


def _quantize(value: Decimal, step: Decimal, *, rounding: str) -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


def _request_json(
    *,
    request: Request,
    urlopen_fn: object = urlopen,
) -> tuple[dict[str, Any] | list[Any], int | None]:
    try:
        with urlopen_fn(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, getattr(response, "status", None)
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = {"http_error_body": raw_body}
        return payload, exc.code


def _load_config(config_path: Path) -> BinanceAdapterConfig:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    binance = payload["binance"]
    return BinanceAdapterConfig(
        rest_base_url=str(binance["rest_base_url"]),
        websocket_base_url=str(binance["websocket_base_url"]),
        api_key=os.environ.get("BINANCE_API_KEY", ""),
        api_secret=os.environ.get("BINANCE_API_SECRET", ""),
        endpoint_profile_name=str(binance["endpoint_profile_name"]),
    )


def _validate_testnet_only(config: BinanceAdapterConfig) -> None:
    if config.endpoint_profile_name != "binance_spot_testnet":
        raise ValueError("action driver is testnet-only and requires endpoint_profile_name=binance_spot_testnet")
    if "testnet.binance.vision" not in config.rest_base_url:
        raise ValueError("action driver requires Binance Spot testnet REST host")
    if "testnet.binance.vision" not in config.websocket_base_url:
        raise ValueError("action driver requires Binance Spot testnet websocket host")


class BinanceSpotTestnetActionApi:
    """Small signed REST helper for evidence-only testnet order actions."""

    def __init__(
        self,
        *,
        config: BinanceAdapterConfig,
        urlopen_fn: object = urlopen,
        time_provider: callable | None = None,
    ) -> None:
        _validate_testnet_only(config)
        self._config = config
        self._urlopen_fn = urlopen_fn
        self._time_provider = time_provider or (lambda: int(datetime.now(UTC).timestamp() * 1000))

    def symbol_rules(self, symbol: str) -> SymbolRules:
        request = Request(
            url=f"{self._config.rest_base_url.rstrip('/')}/api/v3/exchangeInfo?symbol={symbol}",
            method="GET",
        )
        payload, _ = _request_json(request=request, urlopen_fn=self._urlopen_fn)
        if not isinstance(payload, dict):
            raise ValueError("non-object exchangeInfo payload")
        symbols = payload.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            raise ValueError(f"exchangeInfo did not return rules for {symbol}")
        symbol_payload = symbols[0]
        filters = {str(item.get("filterType")): item for item in symbol_payload.get("filters", []) if isinstance(item, dict)}
        lot = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})
        min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        return SymbolRules(
            symbol=symbol,
            tick_size=Decimal(str(price_filter.get("tickSize", "0.01"))),
            step_size=Decimal(str(lot.get("stepSize", "0.000001"))),
            min_qty=Decimal(str(lot.get("minQty", "0.000001"))),
            min_notional=(
                Decimal(str(min_notional_filter.get("minNotional")))
                if min_notional_filter.get("minNotional") is not None
                else None
            ),
        )

    def last_price(self, symbol: str) -> Decimal:
        request = Request(
            url=f"{self._config.rest_base_url.rstrip('/')}/api/v3/ticker/price?symbol={symbol}",
            method="GET",
        )
        payload, _ = _request_json(request=request, urlopen_fn=self._urlopen_fn)
        if not isinstance(payload, dict) or "price" not in payload:
            raise ValueError(f"ticker price unavailable for {symbol}")
        return Decimal(str(payload["price"]))

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        client_order_id: str,
    ) -> tuple[dict[str, Any] | list[Any], int | None]:
        query = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": _format_decimal(quantity),
            "price": _format_decimal(price),
            "newClientOrderId": client_order_id,
        }
        return self._signed_request(method="POST", path="/api/v3/order", query=query)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: str,
        client_order_id: str,
    ) -> tuple[dict[str, Any] | list[Any], int | None]:
        query = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": client_order_id,
        }
        return self._signed_request(method="DELETE", path="/api/v3/order", query=query)

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        client_order_id: str,
    ) -> tuple[dict[str, Any] | list[Any], int | None]:
        query = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": _format_decimal(quantity),
            "newClientOrderId": client_order_id,
        }
        return self._signed_request(method="POST", path="/api/v3/order", query=query)

    def _signed_request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str],
    ) -> tuple[dict[str, Any] | list[Any], int | None]:
        signed_query = {
            **query,
            "timestamp": str(int(self._time_provider())),
            "recvWindow": str(self._config.recv_window_ms),
        }
        query_string = urlencode(signed_query)
        signature = hmac.new(
            self._config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            url=f"{self._config.rest_base_url.rstrip('/')}{path}?{query_string}&signature={signature}",
            method=method,
            headers={"X-MBX-APIKEY": self._config.api_key},
        )
        return _request_json(request=request, urlopen_fn=self._urlopen_fn)


def _classify_response(payload: dict[str, Any] | list[Any], http_status: int | None) -> tuple[bool, str, str | None]:
    if isinstance(payload, dict) and "code" in payload and "msg" in payload and payload.get("orderId") is None:
        return (False, "failure", f"binance error {payload.get('code')}: {payload.get('msg')}")
    if isinstance(payload, dict) and payload.get("http_error_body"):
        return (False, "failure", f"http error body: {payload.get('http_error_body')}")
    if http_status is not None and http_status >= 400:
        return (False, "failure", f"http status {http_status}")
    return (True, "success", None)


def _compute_resting_quantity(
    *,
    requested_qty: Decimal | None,
    rules: SymbolRules,
    resting_price: Decimal,
    market_price: Decimal,
) -> Decimal:
    if requested_qty is not None:
        qty = _quantize(requested_qty, rules.step_size, rounding=ROUND_DOWN)
        if qty < rules.min_qty:
            raise ValueError("requested qty is below symbol minQty after step-size rounding")
        return qty

    qty = rules.min_qty
    if rules.min_notional is not None:
        required_notional = max(rules.min_notional, Decimal("5"))
        qty = max(
            qty,
            _quantize(required_notional / market_price, rules.step_size, rounding=ROUND_UP),
            _quantize(required_notional / resting_price, rules.step_size, rounding=ROUND_UP),
        )
    return _quantize(qty, rules.step_size, rounding=ROUND_UP)


def _build_resting_price(last_price: Decimal, tick_size: Decimal) -> Decimal:
    target = last_price * Decimal("0.50")
    price = _quantize(target, tick_size, rounding=ROUND_DOWN)
    if price <= 0:
        raise ValueError("computed resting price is non-positive")
    return price


def _write_events_jsonl(path: Path, events: list[ActionDriverEvent]) -> None:
    lines = [json.dumps(asdict(event), sort_keys=True) for event in events]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_summary_md(
    *,
    path: Path,
    run_id: str,
    config: BinanceAdapterConfig,
    symbol: str,
    qty: Decimal | None,
    fill_attempt_enabled: bool,
    events: list[ActionDriverEvent],
) -> None:
    success_count = sum(1 for event in events if event.success)
    failure_count = len(events) - success_count
    lines = [
        "# Testnet Event Action Driver Summary",
        "",
        f"- run_id: `{run_id}`",
        f"- endpoint_profile_name: `{config.endpoint_profile_name}`",
        f"- rest_base_url: `{config.rest_base_url}`",
        f"- masked_api_key: `{_mask(config.api_key)}`",
        f"- symbol: `{symbol}`",
        f"- requested_qty: `{_format_decimal(qty) if qty is not None else 'auto'}`",
        f"- fill_attempt_enabled: `{str(fill_attempt_enabled).lower()}`",
        f"- actions_recorded: `{len(events)}`",
        f"- successful_actions: `{success_count}`",
        f"- failed_actions: `{failure_count}`",
        "",
        "## Actions",
        "",
    ]
    for event in events:
        lines.extend(
            [
                f"### {event.action_type}",
                f"- timestamp: `{event.timestamp}`",
                f"- response_class: `{event.exchange_response_class}`",
                f"- success: `{str(event.success).lower()}`",
                f"- side: `{event.side}`",
                f"- order_type: `{event.order_type}`",
                f"- qty: `{event.qty}`",
                f"- price: `{event.price or 'n/a'}`",
                f"- client_order_id: `{event.client_order_id or 'n/a'}`",
                f"- exchange_order_id: `{event.exchange_order_id or 'n/a'}`",
                f"- detail: `{event.detail or 'none'}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _failure_reasons(events: list[ActionDriverEvent]) -> list[str]:
    reasons: list[str] = []
    for event in events:
        if event.success:
            continue
        reason = event.detail or event.exchange_response_class
        reasons.append(f"{event.action_type}: {reason}")
    return reasons


def _classify_window_outcome(
    *,
    create_leg_success: bool,
    cancel_leg_success: bool,
    fill_attempt_enabled: bool,
    fill_leg_success: bool,
) -> str:
    mandatory_success = create_leg_success and cancel_leg_success
    if mandatory_success:
        return SUCCESS
    if fill_attempt_enabled and fill_leg_success:
        return PARTIAL_SUCCESS_NONBLOCKING
    return FATAL_FAILURE


def _write_result_artifact(
    *,
    path: Path,
    run_id: str,
    window_outcome: str,
    mandatory_success: bool,
    fill_attempt_enabled: bool,
    events: list[ActionDriverEvent],
    create_leg_success: bool,
    cancel_leg_success: bool,
    fill_leg_success: bool,
) -> None:
    successful_actions = sum(1 for event in events if event.success)
    failed_actions = len(events) - successful_actions
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "window_outcome": window_outcome,
                "mandatory_success": mandatory_success,
                "fill_attempt_enabled": fill_attempt_enabled,
                "successful_actions": successful_actions,
                "failed_actions": failed_actions,
                "failure_reasons": _failure_reasons(events),
                "create_leg_success": create_leg_success,
                "cancel_leg_success": cancel_leg_success,
                "fill_leg_success": fill_leg_success,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def run_action_driver(
    args: argparse.Namespace,
    *,
    api: BinanceSpotTestnetActionApi | None = None,
) -> int:
    config = _load_config(args.config)
    _validate_testnet_only(config)
    if not config.api_key or not config.api_secret:
        raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set for the testnet action driver")

    action_dir = args.reports_dir / "event_exercises" / args.run_id / "action_driver"
    action_dir.mkdir(parents=True, exist_ok=True)
    events_path = action_dir / "action_driver_events.jsonl"
    summary_path = action_dir / "action_driver_summary.md"
    result_path = action_dir / "action_driver_result.json"

    resolved_api = api or BinanceSpotTestnetActionApi(config=config)
    requested_qty = Decimal(args.qty) if args.qty is not None else None
    rules = resolved_api.symbol_rules(args.symbol)
    market_price = resolved_api.last_price(args.symbol)
    resting_price = _build_resting_price(market_price, rules.tick_size)
    resting_qty = _compute_resting_quantity(
        requested_qty=requested_qty,
        rules=rules,
        resting_price=resting_price,
        market_price=market_price,
    )

    events: list[ActionDriverEvent] = []
    create_client_order_id = _build_client_order_id(run_id=args.run_id, action_suffix="c")
    create_payload, create_status = resolved_api.place_limit_order(
        symbol=args.symbol,
        side="BUY",
        quantity=resting_qty,
        price=resting_price,
        client_order_id=create_client_order_id,
    )
    create_success, create_class, create_detail = _classify_response(create_payload, create_status)
    create_order_id = str(create_payload.get("orderId")) if isinstance(create_payload, dict) and create_payload.get("orderId") is not None else None
    events.append(
        ActionDriverEvent(
            timestamp=datetime.now(UTC).isoformat(),
            action_type="place_resting_create_order",
            symbol=args.symbol,
            side="BUY",
            order_type="LIMIT",
            qty=_format_decimal(resting_qty),
            price=_format_decimal(resting_price),
            exchange_response_class=create_class,
            success=create_success,
            client_order_id=create_client_order_id,
            exchange_order_id=create_order_id,
            http_status=create_status,
            detail=create_detail,
        )
    )

    if create_success and create_order_id is not None:
        cancel_payload, cancel_status = resolved_api.cancel_order(
            symbol=args.symbol,
            order_id=create_order_id,
            client_order_id=create_client_order_id,
        )
        cancel_success, cancel_class, cancel_detail = _classify_response(cancel_payload, cancel_status)
        cancel_order_id = str(cancel_payload.get("orderId")) if isinstance(cancel_payload, dict) and cancel_payload.get("orderId") is not None else create_order_id
        events.append(
            ActionDriverEvent(
                timestamp=datetime.now(UTC).isoformat(),
                action_type="cancel_resting_order",
                symbol=args.symbol,
                side="BUY",
                order_type="LIMIT",
                qty=_format_decimal(resting_qty),
                price=_format_decimal(resting_price),
                exchange_response_class=cancel_class,
                success=cancel_success,
                client_order_id=create_client_order_id,
                exchange_order_id=cancel_order_id,
                http_status=cancel_status,
                detail=cancel_detail,
            )
        )
    else:
        events.append(
            ActionDriverEvent(
                timestamp=datetime.now(UTC).isoformat(),
                action_type="cancel_resting_order",
                symbol=args.symbol,
                side="BUY",
                order_type="LIMIT",
                qty=_format_decimal(resting_qty),
                price=_format_decimal(resting_price),
                exchange_response_class="skipped",
                success=False,
                client_order_id=create_client_order_id,
                exchange_order_id=create_order_id,
                detail="resting create order did not succeed, so cancel was skipped",
            )
        )

    if args.enable_fill_attempt:
        fill_client_order_id = _build_client_order_id(run_id=args.run_id, action_suffix="f")
        fill_qty = _quantize(resting_qty, rules.step_size, rounding=ROUND_DOWN)
        fill_payload, fill_status = resolved_api.place_market_order(
            symbol=args.symbol,
            side="BUY",
            quantity=fill_qty,
            client_order_id=fill_client_order_id,
        )
        fill_success, fill_class, fill_detail = _classify_response(fill_payload, fill_status)
        fill_order_id = str(fill_payload.get("orderId")) if isinstance(fill_payload, dict) and fill_payload.get("orderId") is not None else None
        events.append(
            ActionDriverEvent(
                timestamp=datetime.now(UTC).isoformat(),
                action_type="place_fill_attempt_order",
                symbol=args.symbol,
                side="BUY",
                order_type="MARKET",
                qty=_format_decimal(fill_qty),
                exchange_response_class=fill_class,
                success=fill_success,
                client_order_id=fill_client_order_id,
                exchange_order_id=fill_order_id,
                http_status=fill_status,
                detail=fill_detail,
            )
        )

    _write_events_jsonl(events_path, events)
    _write_summary_md(
        path=summary_path,
        run_id=args.run_id,
        config=config,
        symbol=args.symbol,
        qty=requested_qty,
        fill_attempt_enabled=args.enable_fill_attempt,
        events=events,
    )

    action_statuses = {event.action_type: event.success for event in events}
    create_leg_success = action_statuses.get("place_resting_create_order", False)
    cancel_leg_success = action_statuses.get("cancel_resting_order", False)
    fill_leg_success = action_statuses.get("place_fill_attempt_order", False)
    mandatory_success = create_leg_success and cancel_leg_success
    window_outcome = _classify_window_outcome(
        create_leg_success=create_leg_success,
        cancel_leg_success=cancel_leg_success,
        fill_attempt_enabled=args.enable_fill_attempt,
        fill_leg_success=fill_leg_success,
    )
    _write_result_artifact(
        path=result_path,
        run_id=args.run_id,
        window_outcome=window_outcome,
        mandatory_success=mandatory_success,
        fill_attempt_enabled=args.enable_fill_attempt,
        events=events,
        create_leg_success=create_leg_success,
        cancel_leg_success=cancel_leg_success,
        fill_leg_success=fill_leg_success,
    )
    return 0 if window_outcome in {SUCCESS, PARTIAL_SUCCESS_NONBLOCKING} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a narrow Binance Spot testnet event action driver")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--qty")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--enable-fill-attempt", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    action_dir = args.reports_dir / "event_exercises" / args.run_id / "action_driver"
    result_path = action_dir / "action_driver_result.json"
    try:
        return run_action_driver(args)
    except Exception as exc:
        action_dir.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "window_outcome": FATAL_FAILURE,
                    "mandatory_success": False,
                    "fill_attempt_enabled": bool(args.enable_fill_attempt),
                    "successful_actions": 0,
                    "failed_actions": 0,
                    "failure_reasons": [str(exc)],
                    "create_leg_success": False,
                    "cancel_leg_success": False,
                    "fill_leg_success": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
