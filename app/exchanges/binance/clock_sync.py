"""Binance clock synchronization safety checks and recalibration flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Protocol

from .models import BinanceAdapterConfig
from .models import BinanceClockCalibrationResult
from .models import BinanceClockStatus
from .models import BinanceServerTimeSample


class BinanceServerTimeTransport(Protocol):
    """Transport boundary for Binance server-time retrieval."""

    def fetch_server_time_sample(self) -> BinanceServerTimeSample:
        """Return one server-time sample for offset evaluation."""


@dataclass(frozen=True)
class BinanceClockSync:
    """Checks timestamp safety before future signed Binance requests.

    Responsibilities:
    - evaluate offset against configured skew tolerance
    - expose time uncertainty explicitly
    - retry/recalibrate from repeated server-time samples
    - provide operator-facing status summaries

    Non-goals:
    - implement the actual Binance network transport
    - hide uncertain clock state behind optimistic defaults
    """

    config: BinanceAdapterConfig

    def check(self, *, server_time_ms: int | None = None, local_time_ms: int | None = None) -> BinanceClockStatus:
        """Return clock status using injected timestamps when provided."""

        if server_time_ms is None or local_time_ms is None:
            return BinanceClockStatus(
                offset_ms=0,
                round_trip_ms=0,
                is_within_tolerance=False,
                checked_at=datetime.now(UTC),
                server_time_ms=server_time_ms,
                local_time_ms=local_time_ms,
                is_uncertain=True,
                source="missing_reference",
                alert="server time reference unavailable",
            )
        offset_ms = server_time_ms - local_time_ms
        return self._status_from_offset(
            offset_ms=offset_ms,
            round_trip_ms=0,
            server_time_ms=server_time_ms,
            local_time_ms=local_time_ms,
            source="direct_check",
        )

    def sample_server_time(
        self,
        *,
        server_time_ms: int,
        local_time_ms: int,
        round_trip_ms: int = 0,
    ) -> BinanceServerTimeSample:
        """Return one server-time sample for later recalibration logic."""

        return BinanceServerTimeSample(
            server_time_ms=server_time_ms,
            local_time_ms=local_time_ms,
            round_trip_ms=round_trip_ms,
        )

    def check_sample(self, sample: BinanceServerTimeSample) -> BinanceClockStatus:
        """Convert one server-time sample into a clock-status decision.

        The offset uses midpoint compensation so long round-trip samples stay
        visibly degraded rather than looking artificially precise.
        """

        adjusted_local_time_ms = sample.local_time_ms + int(sample.round_trip_ms / 2)
        offset_ms = sample.server_time_ms - adjusted_local_time_ms
        return self._status_from_offset(
            offset_ms=offset_ms,
            round_trip_ms=sample.round_trip_ms,
            server_time_ms=sample.server_time_ms,
            local_time_ms=sample.local_time_ms,
            source="server_time_sample",
        )

    def recalibrate(
        self,
        *,
        transport: BinanceServerTimeTransport,
        max_attempts: int = 3,
    ) -> BinanceClockCalibrationResult:
        """Retry server-time sampling and return the best visible clock status."""

        samples: list[BinanceServerTimeSample] = []
        statuses: list[BinanceClockStatus] = []
        alerts: list[str] = []
        for attempt in range(1, max_attempts + 1):
            sample = transport.fetch_server_time_sample()
            samples.append(sample)
            status = self.check_sample(sample)
            statuses.append(
                BinanceClockStatus(
                    offset_ms=status.offset_ms,
                    round_trip_ms=status.round_trip_ms,
                    is_within_tolerance=status.is_within_tolerance,
                    checked_at=status.checked_at,
                    server_time_ms=status.server_time_ms,
                    local_time_ms=status.local_time_ms,
                    is_uncertain=status.is_uncertain,
                    recalibration_attempts=attempt,
                    source="recalibration",
                    alert=status.alert,
                )
            )
            if statuses[-1].is_within_tolerance:
                if attempt > 1:
                    alerts.append(f"clock recalibrated after {attempt} attempt(s)")
                return BinanceClockCalibrationResult(
                    final_status=statuses[-1],
                    samples=tuple(samples),
                    alerts=tuple(alerts),
                )
        best_status = min(statuses, key=lambda status: (abs(status.offset_ms), status.round_trip_ms))
        alerts.append(f"clock remained outside tolerance after {max_attempts} attempt(s)")
        return BinanceClockCalibrationResult(
            final_status=BinanceClockStatus(
                offset_ms=best_status.offset_ms,
                round_trip_ms=best_status.round_trip_ms,
                is_within_tolerance=False,
                checked_at=best_status.checked_at,
                server_time_ms=best_status.server_time_ms,
                local_time_ms=best_status.local_time_ms,
                is_uncertain=True,
                recalibration_attempts=max_attempts,
                source="recalibration",
                alert="time sync uncertain after recalibration attempts",
            ),
            samples=tuple(samples),
            alerts=tuple(alerts),
        )

    def recalibrate_if_needed(
        self,
        *,
        current_status: BinanceClockStatus,
        transport: BinanceServerTimeTransport,
        max_attempts: int = 3,
    ) -> BinanceClockCalibrationResult | None:
        """Retry time sampling only when current drift is unsafe or uncertain."""

        if current_status.is_within_tolerance and not current_status.is_uncertain:
            return None
        return self.recalibrate(transport=transport, max_attempts=max_attempts)

    def render_operator_report(self, status: BinanceClockStatus) -> str:
        """Render a short operator-facing clock status summary."""

        return "\n".join(
            [
                "# Binance Clock Sync",
                f"- source: {status.source}",
                f"- offset_ms: {status.offset_ms}",
                f"- round_trip_ms: {status.round_trip_ms}",
                f"- within_tolerance: {status.is_within_tolerance}",
                f"- is_uncertain: {status.is_uncertain}",
                f"- recalibration_attempts: {status.recalibration_attempts}",
                f"- alert: {status.alert or 'none'}",
            ]
        )

    def _status_from_offset(
        self,
        *,
        offset_ms: int,
        round_trip_ms: int,
        server_time_ms: int | None,
        local_time_ms: int | None,
        source: str,
    ) -> BinanceClockStatus:
        within_tolerance = abs(offset_ms) <= self.config.max_clock_skew_ms
        is_uncertain = not within_tolerance
        alert = None
        if not within_tolerance:
            alert = "clock skew outside configured tolerance"
        return BinanceClockStatus(
            offset_ms=offset_ms,
            round_trip_ms=round_trip_ms,
            is_within_tolerance=within_tolerance,
            checked_at=datetime.now(UTC),
            server_time_ms=server_time_ms,
            local_time_ms=local_time_ms,
            is_uncertain=is_uncertain,
            source=source,
            alert=alert,
        )
