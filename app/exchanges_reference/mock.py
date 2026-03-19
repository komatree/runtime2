from datetime import datetime, timezone
from random import Random

from bot.config import FEE_RATE, ORDER_QUOTE_AMOUNT
from bot.exchange.base import BaseExchange
from bot.models import Fill, Order


class MockExchange(BaseExchange):
    def __init__(self, seed: int = 42, quote: str = "KRW") -> None:
        self._quote = quote
        self._rng = Random(seed)
        self._prices: dict[str, float] = {
            "BTC": 100_000_000.0,
            "ETH": 5_000_000.0,
            "SOL": 200_000.0,
        }
        self._balances: dict[str, float] = {
            self._quote: 1_000_000.0,
            "BTC": 0.0,
            "ETH": 0.0,
            "SOL": 0.0,
        }

    def get_price(self, symbol: str) -> float:
        current = self._prices.get(symbol, 100_000.0)
        # Small deterministic random walk per call.
        drift = self._rng.uniform(-0.005, 0.005)
        next_price = max(1.0, current * (1.0 + drift))
        self._prices[symbol] = next_price
        return next_price

    def place_order(self, order: Order) -> Fill:
        base_asset = order.symbol
        quote_asset = self._quote

        if order.side == "buy":
            qty = ORDER_QUOTE_AMOUNT / order.price
            fee = qty * order.price * FEE_RATE
            total_cost = qty * order.price + fee
            if self.get_balance(quote_asset) < total_cost:
                raise ValueError("insufficient quote balance")
            self._balances[quote_asset] -= total_cost
            self._balances[base_asset] = self.get_balance(base_asset) + qty
        else:
            qty = order.qty
            fee = qty * order.price * FEE_RATE
            if self.get_balance(base_asset) < qty:
                raise ValueError("insufficient base balance")
            proceeds = qty * order.price - fee
            self._balances[base_asset] -= qty
            self._balances[quote_asset] += proceeds

        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            qty=qty,
            price=order.price,
            fee=fee,
            ts=datetime.now(timezone.utc),
        )

    def get_balance(self, asset: str) -> float:
        return self._balances.get(asset, 0.0)

    def quote_currency(self) -> str:
        return self._quote
