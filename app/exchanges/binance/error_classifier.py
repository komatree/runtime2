"""Binance HTTP/code error classification hooks.

Adapted selectively from the local reference error classifier. The new version
returns `BinanceClientError` models instead of legacy exception classes.
"""

from __future__ import annotations

from typing import Any

from .models import BinanceClientError
from .models import BinanceErrorCategory


def classify_binance_http_error(
    *,
    http_status: int | None,
    json_code: int | None,
    message: str | None,
    headers: dict[str, Any] | None = None,
) -> BinanceClientError:
    """Classify Binance transport or API errors into adapter-facing categories."""

    text = (message or "").strip()
    text_upper = text.upper()
    normalized_headers = {str(key).lower(): value for key, value in (headers or {}).items()}

    def _header(name: str) -> str | None:
        value = normalized_headers.get(name.lower())
        return str(value) if value is not None else None

    def _header_float(name: str) -> float | None:
        value = _header(name)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    request_id = _header("x-request-id") or _header("x-mbx-uuid")
    retry_after_seconds = _header_float("retry-after")

    if http_status is None:
        return BinanceClientError(
            category=BinanceErrorCategory.TRANSIENT_NETWORK,
            message=text or "binance network error",
            retryable=True,
            raw_code=str(json_code) if json_code is not None else None,
            http_status=http_status,
            request_id=request_id,
        )

    if http_status in {401, 403} or json_code in {-2014, -2015}:
        return BinanceClientError(
            category=BinanceErrorCategory.AUTH,
            message=text or "binance authentication error",
            retryable=False,
            raw_code=str(json_code) if json_code is not None else None,
            http_status=http_status,
            request_id=request_id,
        )

    if http_status in {418, 429} or json_code == -1003:
        return BinanceClientError(
            category=BinanceErrorCategory.RATE_LIMIT,
            message=text or "binance rate limit error",
            retryable=True,
            raw_code=str(json_code) if json_code is not None else None,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
            request_id=request_id,
        )

    if json_code == -1021 or "TIMESTAMP" in text_upper:
        return BinanceClientError(
            category=BinanceErrorCategory.CLOCK_SKEW,
            message=text or "binance timestamp drift error",
            retryable=True,
            raw_code=str(json_code) if json_code is not None else None,
            http_status=http_status,
            request_id=request_id,
        )

    if http_status >= 500 or json_code in {-1013, -2010}:
        return BinanceClientError(
            category=BinanceErrorCategory.ORDER_REJECT if json_code in {-1013, -2010} else BinanceErrorCategory.UNKNOWN,
            message=text or "binance upstream error",
            retryable=http_status >= 500,
            raw_code=str(json_code) if json_code is not None else None,
            http_status=http_status,
            request_id=request_id,
        )

    return BinanceClientError(
        category=BinanceErrorCategory.UNKNOWN,
        message=text or "binance unknown error",
        retryable=False,
        raw_code=str(json_code) if json_code is not None else None,
        http_status=http_status,
        request_id=request_id,
    )
