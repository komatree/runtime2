"""Structured runtime observability models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ExchangeHealthState(str, Enum):
    """Operator-facing exchange health severity."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FATAL = "fatal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExchangeComponentHealth:
    """One operator-facing exchange health component."""

    component: str
    state: ExchangeHealthState
    detail: str
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExchangeHealthSnapshot:
    """Unified exchange health surface for operator reporting and gating."""

    venue: str
    generated_at: datetime
    overall_state: ExchangeHealthState
    private_stream: ExchangeComponentHealth
    reconciliation: ExchangeComponentHealth
    clock_sync: ExchangeComponentHealth
    status_query: ExchangeComponentHealth
    alerts: tuple[str, ...] = ()


class RuntimeDegradationFlag(str, Enum):
    """Non-fatal degraded states that operators should still inspect."""

    INDEX_SUITE_MISSING = "index_suite_missing"
    STABLECOIN_MISSING = "stablecoin_missing"
    EXCHANGE_DATA_DEGRADED = "exchange_data_degraded"


@dataclass(frozen=True)
class RuntimeCycleSummary:
    """Compact operator-facing summary for one completed runtime cycle."""

    cycle_id: str
    mode: str
    instrument_id: str
    timeframe: str
    cycle_completed_at: datetime
    bar_close_time: datetime
    feature_snapshot_time: datetime
    signal_count: int
    risk_decision_count: int
    execution_intent_count: int
    persistence_succeeded_at: datetime
    degradation_flags: tuple[RuntimeDegradationFlag, ...]
    alerts: tuple[str, ...]
    exchange_health_state: ExchangeHealthState | None = None


@dataclass(frozen=True)
class RuntimeHealthSnapshot:
    """Latest runtime health/status view written for operators."""

    generated_at: datetime
    mode: str
    last_closed_bar_processed_at: datetime | None
    last_successful_feature_snapshot_at: datetime | None
    last_strategy_evaluation_at: datetime | None
    last_persistence_success_at: datetime | None
    degradation_flags: tuple[RuntimeDegradationFlag, ...]
    latest_cycle_id: str | None
    latest_instrument_id: str | None
    latest_alerts: tuple[str, ...]
    exchange_health: ExchangeHealthSnapshot | None = None
