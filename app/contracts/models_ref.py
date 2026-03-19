from dataclasses import dataclass
from datetime import datetime
from typing import Any
from typing import Literal

SignalSide = Literal["buy", "sell", "flat"]
OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["new", "filled", "cancelled", "partial"]
HedgeState = Literal["OFF", "ARMED", "ON", "COOLDOWN"]


@dataclass(frozen=True)
class Candle:
    """Market OHLCV data for a symbol at a specific timestamp."""

    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    """Strategy output indicating desired directional bias and confidence."""

    symbol: str
    ts: datetime
    side: SignalSide
    strength: float
    reason: str
    strategy_name: str


@dataclass(frozen=True)
class Order:
    """Order request/record with exchange-facing execution details."""

    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    price: float
    type: OrderType
    status: OrderStatus
    ts: datetime
    tag: str = ""
    reason_code: str = ""


@dataclass(frozen=True)
class Fill:
    """Executed trade fill details for an order."""

    order_id: str
    symbol: str
    qty: float
    price: float
    fee: float
    ts: datetime


@dataclass(frozen=True)
class SymbolScore:
    """Per-symbol ranking score used by symbol selection."""

    symbol: str
    ts: datetime
    score: float
    reason: str
    model_name: str
    selected: bool


@dataclass(frozen=True)
class HedgeEvent:
    """State transition/event record for defensive BTC hedge control."""

    ts: datetime
    state: HedgeState
    hedge_ratio: float
    risk_score: float
    reason_json: dict[str, Any]
    btc_price: float | None = None
