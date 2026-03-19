from __future__ import annotations

import re
from typing import Any


class ExchangeError(Exception):
    """Base exchange-layer error for normalized adapter handling."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.binance_code = binance_code
        self.message = message


class RateLimitError(ExchangeError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        weight_ip: int | None = None,
        weight_uid: int | None = None,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, binance_code=binance_code)
        self.retry_after_seconds = retry_after_seconds
        self.weight_ip = weight_ip
        self.weight_uid = weight_uid


class IpBannedError(ExchangeError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        weight_ip: int | None = None,
        weight_uid: int | None = None,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, binance_code=binance_code)
        self.retry_after_seconds = retry_after_seconds
        self.weight_ip = weight_ip
        self.weight_uid = weight_uid


class TimestampDriftError(ExchangeError):
    def __init__(
        self,
        message: str,
        *,
        server_time_ms: int | None = None,
        local_time_ms: int | None = None,
        drift_ms: int | None = None,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, binance_code=binance_code)
        self.server_time_ms = server_time_ms
        self.local_time_ms = local_time_ms
        self.drift_ms = drift_ms


class MinNotionalError(ExchangeError):
    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        notional: float | None = None,
        required_min_notional: float | None = None,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, binance_code=binance_code)
        self.symbol = symbol
        self.notional = notional
        self.required_min_notional = required_min_notional


class LotSizeError(ExchangeError):
    pass


class PriceFilterError(ExchangeError):
    pass


class InsufficientBalanceError(ExchangeError):
    pass


class AuthenticationError(ExchangeError):
    pass


class NetworkError(ExchangeError):
    pass


class UnexpectedExchangeError(ExchangeError):
    pass


class UnknownExecutionError(ExchangeError):
    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        request_id: str | None = None,
        http_status: int | None = None,
        binance_code: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status, binance_code=binance_code)
        self.endpoint = endpoint
        self.request_id = request_id
        self.is_unknown_execution = True


def classify_binance_error(
    http_status: int | None,
    json_code: int | None,
    msg: str | None,
    headers: dict[str, Any] | None = None,
    endpoint: str | None = None,
) -> ExchangeError:
    """
    Convert Binance HTTP/code/message payloads into normalized exchange errors.
    """
    text = (msg or "").strip()
    text_u = text.upper()
    hdrs = {str(k).lower(): v for k, v in (headers or {}).items()}

    def _get_header(name: str) -> str | None:
        value = hdrs.get(name.lower())
        return str(value) if value is not None else None

    def _to_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _to_int_or_none(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    def _to_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    retry_after = _to_int_or_none(_get_header("Retry-After"))
    weight_ip = _to_int(_get_header("x-mbx-used-weight-1m") or _get_header("x-mbx-used-weight"))
    weight_uid = _to_int(_get_header("x-mbx-used-weight-uid-1m") or _get_header("x-mbx-used-weight-uid"))

    def _make(err_cls: type[ExchangeError]) -> ExchangeError:
        return err_cls(
            text or "binance exchange error",
            http_status=http_status,
            binance_code=json_code,
        )

    if http_status is None:
        return _make(NetworkError)

    # HTTP status takes precedence for 418/429 mapping.
    if http_status == 418:
        return IpBannedError(
            text or "binance exchange error",
            http_status=http_status,
            binance_code=json_code,
            retry_after_seconds=retry_after if retry_after is not None else 1,
            weight_ip=weight_ip,
            weight_uid=weight_uid,
        )
    if http_status == 429:
        return RateLimitError(
            text or "binance exchange error",
            http_status=http_status,
            binance_code=json_code,
            retry_after_seconds=retry_after if retry_after is not None else 1,
            weight_ip=weight_ip,
            weight_uid=weight_uid,
        )

    if http_status in {401, 403}:
        return _make(AuthenticationError)
    if http_status in {500, 502, 503, 504}:
        request_id = _get_header("x-request-id") or _get_header("x-mbx-uuid")
        return UnknownExecutionError(
            text or "binance exchange error",
            endpoint=endpoint or "",
            request_id=request_id,
            http_status=http_status,
            binance_code=json_code,
        )
    if http_status >= 500:
        return _make(NetworkError)

    if json_code in {-2014, -2015}:
        return _make(AuthenticationError)
    if json_code == -1021:
        return TimestampDriftError(
            text or "binance exchange error",
            http_status=http_status,
            binance_code=json_code,
        )
    if json_code == -1003:
        if "IP BANNED" in text_u or "TOO MANY REQUESTS" in text_u:
            if "IP BANNED" in text_u:
                return IpBannedError(
                    text or "binance exchange error",
                    http_status=http_status,
                    binance_code=json_code,
                    retry_after_seconds=retry_after if retry_after is not None else 1,
                    weight_ip=weight_ip,
                    weight_uid=weight_uid,
                )
            return RateLimitError(
                text or "binance exchange error",
                http_status=http_status,
                binance_code=json_code,
                retry_after_seconds=retry_after if retry_after is not None else 1,
                weight_ip=weight_ip,
                weight_uid=weight_uid,
            )

    if json_code == -1013:
        if "PRICE_FILTER" in text_u:
            return _make(PriceFilterError)
        if "LOT_SIZE" in text_u or "MARKET_LOT_SIZE" in text_u:
            return _make(LotSizeError)
        if "MIN_NOTIONAL" in text_u:
            required = None
            m = re.search(r"(?i)min[_ ]?notional[^0-9]*([0-9]+(?:\.[0-9]+)?)", text)
            if m:
                try:
                    required = float(m.group(1))
                except ValueError:
                    required = None
            return MinNotionalError(
                text or "binance exchange error",
                http_status=http_status,
                binance_code=json_code,
                symbol=None,
                notional=None,
                required_min_notional=required,
            )
        return _make(UnexpectedExchangeError)

    if json_code == -2010:
        if "INSUFFICIENT BALANCE" in text_u or "ACCOUNT HAS INSUFFICIENT BALANCE" in text_u:
            return _make(InsufficientBalanceError)
        return _make(UnexpectedExchangeError)

    return _make(UnexpectedExchangeError)
