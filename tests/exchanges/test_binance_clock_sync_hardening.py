"""Binance clock sync hardening tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from app.exchanges.binance import BinanceAdapterConfig
from app.exchanges.binance import BinanceClockSync
from app.exchanges.binance import BinanceServerTimeSample
from app.monitoring.exchange_health import BinanceExchangeHealthService
from app.monitoring.models import ExchangeHealthState


def test_positive_500ms_drift_stays_safe_without_recalibration() -> None:
    sync = BinanceClockSync(_config())

    status = sync.check(server_time_ms=10_500, local_time_ms=10_000)
    recalibration = sync.recalibrate_if_needed(
        current_status=status,
        transport=_FakeClockTransport(
            samples=(BinanceServerTimeSample(server_time_ms=10_500, local_time_ms=10_000, round_trip_ms=0),)
        ),
        max_attempts=2,
    )

    assert status.offset_ms == 500
    assert status.is_within_tolerance is True
    assert status.is_uncertain is False
    assert recalibration is None


def test_negative_500ms_drift_stays_safe_without_recalibration() -> None:
    sync = BinanceClockSync(_config())

    status = sync.check(server_time_ms=9_500, local_time_ms=10_000)
    recalibration = sync.recalibrate_if_needed(
        current_status=status,
        transport=_FakeClockTransport(
            samples=(BinanceServerTimeSample(server_time_ms=9_500, local_time_ms=10_000, round_trip_ms=0),)
        ),
        max_attempts=2,
    )

    assert status.offset_ms == -500
    assert status.is_within_tolerance is True
    assert status.is_uncertain is False
    assert recalibration is None


def test_recalibration_converges_after_drifted_first_attempt() -> None:
    sync = BinanceClockSync(_config())
    transport = _FakeClockTransport(
        samples=(
            BinanceServerTimeSample(server_time_ms=10_000, local_time_ms=8_400, round_trip_ms=40),
            BinanceServerTimeSample(server_time_ms=12_000, local_time_ms=11_250, round_trip_ms=20),
        )
    )

    initial = sync.check_sample(transport.samples[0])
    recalibrated = sync.recalibrate_if_needed(
        current_status=initial,
        transport=transport,
        max_attempts=3,
    )

    assert initial.is_within_tolerance is False
    assert recalibrated is not None
    assert recalibrated.final_status.is_within_tolerance is True
    assert recalibrated.final_status.recalibration_attempts == 2
    assert "recalibrated after 2 attempt(s)" in recalibrated.alerts[0]


def test_recalibration_marks_time_sync_uncertain_when_drift_persists() -> None:
    sync = BinanceClockSync(_config())
    transport = _FakeClockTransport(
        samples=(
            BinanceServerTimeSample(server_time_ms=10_000, local_time_ms=8_000, round_trip_ms=30),
            BinanceServerTimeSample(server_time_ms=12_000, local_time_ms=10_400, round_trip_ms=50),
            BinanceServerTimeSample(server_time_ms=14_000, local_time_ms=12_650, round_trip_ms=30),
        )
    )

    result = sync.recalibrate(transport=transport, max_attempts=3)
    report = sync.render_operator_report(result.final_status)

    assert result.final_status.is_within_tolerance is False
    assert result.final_status.is_uncertain is True
    assert result.final_status.recalibration_attempts == 3
    assert result.final_status.alert == "time sync uncertain after recalibration attempts"
    assert "clock remained outside tolerance after 3 attempt(s)" in result.alerts[0]
    assert "is_uncertain: True" in report


def test_sudden_exchange_time_jump_triggers_recalibration_and_recovers() -> None:
    sync = BinanceClockSync(_config())
    transport = _FakeClockTransport(
        samples=(
            BinanceServerTimeSample(server_time_ms=15_000, local_time_ms=13_100, round_trip_ms=50),
            BinanceServerTimeSample(server_time_ms=15_500, local_time_ms=14_700, round_trip_ms=20),
        )
    )

    initial = sync.check_sample(transport.samples[0])
    recalibrated = sync.recalibrate_if_needed(
        current_status=initial,
        transport=transport,
        max_attempts=3,
    )

    assert initial.is_within_tolerance is False
    assert initial.is_uncertain is True
    assert recalibrated is not None
    assert recalibrated.final_status.is_within_tolerance is True
    assert recalibrated.final_status.recalibration_attempts == 2


def test_local_ntp_skew_remains_fatal_in_exchange_health_when_recalibration_fails() -> None:
    sync = BinanceClockSync(_config())
    transport = _FakeClockTransport(
        samples=(
            BinanceServerTimeSample(server_time_ms=20_000, local_time_ms=17_800, round_trip_ms=40),
            BinanceServerTimeSample(server_time_ms=22_000, local_time_ms=19_850, round_trip_ms=30),
            BinanceServerTimeSample(server_time_ms=24_000, local_time_ms=21_900, round_trip_ms=20),
        )
    )

    current_status = sync.check(
        server_time_ms=20_000,
        local_time_ms=17_500,
    )
    recalibrated = sync.recalibrate_if_needed(
        current_status=current_status,
        transport=transport,
        max_attempts=3,
    )
    assert recalibrated is not None

    snapshot = BinanceExchangeHealthService().build_snapshot(
        clock_status=recalibrated.final_status,
        generated_at=datetime(2026, 3, 14, 0, 0, tzinfo=UTC),
    )

    assert recalibrated.final_status.is_uncertain is True
    assert recalibrated.final_status.alert == "time sync uncertain after recalibration attempts"
    assert snapshot.clock_sync.state is ExchangeHealthState.FATAL
    assert snapshot.overall_state is ExchangeHealthState.FATAL
    assert snapshot.clock_sync.detail == "clock sync uncertain or out of tolerance"


@dataclass
class _FakeClockTransport:
    samples: tuple[BinanceServerTimeSample, ...]
    index: int = 0

    def fetch_server_time_sample(self) -> BinanceServerTimeSample:
        sample = self.samples[self.index]
        if self.index < len(self.samples) - 1:
            self.index += 1
        return sample


def _config() -> BinanceAdapterConfig:
    return BinanceAdapterConfig(
        rest_base_url="https://api.binance.com",
        websocket_base_url="wss://stream.binance.com:9443",
        recv_window_ms=5000,
        max_clock_skew_ms=1000,
        allow_order_submission=False,
    )
