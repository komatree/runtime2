from abc import ABC, abstractmethod

from bot.models import Fill, Order


class BaseExchange(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: Order) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self, asset: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def quote_currency(self) -> str:
        raise NotImplementedError


# Backward-compatible alias for older imports.
Exchange = BaseExchange
