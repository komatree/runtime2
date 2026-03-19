"""Request-weight aware throttling for Binance REST control-plane calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Mapping

from .models import BinanceRequestWeightSnapshot


@dataclass
class BinanceRequestWeightTracker:
    """Track request-weight usage conservatively and fail closed when exhausted."""

    max_weight: int
    window: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        self._used_weight = 0
        self._window_started_at: datetime | None = None
        self._last_snapshot: BinanceRequestWeightSnapshot | None = None

    def consume(
        self,
        *,
        endpoint: str,
        weight: int,
        occurred_at: datetime | None = None,
    ) -> BinanceRequestWeightSnapshot:
        """Reserve request weight before a REST call."""

        now = occurred_at or datetime.now(UTC)
        self._roll_window(now=now)
        next_weight = self._used_weight + weight
        if next_weight > self.max_weight:
            snapshot = BinanceRequestWeightSnapshot(
                used_weight=self._used_weight,
                max_weight=self.max_weight,
                remaining_weight=max(self.max_weight - self._used_weight, 0),
                window_started_at=self._window_started_at or now,
                endpoint=endpoint,
                is_throttled=True,
                alert=f"request-weight budget exceeded before {endpoint}",
            )
            self._last_snapshot = snapshot
            return snapshot
        self._used_weight = next_weight
        snapshot = BinanceRequestWeightSnapshot(
            used_weight=self._used_weight,
            max_weight=self.max_weight,
            remaining_weight=max(self.max_weight - self._used_weight, 0),
            window_started_at=self._window_started_at or now,
            endpoint=endpoint,
        )
        self._last_snapshot = snapshot
        return snapshot

    def observe_response_headers(
        self,
        *,
        headers: Mapping[str, str] | None,
        endpoint: str,
        occurred_at: datetime | None = None,
    ) -> BinanceRequestWeightSnapshot | None:
        """Update usage from Binance weight headers when available."""

        if not headers:
            return self._last_snapshot
        now = occurred_at or datetime.now(UTC)
        self._roll_window(now=now)
        lowered = {key.lower(): value for key, value in headers.items()}
        header_value = lowered.get("x-mbx-used-weight-1m")
        if header_value is None:
            return self._last_snapshot
        try:
            used_weight = int(header_value)
        except ValueError:
            return self._last_snapshot
        self._used_weight = max(self._used_weight, used_weight)
        snapshot = BinanceRequestWeightSnapshot(
            used_weight=self._used_weight,
            max_weight=self.max_weight,
            remaining_weight=max(self.max_weight - self._used_weight, 0),
            window_started_at=self._window_started_at or now,
            endpoint=endpoint,
            is_throttled=self._used_weight >= self.max_weight,
            alert=(
                f"request-weight budget exhausted after {endpoint}"
                if self._used_weight >= self.max_weight
                else None
            ),
        )
        self._last_snapshot = snapshot
        return snapshot

    def latest_snapshot(self) -> BinanceRequestWeightSnapshot | None:
        """Return the latest known request-weight state."""

        return self._last_snapshot

    def _roll_window(self, *, now: datetime) -> None:
        if self._window_started_at is None or now - self._window_started_at >= self.window:
            self._window_started_at = now
            self._used_weight = 0
