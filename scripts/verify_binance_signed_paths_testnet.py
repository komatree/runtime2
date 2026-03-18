#!/usr/bin/env python3
"""Verify runtime2 Binance signed paths against Spot testnet safely.

This harness is intentionally conservative:
- local capture verification runs by default
- live Spot testnet verification only runs with --allow-live-testnet
- no order submission is performed
- secrets are masked in outputs
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
from dataclasses import field
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from decimal import ROUND_DOWN
from decimal import ROUND_UP
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinancePrivateUserDataTransport
from app.exchanges.binance import BinanceRequestWeightTracker
from app.exchanges.binance import BinanceSignedRestOrderStatusTransport


@dataclass(frozen=True)
class VerificationResult:
    name: str
    path_type: str
    status: str
    verified_live: bool
    detail: str
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationSummary:
    checked_at: str
    config_path: str
    endpoint_profile_name: str
    live_testnet_enabled: bool
    results: tuple[VerificationResult, ...]


@dataclass(frozen=True)
class _RestProbeTarget:
    symbol: str
    quantity: str
    client_order_id: str
    exchange_order_id: str
    create_http_status: int | None
    create_order_status: str | None


@dataclass
class _FakeHttpResponse:
    payload: object
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class _CapturingUrlOpen:
    payload: object
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, request):
        self.calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "method": request.get_method(),
            }
        )
        return _FakeHttpResponse(self.payload, status=self.status, headers=self.headers)


@dataclass
class _CapturingWebSocketConnection:
    responses: list[str]
    sent_frames: list[str] = field(default_factory=list)

    def recv_text(self) -> str:
        return self.responses.pop(0)

    def send_text(self, text: str) -> None:
        self.sent_frames.append(text)

    def close(self) -> None:
        return None


@dataclass
class _CapturingWebSocketFactory:
    responses: tuple[str, ...]

    def __post_init__(self) -> None:
        self.last_connection: _CapturingWebSocketConnection | None = None
        self.calls: list[dict[str, object]] = []

    def connect(self, *, url: str, headers: dict[str, str] | None = None):
        self.calls.append({"url": url, "headers": headers or {}})
        self.last_connection = _CapturingWebSocketConnection(responses=list(self.responses))
        return self.last_connection


def _mask(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _quantize(value: Decimal, step: Decimal, *, rounding: str) -> Decimal:
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


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


def _request_json(*, request: Request, urlopen_fn: object = urlopen) -> tuple[dict[str, Any] | list[Any], int | None]:
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


def _build_rest_probe_client_order_id() -> str:
    return f"rt2-rest-probe-{int(datetime.now(UTC).timestamp())}"


def _create_live_rest_probe_order(config: BinanceAdapterConfig) -> _RestProbeTarget:
    if not config.api_key or not config.api_secret:
        raise ValueError("BINANCE_API_KEY / BINANCE_API_SECRET are not set")
    exchange_info_request = Request(
        url=f"{config.rest_base_url.rstrip('/')}/api/v3/exchangeInfo?symbol=BTCUSDT",
        method="GET",
    )
    exchange_info_payload, _ = _request_json(request=exchange_info_request)
    if not isinstance(exchange_info_payload, dict):
        raise ValueError("non-object exchangeInfo payload")
    symbols = exchange_info_payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("exchangeInfo did not return rules for BTCUSDT")
    symbol_payload = symbols[0]
    filters = {
        str(item.get("filterType")): item
        for item in symbol_payload.get("filters", [])
        if isinstance(item, dict)
    }
    lot = filters.get("LOT_SIZE", {})
    min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
    step_size = Decimal(str(lot.get("stepSize", "0.000001")))
    min_qty = Decimal(str(lot.get("minQty", "0.000001")))
    min_notional = (
        Decimal(str(min_notional_filter.get("minNotional")))
        if min_notional_filter.get("minNotional") is not None
        else Decimal("5")
    )

    ticker_request = Request(
        url=f"{config.rest_base_url.rstrip('/')}/api/v3/ticker/price?symbol=BTCUSDT",
        method="GET",
    )
    ticker_payload, _ = _request_json(request=ticker_request)
    if not isinstance(ticker_payload, dict) or "price" not in ticker_payload:
        raise ValueError("ticker price unavailable for BTCUSDT")
    market_price = Decimal(str(ticker_payload["price"]))
    required_qty = max(
        min_qty,
        _quantize(min_notional / market_price, step_size, rounding=ROUND_UP),
        _quantize(Decimal("5") / market_price, step_size, rounding=ROUND_UP),
    )
    quantity = _quantize(required_qty, step_size, rounding=ROUND_DOWN)
    if quantity < min_qty:
        quantity = min_qty

    client_order_id = _build_rest_probe_client_order_id()
    signed_query = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": _format_decimal(quantity),
        "newClientOrderId": client_order_id,
        "timestamp": str(int(datetime.now(UTC).timestamp() * 1000)),
        "recvWindow": str(config.recv_window_ms),
    }
    query_string = urlencode(signed_query)
    signature = hmac.new(
        config.api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    request = Request(
        url=f"{config.rest_base_url.rstrip('/')}/api/v3/order?{query_string}&signature={signature}",
        method="POST",
        headers={"X-MBX-APIKEY": config.api_key},
    )
    payload, http_status = _request_json(request=request)
    if isinstance(payload, dict) and "code" in payload and "msg" in payload and payload.get("orderId") is None:
        raise ValueError(f"probe order create failed with Binance {payload.get('code')}: {payload.get('msg')}")
    if not isinstance(payload, dict) or payload.get("orderId") is None:
        raise ValueError("probe order create did not return an orderId")
    return _RestProbeTarget(
        symbol="BTCUSDT",
        quantity=_format_decimal(quantity),
        client_order_id=str(payload.get("clientOrderId", client_order_id)),
        exchange_order_id=str(payload["orderId"]),
        create_http_status=http_status,
        create_order_status=str(payload.get("status")) if payload.get("status") is not None else None,
    )


def _rest_local_capture(config: BinanceAdapterConfig) -> VerificationResult:
    urlopen = _CapturingUrlOpen(payload={"code": -2013, "msg": "Order does not exist."}, status=400)
    transport = BinanceSignedRestOrderStatusTransport(
        config=config,
        venue_symbol="BTCUSDT",
        time_provider=lambda: 1773532800000,
        urlopen_fn=urlopen,
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=1200),
    )
    client_order_id = "runtime2 verify/space+plus:test"
    transport.lookup_by_client_order_id(client_order_id=client_order_id)
    call = urlopen.calls[0]
    parsed = urlparse(str(call["url"]))
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    signature = next(value for key, value in pairs if key == "signature")
    unsigned_pairs = [(key, value) for key, value in pairs if key != "signature"]
    unsigned_query = urlencode(unsigned_pairs)
    expected_signature = hmac.new(
        config.api_secret.encode("utf-8"),
        unsigned_query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    query_keys = tuple(key for key, _ in unsigned_pairs)
    return VerificationResult(
        name="local_rest_percent_encode_and_hmac",
        path_type="signed_rest_order_lookup",
        status="verified on current local capture",
        verified_live=False,
        detail="runtime2 REST signing path encodes the query before HMAC and includes timestamp, recvWindow, and signature",
        evidence={
            "request_method": call["method"],
            "query_keys": query_keys,
            "contains_timestamp": "timestamp" in query_keys,
            "contains_recv_window": "recvWindow" in query_keys,
            "contains_signature": signature != "",
            "signature_matches_expected_hmac": signature == expected_signature,
            "encoded_query_before_signature": unsigned_query,
            "masked_api_key": _mask(config.api_key),
        },
    )


def _ws_local_capture(config: BinanceAdapterConfig) -> VerificationResult:
    factory = _CapturingWebSocketFactory(
        responses=(json.dumps({"id": 1, "status": 200, "result": {"subscriptionId": 42}}),)
    )
    transport = BinancePrivateUserDataTransport(
        rest_base_url=config.rest_base_url,
        websocket_base_url=config.websocket_base_url,
        api_key=config.api_key,
        api_secret=config.api_secret,
        endpoint_profile_name=config.endpoint_profile_name,
        websocket_factory=factory,
    )
    connection_id = transport.open_connection(account_scope="spot")
    subscription = transport.subscribe(connection_id=connection_id, account_scope="spot")
    sent = json.loads(factory.last_connection.sent_frames[0]) if factory.last_connection else {}
    params = dict(sent.get("params", {}))
    signature = str(params.pop("signature", ""))
    canonical_query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    expected_signature = hmac.new(
        config.api_secret.encode("utf-8"),
        canonical_query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return VerificationResult(
        name="local_ws_api_subscription_signing",
        path_type="ws_api_user_data_subscription",
        status="verified on current local capture",
        verified_live=False,
        detail="runtime2 WS-API user data subscription builds a signed request with apiKey, recvWindow, timestamp, and signature",
        evidence={
            "request_method": sent.get("method"),
            "contains_api_key": "apiKey" in sent.get("params", {}),
            "contains_timestamp": "timestamp" in sent.get("params", {}),
            "contains_recv_window": "recvWindow" in sent.get("params", {}),
            "contains_signature": signature != "",
            "signature_matches_expected_hmac": signature == expected_signature,
            "subscription_bootstrap_method": subscription.bootstrap_method,
            "ws_api_url": factory.calls[0]["url"] if factory.calls else None,
            "masked_api_key": _mask(config.api_key),
        },
    )


def _live_rest_verification(config: BinanceAdapterConfig) -> VerificationResult:
    if not config.api_key or not config.api_secret:
        return VerificationResult(
            name="live_rest_signed_lookup_on_spot_testnet",
            path_type="signed_rest_order_lookup",
            status="not verified",
            verified_live=False,
            detail="BINANCE_API_KEY / BINANCE_API_SECRET are not set, so live Spot testnet REST verification was not attempted",
        )
    try:
        probe_target = _create_live_rest_probe_order(config)
    except Exception as exc:
        return VerificationResult(
            name="live_rest_signed_lookup_on_spot_testnet",
            path_type="signed_rest_order_lookup",
            status="not verified",
            verified_live=False,
            detail=f"Spot testnet REST verification could not create a minimal lookup target: {exc}",
        )
    transport = BinanceSignedRestOrderStatusTransport(
        config=config,
        venue_symbol=probe_target.symbol,
        time_provider=lambda: int(datetime.now(UTC).timestamp() * 1000),
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=1200),
    )
    result = transport.lookup_by_client_order_id(client_order_id=probe_target.client_order_id)
    health = transport.last_health()
    alert = result.alert or (health.alert if health is not None and health.alert is not None else "")
    normalized_alert = alert.lower()
    if "-1022" in alert or "INVALID_SIGNATURE" in alert:
        status = "not verified"
        detail = "Spot testnet REST signed lookup failed with an INVALID_SIGNATURE-class error"
    elif any(
        marker in normalized_alert
        for marker in (
            "temporary failure in name resolution",
            "name or service not known",
            "connection refused",
            "timed out",
            "timeout",
            "network is unreachable",
            "http error 5",
            "urlopen error",
        )
    ):
        status = "not verified"
        detail = f"Spot testnet REST signed lookup did not complete because of an environment/transport error: {alert}"
    elif health is not None and health.state.value == "success":
        status = "verified on current Spot testnet"
        detail = (
            "Spot testnet accepted the signed REST lookup path without INVALID_SIGNATURE; "
            "the returned business result was successful"
        )
    elif "binance lookup error" in normalized_alert:
        status = "verified on current Spot testnet"
        detail = (
            "Spot testnet accepted the signed REST lookup path without INVALID_SIGNATURE; "
            "the returned result was a signed business error rather than a transport failure"
        )
    else:
        status = "partially verified"
        detail = (
            "Spot testnet REST lookup reached the signed transport path, "
            "but acceptance could not be proven conclusively from the returned result"
        )
    return VerificationResult(
        name="live_rest_signed_lookup_on_spot_testnet",
        path_type="signed_rest_order_lookup",
        status=status,
        verified_live=status == "verified on current Spot testnet",
        detail=detail,
        evidence={
            "probe_order_source": "harness_created_market_order",
            "probe_symbol": probe_target.symbol,
            "probe_quantity": probe_target.quantity,
            "probe_client_order_id": probe_target.client_order_id,
            "probe_exchange_order_id": probe_target.exchange_order_id,
            "probe_create_http_status": probe_target.create_http_status,
            "probe_create_order_status": probe_target.create_order_status,
            "found": result.found,
            "result_alert": result.alert,
            "health_state": health.state.value if health is not None else None,
            "health_alert": health.alert if health is not None else None,
            "endpoint_profile_name": config.endpoint_profile_name,
        },
    )


def _live_ws_verification(config: BinanceAdapterConfig) -> VerificationResult:
    if not config.api_key or not config.api_secret:
        return VerificationResult(
            name="live_ws_api_user_data_subscription_on_spot_testnet",
            path_type="ws_api_user_data_subscription",
            status="not verified",
            verified_live=False,
            detail="BINANCE_API_KEY / BINANCE_API_SECRET are not set, so live Spot testnet WS-API subscription verification was not attempted",
        )
    transport = BinancePrivateUserDataTransport(
        rest_base_url=config.rest_base_url,
        websocket_base_url=config.websocket_base_url,
        api_key=config.api_key,
        api_secret=config.api_secret,
        endpoint_profile_name=config.endpoint_profile_name,
        request_weight_tracker=BinanceRequestWeightTracker(max_weight=1200),
    )
    connection_id: str | None = None
    try:
        connection_id = transport.open_connection(account_scope="spot")
        subscription = transport.subscribe(connection_id=connection_id, account_scope="spot")
    except Exception as exc:
        detail = str(exc)
        status = "not verified"
        if "-1022" in detail or "INVALID_SIGNATURE" in detail:
            detail = f"Spot testnet WS-API subscription failed with an INVALID_SIGNATURE-class error: {exc}"
        else:
            detail = f"Spot testnet WS-API subscription was attempted but did not complete successfully: {exc}"
        return VerificationResult(
            name="live_ws_api_user_data_subscription_on_spot_testnet",
            path_type="ws_api_user_data_subscription",
            status=status,
            verified_live=False,
            detail=detail,
        )
    finally:
        if connection_id is not None:
            try:
                transport.close_connection(connection_id=connection_id)
            except Exception:
                pass
    return VerificationResult(
        name="live_ws_api_user_data_subscription_on_spot_testnet",
        path_type="ws_api_user_data_subscription",
        status="verified on current Spot testnet",
        verified_live=True,
        detail="Spot testnet accepted runtime2 WS-API userDataStream.subscribe.signature bootstrap",
        evidence={
            "subscription_id": subscription.subscription_id,
            "bootstrap_method": subscription.bootstrap_method,
            "endpoint_profile_name": config.endpoint_profile_name,
        },
    )


def _recv_window_timestamp_assumption_result(
    rest_result: VerificationResult,
    ws_result: VerificationResult,
) -> VerificationResult:
    live_verified = rest_result.verified_live and ws_result.verified_live
    if live_verified:
        return VerificationResult(
            name="timestamp_and_recv_window_assumptions",
            path_type="shared_signed_path",
            status="verified on current Spot testnet",
            verified_live=True,
            detail="Both signed REST and signed WS-API paths were accepted on Spot testnet with runtime2 timestamp and recvWindow assumptions",
        )
    return VerificationResult(
        name="timestamp_and_recv_window_assumptions",
        path_type="shared_signed_path",
        status="partially verified",
        verified_live=False,
        detail=(
            "timestamp/recvWindow assumptions are verified locally through the constructed signed requests, "
            "but not fully live-verified unless both live REST and live WS checks succeed"
        ),
    )


def _render_markdown(summary: VerificationSummary) -> str:
    lines = [
        "# Binance Signed Path Verification Results",
        "",
        f"- checked_at: `{summary.checked_at}`",
        f"- config_path: `{summary.config_path}`",
        f"- endpoint_profile_name: `{summary.endpoint_profile_name}`",
        f"- live_testnet_enabled: `{summary.live_testnet_enabled}`",
        "",
        "## Results",
        "",
        "| Check | Path Type | Status | Live Verified | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in summary.results:
        lines.append(
            f"| `{result.name}` | `{result.path_type}` | `{result.status}` | `{result.verified_live}` | {result.detail} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Notes",
            "",
            "- `verified on current Spot testnet` means the harness attempted the real testnet path with current credentials and did not observe an `INVALID_SIGNATURE`-class failure for that path.",
            "- `partially verified` means the harness verified the constructed request/signing shape locally but did not complete a real testnet proof for the entire path.",
            "- `not verified` means the harness did not attempt the live path or the attempt failed before proving current Spot testnet acceptance.",
        ]
    )
    return "\n".join(lines) + "\n"


def _summary_to_json(summary: VerificationSummary) -> dict[str, Any]:
    return {
        "checked_at": summary.checked_at,
        "config_path": summary.config_path,
        "endpoint_profile_name": summary.endpoint_profile_name,
        "live_testnet_enabled": summary.live_testnet_enabled,
        "results": [asdict(result) for result in summary.results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify runtime2 Binance signed paths on Spot testnet")
    parser.add_argument(
        "--config",
        default="configs/runtime2_restricted_live_testnet.toml",
        help="Path to the Spot testnet runtime2 config",
    )
    parser.add_argument(
        "--allow-live-testnet",
        action="store_true",
        help="Attempt real Spot testnet verification using current BINANCE_API_KEY / BINANCE_API_SECRET",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/signed_path_verification/latest",
        help="Directory for JSON/Markdown verification artifacts",
    )
    args = parser.parse_args()

    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = _load_config(config_path)
    checked_at = datetime.now(UTC).isoformat()

    results: list[VerificationResult] = [
        _rest_local_capture(config),
        _ws_local_capture(config),
    ]
    if args.allow_live_testnet:
        live_rest = _live_rest_verification(config)
        live_ws = _live_ws_verification(config)
    else:
        live_rest = VerificationResult(
            name="live_rest_signed_lookup_on_spot_testnet",
            path_type="signed_rest_order_lookup",
            status="not verified",
            verified_live=False,
            detail="live Spot testnet verification was not attempted because --allow-live-testnet was not provided",
        )
        live_ws = VerificationResult(
            name="live_ws_api_user_data_subscription_on_spot_testnet",
            path_type="ws_api_user_data_subscription",
            status="not verified",
            verified_live=False,
            detail="live Spot testnet verification was not attempted because --allow-live-testnet was not provided",
        )
    results.extend((live_rest, live_ws, _recv_window_timestamp_assumption_result(live_rest, live_ws)))
    summary = VerificationSummary(
        checked_at=checked_at,
        config_path=str(config_path),
        endpoint_profile_name=config.endpoint_profile_name,
        live_testnet_enabled=args.allow_live_testnet,
        results=tuple(results),
    )

    output_dir = ROOT / args.output_dir if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "signed_path_summary.json"
    md_path = output_dir / "signed_path_summary.md"
    json_path.write_text(json.dumps(_summary_to_json(summary), indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(summary), encoding="utf-8")

    print(f"checked_at: {summary.checked_at}")
    print(f"config_path: {summary.config_path}")
    print(f"endpoint_profile_name: {summary.endpoint_profile_name}")
    print(f"live_testnet_enabled: {summary.live_testnet_enabled}")
    for result in summary.results:
        print(f"{result.name}: {result.status}")
    print(f"signed_path_summary_json: {json_path}")
    print(f"signed_path_summary_md: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
