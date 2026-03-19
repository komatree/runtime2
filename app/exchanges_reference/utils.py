from __future__ import annotations

import math
import random

from bot.exchange.errors import MinNotionalError

SYMBOL_MAP: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}


def to_usdt_symbol(symbol: str) -> str:
    """
    Convert internal symbol into Binance spot USDT pair symbol.
    Falls back to "<SYMBOL>USDT" for unknown symbols.
    """
    key = (symbol or "").strip().upper()
    if not key:
        return "USDT"
    return SYMBOL_MAP.get(key, f"{key}USDT")


def snap_qty_to_step(qty: float, step_size: float) -> float:
    """Floor quantity to exchange lot step."""
    if step_size <= 0:
        raise ValueError("step_size must be > 0")
    if qty <= 0:
        return 0.0
    return math.floor(qty / step_size) * step_size


def snap_price_to_tick(price: float, tick_size: float) -> float:
    """Floor price to exchange tick size."""
    if tick_size <= 0:
        raise ValueError("tick_size must be > 0")
    if price <= 0:
        return 0.0
    return math.floor(price / tick_size) * tick_size


def ensure_min_notional(qty: float, price: float, min_notional: float) -> None:
    """Raise MinNotionalError when qty*price is below min_notional."""
    if min_notional <= 0:
        return
    notional = float(qty) * float(price)
    if notional < float(min_notional):
        raise MinNotionalError(
            f"notional {notional:.12g} < min_notional {float(min_notional):.12g}",
            symbol=None,
            notional=notional,
            required_min_notional=float(min_notional),
            http_status=400,
            binance_code=-1013,
        )


def select_market_step_size(market_lot_step_size: float | None, lot_step_size: float | None) -> float:
    """
    For MARKET orders, prefer MARKET_LOT_SIZE.stepSize, fallback to LOT_SIZE.stepSize.
    """
    if market_lot_step_size is not None and market_lot_step_size > 0:
        return float(market_lot_step_size)
    if lot_step_size is not None and lot_step_size > 0:
        return float(lot_step_size)
    return 0.0


def should_enforce_min_notional_for_market(apply_to_market: bool | None) -> bool:
    """
    Binance MIN_NOTIONAL applyToMarket gate for MARKET orders.
    """
    return bool(apply_to_market)


def backoff_seconds(
    attempt: int,
    base: float = 1.0,
    cap: float = 30.0,
    jitter: str = "full",
) -> float:
    """
    Compute exponential backoff with jitter.

    full jitter:
      sleep = random.uniform(0, min(cap, base * 2**attempt))
    """
    if attempt < 0:
        attempt = 0
    max_sleep = min(float(cap), float(base) * (2.0 ** int(attempt)))
    if max_sleep <= 0:
        return 0.0
    if jitter == "full":
        return float(random.uniform(0.0, max_sleep))
    return max_sleep
