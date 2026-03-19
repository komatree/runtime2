from __future__ import annotations

import os

from bot.exchange.base import BaseExchange
from bot.exchange.binance_spot import BinanceSpotExchange
from bot.exchange.mock import MockExchange

DEFAULT_BINANCE_BASE_URL = "https://api.binance.com"


def _is_real_mode(value: str | None) -> bool:
    raw = (value or "dry").strip().lower()
    return raw in {"real", "live", "prod", "production"}


def build_exchange_from_env() -> BaseExchange:
    provider = (os.getenv("EXCHANGE_PROVIDER", "mock") or "mock").strip().lower()
    mode = os.getenv("EXCHANGE_MODE", "dry")
    quote = (os.getenv("EXCHANGE_QUOTE", "") or "").strip().upper()

    if provider == "mock":
        seed_raw = os.getenv("EXCHANGE_MOCK_SEED", "42")
        try:
            seed = int(seed_raw)
        except ValueError:
            seed = 42
        mock_quote = quote or "KRW"
        return MockExchange(seed=seed, quote=mock_quote)

    if provider == "binance_spot":
        api_key = (os.getenv("BINANCE_API_KEY", "") or "").strip()
        api_secret = (os.getenv("BINANCE_API_SECRET", "") or "").strip()
        # Testnet URL must be injected by runner scripts, not factory defaults.
        base_url = (os.getenv("BINANCE_BASE_URL", DEFAULT_BINANCE_BASE_URL) or DEFAULT_BINANCE_BASE_URL).strip()
        if not api_key:
            raise ValueError("BINANCE_API_KEY is required for EXCHANGE_PROVIDER=binance_spot")
        if not api_secret:
            raise ValueError("BINANCE_API_SECRET is required for EXCHANGE_PROVIDER=binance_spot")
        return BinanceSpotExchange(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            dry_run=not _is_real_mode(mode),
            quote=quote or "USDT",
        )

    raise ValueError(f"Unsupported EXCHANGE_PROVIDER: {provider}")
