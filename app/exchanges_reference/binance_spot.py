from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request

import requests

from bot.exchange.base import BaseExchange
from bot.exchange.errors import (
    ExchangeError,
    IpBannedError,
    LotSizeError,
    NetworkError,
    PriceFilterError,
    RateLimitError,
    UnknownExecutionError,
    UnexpectedExchangeError,
    classify_binance_error,
)
from bot.exchange.utils import ensure_min_notional, snap_price_to_tick, snap_qty_to_step
from bot.exchange.utils import (
    backoff_seconds,
    select_market_step_size,
    should_enforce_min_notional_for_market,
)
from bot.models import Candle, Fill, Order

logger = logging.getLogger(__name__)


class BinanceSpotExchange(BaseExchange):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        dry_run: bool,
        quote: str = "USDT",
        exchangeinfo_ttl_seconds: int = 3600,
        recv_window_ms: int = 10000,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._dry_run = bool(dry_run)
        self._quote = quote.upper()
        self._api_key_len = len(self._api_key)
        self._api_key_fingerprint = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()[:8] if self._api_key else ""
        self._api_secret_len = len(self._api_secret)
        self._api_secret_fingerprint = hashlib.sha256(self._api_secret.encode("utf-8")).hexdigest()[:8] if self._api_secret else ""
        self._exchangeinfo_ttl_seconds = int(exchangeinfo_ttl_seconds)
        self._recv_window_ms = int(recv_window_ms)
        self._exchangeinfo_cache: dict[str, Any] | None = None
        self._exchangeinfo_loaded_at = 0.0
        self._max_network_attempts = 3
        self._session = requests.Session()
        self._last_request_meta: dict[str, Any] | None = None

    def quote_currency(self) -> str:
        return self._quote

    def get_last_request_meta(self) -> dict[str, Any]:
        return dict(self._last_request_meta or {})

    def get_api_key_fingerprint(self) -> dict[str, Any]:
        return {
            "fingerprint": self._api_key_fingerprint,
            "length": self._api_key_len,
            "source": "env:BINANCE_API_KEY",
        }

    def get_api_secret_fingerprint(self) -> dict[str, Any]:
        return {
            "fingerprint": self._api_secret_fingerprint,
            "length": self._api_secret_len,
            "source": "env:BINANCE_API_SECRET",
        }

    def _sanitize_params_for_meta(self, params: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in params.items():
            if str(k).lower() == "signature":
                continue
            out[str(k)] = v
        return out

    def _extract_errno(self, exc: BaseException) -> int | None:
        current: BaseException | None = exc
        while current is not None:
            errno_attr = getattr(current, "errno", None)
            if errno_attr is not None:
                try:
                    return int(errno_attr)
                except (TypeError, ValueError):
                    pass
            current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        return None

    def describe_exception(
        self,
        exc: BaseException,
        *,
        endpoint: str | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        meta = self.get_last_request_meta()
        effective_endpoint = endpoint or str(meta.get("endpoint", ""))
        effective_params = params if params is not None else dict(meta.get("params", {}))
        effective_timeout = timeout if timeout is not None else meta.get("timeout")
        elapsed_ms = meta.get("elapsed_ms")
        try:
            elapsed_ms_int = int(elapsed_ms) if elapsed_ms is not None else None
        except (TypeError, ValueError):
            elapsed_ms_int = None
        errno_value = self._extract_errno(exc)
        return {
            "endpoint": effective_endpoint,
            "params": self._sanitize_params_for_meta(dict(effective_params or {})),
            "timeout": effective_timeout,
            "elapsed_ms": elapsed_ms_int,
            "exception_class": type(exc).__name__,
            "errno": errno_value,
            "message": str(exc),
        }

    def get_price(self, symbol: str) -> float:
        ex_symbol = self._to_exchange_symbol(symbol)
        payload = self._request_json(
            "GET",
            "/api/v3/ticker/price",
            params={"symbol": ex_symbol},
            signed=False,
        )
        return float(payload["price"])

    def get_balance(self, asset: str) -> float:
        payload = self._request_json(
            "GET",
            "/api/v3/account",
            params={},
            signed=True,
        )
        target = asset.strip().upper()
        for item in payload.get("balances", []):
            if str(item.get("asset", "")).upper() == target:
                free = float(item.get("free", 0.0))
                locked = float(item.get("locked", 0.0))
                return free + locked
        return 0.0

    def fetch_recent_candles(self, symbol: str, interval: str = "1m", limit: int = 200) -> list[Candle]:
        ex_symbol = self._to_exchange_symbol(symbol)
        payload = self._request_json(
            "GET",
            "/api/v3/klines",
            params={"symbol": ex_symbol, "interval": interval, "limit": int(limit)},
            signed=False,
        )
        out: list[Candle] = []
        for row in payload:
            # Binance kline schema: [open_time, open, high, low, close, volume, ...]
            open_time_ms = int(row[0])
            ts = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc)
            out.append(
                Candle(
                    symbol=symbol,
                    ts=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return out

    def get_symbol_trading_rules(self, symbol: str) -> dict[str, float]:
        ex_symbol = self._to_exchange_symbol(symbol)
        filters = self._get_symbol_filters(ex_symbol)
        return {
            "min_qty": float(filters.get("marketMinQty", filters.get("minQty", 0.0)) or 0.0),
            "max_qty": float(filters.get("marketMaxQty", filters.get("maxQty", 0.0)) or 0.0),
            "step_size_lot": float(filters.get("stepSize", 0.0) or 0.0),
            "step_size_market": float(filters.get("marketStepSize", 0.0) or 0.0),
            "step_size_effective": float(
                select_market_step_size(
                    float(filters.get("marketStepSize", 0.0) or 0.0),
                    float(filters.get("stepSize", 0.0) or 0.0),
                )
            ),
            "min_notional": float(filters.get("minNotional", 0.0) or 0.0),
            "tick_size": float(filters.get("tickSize", 0.0) or 0.0),
            "min_price": float(filters.get("minPrice", 0.0) or 0.0),
            "max_price": float(filters.get("maxPrice", 0.0) or 0.0),
            "apply_to_market": 1.0 if str(filters.get("applyToMarket", "true")).lower() == "true" else 0.0,
        }

    def _compute_market_order_constraints(self, order: Order) -> dict[str, Any]:
        ex_symbol = self._to_exchange_symbol(order.symbol)
        filters = self._get_symbol_filters(ex_symbol)

        step_size_lot = float(filters.get("stepSize", 0.0))
        step_size_market = float(filters.get("marketStepSize", 0.0))
        step_size = select_market_step_size(step_size_market, step_size_lot)
        min_qty = float(filters.get("marketMinQty", filters.get("minQty", 0.0)))
        max_qty = float(filters.get("marketMaxQty", filters.get("maxQty", 0.0)))
        tick_size = float(filters.get("tickSize", 0.0))
        min_price = float(filters.get("minPrice", 0.0))
        max_price = float(filters.get("maxPrice", 0.0))
        min_notional = float(filters.get("minNotional", 0.0))
        apply_to_market = filters.get("applyToMarket")

        qty_in = float(order.qty)
        price_in = float(order.price)
        snapped_qty = snap_qty_to_step(qty_in, step_size) if step_size > 0 else qty_in
        price_ref = price_in if price_in > 0 else self.get_price(order.symbol)
        snapped_price = snap_price_to_tick(price_ref, tick_size) if tick_size > 0 else price_ref
        notional = snapped_qty * snapped_price

        min_notional_enforced = should_enforce_min_notional_for_market(
            (str(apply_to_market).lower() == "true") if apply_to_market is not None else True
        )

        ok = True
        reason = "ok"
        if snapped_qty <= 0:
            ok = False
            reason = "qty_snapped_to_zero"
        elif min_qty > 0 and snapped_qty < min_qty:
            ok = False
            reason = "below_min_qty"
        elif max_qty > 0 and snapped_qty > max_qty:
            ok = False
            reason = "above_max_qty"
        elif min_price > 0 and snapped_price < min_price:
            ok = False
            reason = "below_min_price"
        elif max_price > 0 and snapped_price > max_price:
            ok = False
            reason = "above_max_price"
        elif min_notional_enforced and min_notional > 0 and notional < min_notional:
            ok = False
            reason = "below_min_notional"

        return {
            "ok": ok,
            "reason": reason,
            "symbol": order.symbol,
            "exchange_symbol": ex_symbol,
            "qty_in": qty_in,
            "qty_snapped": snapped_qty,
            "price_in": price_in,
            "price_ref": price_ref,
            "price_snapped": snapped_price,
            "notional": notional,
            "min_qty": min_qty,
            "max_qty": max_qty,
            "step_size": step_size,
            "step_size_lot": step_size_lot,
            "step_size_market": step_size_market,
            "min_notional": min_notional,
            "min_notional_enforced": min_notional_enforced,
            "tick_size": tick_size,
            "min_price": min_price,
            "max_price": max_price,
            "apply_to_market": str(apply_to_market if apply_to_market is not None else "true").lower(),
        }

    def validate_market_order_constraints(self, order: Order) -> dict[str, Any]:
        return self._compute_market_order_constraints(order)

    def place_order(self, order: Order) -> Fill:
        if self._dry_run:
            ts = datetime.now(timezone.utc)
            return Fill(
                order_id=order.order_id,
                symbol=order.symbol,
                qty=float(order.qty),
                price=float(order.price),
                fee=0.0,
                ts=ts,
            )

        if str(order.type).lower() != "market":
            raise UnexpectedExchangeError(
                "BinanceSpotExchange micro-live v1 supports MARKET orders only."
            )

        checks = self._compute_market_order_constraints(order)
        ex_symbol = str(checks["exchange_symbol"])
        snapped_qty = float(checks["qty_snapped"])
        snapped_price = float(checks["price_snapped"])
        min_notional = float(checks["min_notional"])
        if str(checks["reason"]) == "qty_snapped_to_zero":
            raise LotSizeError(f"quantity <= 0 after step snap: qty={order.qty}, step_size={checks['step_size']}")
        if str(checks["reason"]) == "below_min_qty":
            raise LotSizeError(f"quantity below minQty: qty={snapped_qty}, minQty={checks['min_qty']}")
        if str(checks["reason"]) == "above_max_qty":
            raise LotSizeError(f"quantity above maxQty: qty={snapped_qty}, maxQty={checks['max_qty']}")
        if str(checks["reason"]) == "below_min_price":
            raise PriceFilterError(f"price below minPrice: price={snapped_price}, minPrice={checks['min_price']}")
        if str(checks["reason"]) == "above_max_price":
            raise PriceFilterError(f"price above maxPrice: price={snapped_price}, maxPrice={checks['max_price']}")
        if str(checks["reason"]) == "below_min_notional":
            ensure_min_notional(snapped_qty, snapped_price, min_notional)

        params = {
            "symbol": ex_symbol,
            "side": str(order.side).upper(),
            "type": "MARKET",
            "quantity": self._fmt_decimal(snapped_qty),
            "newClientOrderId": str(order.order_id),
        }

        try:
            payload = self._request_json("POST", "/api/v3/order", params=params, signed=True)
        except UnknownExecutionError:
            # Unknown execution must be handled by caller-side reconciliation.
            raise
        fill_qty = float(payload.get("executedQty", snapped_qty) or snapped_qty)
        fills = payload.get("fills", []) or []
        fee = sum(float(x.get("commission", 0.0) or 0.0) for x in fills)
        fill_price = self._avg_fill_price(payload, fills, fallback=snapped_price)
        transact_ms = payload.get("transactTime")
        if transact_ms is not None:
            ts = datetime.fromtimestamp(float(transact_ms) / 1000.0, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            qty=fill_qty,
            price=fill_price,
            fee=fee,
            ts=ts,
        )

    def _avg_fill_price(self, payload: dict[str, Any], fills: list[dict[str, Any]], fallback: float) -> float:
        if fills:
            total_qty = 0.0
            total_notional = 0.0
            for f in fills:
                q = float(f.get("qty", 0.0) or 0.0)
                p = float(f.get("price", 0.0) or 0.0)
                total_qty += q
                total_notional += q * p
            if total_qty > 0:
                return total_notional / total_qty
        exec_qty = float(payload.get("executedQty", 0.0) or 0.0)
        quote_qty = float(payload.get("cummulativeQuoteQty", 0.0) or 0.0)
        if exec_qty > 0 and quote_qty > 0:
            return quote_qty / exec_qty
        return fallback

    def _to_exchange_symbol(self, symbol: str) -> str:
        raw = (symbol or "").strip().upper()
        if not raw:
            return self._quote
        if raw.endswith(self._quote):
            return raw
        return f"{raw}{self._quote}"

    def _fmt_decimal(self, value: float) -> str:
        s = f"{value:.12f}".rstrip("0").rstrip(".")
        return s if s else "0"

    def _now_ms(self) -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def _normalize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, (dict, list)):
                out[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                out[key] = value
        return out

    def _encode_params(self, params: dict[str, Any]) -> str:
        return urlencode(self._normalize_params(params), doseq=True, safe="", quote_via=quote)

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        p = dict(params)
        p.setdefault("timestamp", self._now_ms())
        p.setdefault("recvWindow", self._recv_window_ms)
        query = self._encode_params(p)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        p["signature"] = signature
        return p

    def _load_exchange_info(self, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if (
            not force
            and self._exchangeinfo_cache is not None
            and (now - self._exchangeinfo_loaded_at) < self._exchangeinfo_ttl_seconds
        ):
            return self._exchangeinfo_cache
        payload = self._request_json("GET", "/api/v3/exchangeInfo", params={}, signed=False)
        self._exchangeinfo_cache = payload
        self._exchangeinfo_loaded_at = now
        return payload

    def _get_symbol_filters(self, ex_symbol: str) -> dict[str, str]:
        info = self._load_exchange_info(force=False)
        for entry in info.get("symbols", []):
            if str(entry.get("symbol", "")).upper() != ex_symbol:
                continue
            out: dict[str, str] = {}
            for f in entry.get("filters", []):
                ftype = str(f.get("filterType", ""))
                if ftype == "LOT_SIZE":
                    out["minQty"] = str(f.get("minQty", "0"))
                    out["maxQty"] = str(f.get("maxQty", "0"))
                    out["stepSize"] = str(f.get("stepSize", "0"))
                elif ftype == "MARKET_LOT_SIZE":
                    out["marketMinQty"] = str(f.get("minQty", "0"))
                    out["marketMaxQty"] = str(f.get("maxQty", "0"))
                    out["marketStepSize"] = str(f.get("stepSize", "0"))
                elif ftype == "PRICE_FILTER":
                    out["minPrice"] = str(f.get("minPrice", "0"))
                    out["maxPrice"] = str(f.get("maxPrice", "0"))
                    out["tickSize"] = str(f.get("tickSize", "0"))
                elif ftype == "MIN_NOTIONAL":
                    out["minNotional"] = str(f.get("minNotional", "0"))
                    out["applyToMarket"] = str(f.get("applyToMarket", "true"))
            return out
        raise UnexpectedExchangeError(f"symbol not found in exchangeInfo: {ex_symbol}")

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        *,
        signed: bool,
    ) -> dict[str, Any]:
        req_params = self._signed_params(params) if signed else dict(params)
        params_for_meta = self._sanitize_params_for_meta(req_params)
        encoded_params = self._encode_params(req_params)
        body = encoded_params.encode("utf-8")
        url = f"{self._base_url}{path}"
        headers = {"X-MBX-APIKEY": self._api_key} if signed or method.upper() == "POST" else {}
        api_key_header_included = "X-MBX-APIKEY" in headers
        timeout_seconds = 10.0
        if method.upper() == "GET":
            final_url = f"{url}?{encoded_params}" if req_params else url
            request = Request(final_url, method="GET", headers=headers)
        else:
            headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
            request = Request(url, data=body, method=method.upper(), headers=headers)

        if os.getenv("BINANCE_DEBUG_URL", "0") == "1":
            safe_url = self._sanitize_url_for_log(request.full_url)
            logger.info("binance_request method=%s url=%s", method.upper(), safe_url)

        last_status: int | None = None
        last_headers: dict[str, str] = {}
        last_code: int | None = None
        last_msg: str = "binance exchange error"
        for attempt in range(1, self._max_network_attempts + 1):
            attempt_started = time.perf_counter()
            try:
                status, resp_headers, text = self._perform_http(request, timeout=timeout_seconds)
                elapsed_ms = int(max(time.perf_counter() - attempt_started, 0.0) * 1000.0)
                self._last_request_meta = {
                    "method": method.upper(),
                    "endpoint": path,
                    "params": params_for_meta,
                    "api_key_header_included": api_key_header_included,
                    "timeout": timeout_seconds,
                    "elapsed_ms": elapsed_ms,
                    "attempt": attempt,
                    "http_status": int(status),
                }
            except OSError as exc:
                elapsed_ms = int(max(time.perf_counter() - attempt_started, 0.0) * 1000.0)
                self._last_request_meta = {
                    "method": method.upper(),
                    "endpoint": path,
                    "params": params_for_meta,
                    "api_key_header_included": api_key_header_included,
                    "timeout": timeout_seconds,
                    "elapsed_ms": elapsed_ms,
                    "attempt": attempt,
                    "http_status": None,
                }
                if path == "/api/v3/order":
                    raise UnknownExecutionError(
                        str(exc),
                        endpoint=path,
                        request_id=None,
                        http_status=None,
                    ) from exc
                if attempt >= self._max_network_attempts:
                    raise NetworkError(str(exc)) from exc
                wait = backoff_seconds(attempt - 1, base=1.0, cap=30.0, jitter="full")
                time.sleep(max(wait, 0.0))
                continue

            if 200 <= status < 300:
                if not text:
                    return {}
                return json.loads(text)

            code = None
            msg = text
            try:
                payload = json.loads(text or "{}")
                code = payload.get("code")
                msg = payload.get("msg", text)
            except json.JSONDecodeError:
                payload = None

            code_int: int | None = None
            if isinstance(code, int):
                code_int = code
            elif isinstance(code, str):
                try:
                    code_int = int(code)
                except ValueError:
                    code_int = None

            last_status = status
            last_headers = dict(resp_headers or {})
            last_code = code_int
            last_msg = str(msg)

            if status in {429, 418} and attempt < self._max_network_attempts:
                retry_after = resp_headers.get("Retry-After")
                try:
                    retry_after_seconds = int(retry_after) if retry_after is not None else 1
                except ValueError:
                    retry_after_seconds = 1
                wait_backoff = backoff_seconds(attempt - 1, base=1.0, cap=30.0, jitter="full")
                wait = max(wait_backoff, float(retry_after_seconds + 1))
                time.sleep(max(wait, 1.0))
                continue

            err = classify_binance_error(
                status,
                code_int,
                str(msg),
                resp_headers,
                endpoint=path,
            )
            raise err

        if last_status in {429, 418}:
            err = classify_binance_error(last_status, last_code, last_msg, last_headers)
            if last_status == 429 and isinstance(err, RateLimitError):
                raise err
            if last_status == 418 and isinstance(err, IpBannedError):
                raise err
        raise UnexpectedExchangeError("request failed after retries")

    def _sanitize_url_for_log(self, url: str) -> str:
        parts = urlsplit(url)
        if not parts.query:
            return url
        filtered_query = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "signature"
        ]
        safe_query = urlencode(filtered_query, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, parts.fragment))

    def _perform_http(self, request: Request, timeout: float) -> tuple[int, dict[str, str], str]:
        try:
            resp = self._session.request(
                method=request.get_method(),
                url=request.full_url,
                headers={k: v for k, v in request.header_items()},
                data=request.data,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            # Preserve existing retry/error flow that handles OSError from transport.
            raise OSError(str(exc)) from exc
        status = int(getattr(resp, "status_code", 0) or 0)
        headers = {k: v for k, v in dict(resp.headers).items()}
        body = str(getattr(resp, "text", "") or "")
        return status, headers, body
