"""Binance endpoint profile validation for environment isolation."""

from __future__ import annotations

from urllib.parse import urlparse

from .models import BinanceAdapterConfig
from .models import BinanceEndpointProfile


_PROFILES: dict[str, BinanceEndpointProfile] = {
    "binance_spot_prod": BinanceEndpointProfile(
        name="binance_spot_prod",
        allowed_rest_hosts=("api.binance.com",),
        allowed_websocket_hosts=("stream.binance.com",),
    ),
    "binance_spot_testnet": BinanceEndpointProfile(
        name="binance_spot_testnet",
        allowed_rest_hosts=("testnet.binance.vision",),
        allowed_websocket_hosts=("stream.testnet.binance.vision",),
    ),
}


def resolve_endpoint_profile(name: str) -> BinanceEndpointProfile:
    """Return the configured endpoint profile or raise on unknown profiles."""

    try:
        return _PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown Binance endpoint profile: {name}") from exc


def validate_endpoint_profile(config: BinanceAdapterConfig) -> BinanceEndpointProfile:
    """Fail closed when configured REST and websocket hosts do not match the profile."""

    profile = resolve_endpoint_profile(config.endpoint_profile_name)
    rest_host = (urlparse(config.rest_base_url).hostname or "").lower()
    websocket_host = (urlparse(config.websocket_base_url).hostname or "").lower()
    if rest_host not in profile.allowed_rest_hosts:
        raise ValueError(
            "configured Binance REST host does not match endpoint profile "
            f"{profile.name}: {rest_host}"
        )
    if websocket_host not in profile.allowed_websocket_hosts:
        raise ValueError(
            "configured Binance websocket host does not match endpoint profile "
            f"{profile.name}: {websocket_host}"
        )
    return profile
