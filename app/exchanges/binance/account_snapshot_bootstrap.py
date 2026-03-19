"""Signed REST bootstrap of a canonical Binance Spot account snapshot."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from app.contracts import AccountSnapshot
from app.contracts import AssetBalanceSnapshot

from .endpoint_profiles import validate_endpoint_profile
from .models import BinanceAdapterConfig


@dataclass(frozen=True)
class BinanceSignedRestAccountSnapshotBootstrap:
    """Fetch one canonical account snapshot for rehearsal baseline alignment."""

    config: BinanceAdapterConfig
    time_provider: Callable[[], int]
    urlopen_fn: object = urlopen

    def __post_init__(self) -> None:
        validate_endpoint_profile(self.config)

    def fetch_snapshot(self) -> AccountSnapshot:
        timestamp_ms = int(self.time_provider())
        signed_query = {
            "timestamp": str(timestamp_ms),
            "recvWindow": str(self.config.recv_window_ms),
        }
        query_string = urlencode(signed_query)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            url=f"{self.config.rest_base_url.rstrip('/')}/api/v3/account?{query_string}&signature={signature}",
            method="GET",
            headers={"X-MBX-APIKEY": self.config.api_key},
        )
        with self.urlopen_fn(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict):
            raise ValueError("account snapshot bootstrap returned non-object payload")
        balances = payload.get("balances")
        if not isinstance(balances, list):
            raise ValueError("account snapshot bootstrap payload missing balances")
        updated_at = self._parse_event_time(payload.get("updateTime")) or datetime.fromtimestamp(
            timestamp_ms / 1000,
            tz=UTC,
        )
        snapshot_balances = tuple(
            AssetBalanceSnapshot(
                asset=str(balance["asset"]),
                free=Decimal(str(balance["free"])),
                locked=Decimal(str(balance["locked"])),
                updated_at=updated_at,
            )
            for balance in balances
            if isinstance(balance, dict)
            and (
                Decimal(str(balance.get("free", "0"))) > Decimal("0")
                or Decimal(str(balance.get("locked", "0"))) > Decimal("0")
            )
        )
        if not snapshot_balances:
            raise ValueError("account snapshot bootstrap produced no non-zero balances")
        return AccountSnapshot(
            venue="binance",
            account_scope="spot",
            as_of=updated_at,
            balances=snapshot_balances,
            source_event_type="restAccountSnapshot",
            translation_version="binance.account.bootstrap.v1",
            is_partial=False,
        )

    def _parse_event_time(self, raw_value: object) -> datetime | None:
        try:
            if raw_value in (None, ""):
                return None
            return datetime.fromtimestamp(int(raw_value) / 1000, tz=UTC)
        except (TypeError, ValueError):
            return None
