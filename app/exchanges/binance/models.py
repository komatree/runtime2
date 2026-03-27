"""Binance adapter models and explicit pre-live constraints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.contracts import AccountSnapshot
from app.contracts import BarSlice
from app.contracts import Candle
from app.contracts import FillEvent
from app.contracts import OrderState


class BinanceErrorCategory(str, Enum):
    """Normalized error classification hooks for adapter-level handling."""

    AUTH = "auth"
    CLOCK_SKEW = "clock_skew"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_NETWORK = "transient_network"
    ORDER_REJECT = "order_reject"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BinanceEndpointProfile:
    """Allowed endpoint profile for one Binance environment."""

    name: str
    allowed_rest_hosts: tuple[str, ...]
    allowed_websocket_hosts: tuple[str, ...]
    signed_query_enabled: bool = True
    private_stream_enabled: bool = True


class BinanceRecoveryAction(str, Enum):
    """Next action for recovery when reconciliation confidence is insufficient."""

    NONE = "none"
    QUERY_ORDER_STATUS = "query_order_status"
    QUERY_OPEN_ORDERS = "query_open_orders"
    HOLD_PORTFOLIO_MUTATION = "hold_portfolio_mutation"
    ESCALATE_OPERATOR = "escalate_operator"


class BinanceRecoveryConvergenceState(str, Enum):
    """Inspectable recovery convergence state for one order-tracking workflow."""

    PENDING = "pending"
    CONVERGED_TERMINAL = "converged_terminal"
    UNRECONCILED_MANUAL_ATTENTION = "unreconciled_manual_attention"


class BinanceRecoveryTriggerReason(str, Enum):
    """Explicit trigger reason for automatic reconciliation recovery."""

    NOT_REQUIRED = "not_required"
    MISSING_PRIVATE_UPDATES = "missing_private_updates"
    PRIVATE_STREAM_GAP = "private_stream_gap"
    RESTART_RESUME = "restart_resume"
    UNKNOWN_EXECUTION = "unknown_execution"


class BinancePublicStreamState(str, Enum):
    """Observed state of the public market-data websocket path."""

    CONNECTING = "connecting"
    STREAMING = "streaming"
    DEGRADED = "degraded"
    FAILOVER_REST = "failover_rest"
    SESSION_ROLLOVER = "session_rollover"


class BinancePrivateStreamState(str, Enum):
    """Observed state of the authenticated private websocket path."""

    INITIALIZING = "initializing"
    AUTHENTICATED = "authenticated"
    SUBSCRIBED = "subscribed"
    STREAMING = "streaming"
    DEGRADED = "degraded"
    SESSION_ROLLOVER = "session_rollover"
    TERMINATED = "terminated"
    SHUTDOWN = "shutdown"


class BinancePrivateEventFamily(str, Enum):
    """Normalized private event families consumed inside the adapter boundary."""

    ORDER_UPDATE = "order_update"
    ACCOUNT_UPDATE = "account_update"
    STREAM_STATUS = "stream_status"


class BinancePrivateTranslationStatus(str, Enum):
    """Outcome of one raw private payload translation pass."""

    TRANSLATED = "translated"
    IGNORED = "ignored"
    MALFORMED = "malformed"


class BinanceStatusQueryState(str, Enum):
    """Observed state of signed REST order-status lookup attempts."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class BinanceClientError:
    """Normalized adapter error for retries, alerts, and operator reporting."""

    category: BinanceErrorCategory
    message: str
    retryable: bool
    raw_code: str | None = None
    http_status: int | None = None
    retry_after_seconds: float | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class BinanceAdapterConfig:
    """Static configuration for Binance adapter construction.

    Responsibilities:
    - Separate REST and websocket endpoints
    - Explicit recv-window and clock skew guardrails
    - Pre-live gating flags for incomplete trading features
    """

    rest_base_url: str
    websocket_base_url: str
    api_key: str = ""
    api_secret: str = ""
    recv_window_ms: int = 5000
    max_clock_skew_ms: int = 1000
    allow_order_submission: bool = False
    endpoint_profile_name: str = "binance_spot_prod"
    request_weight_limit_per_minute: int = 1200


@dataclass(frozen=True)
class BinanceSymbolMapping:
    """Canonical-to-Binance symbol mapping kept inside the adapter layer."""

    instrument_id: str
    venue_symbol: str


@dataclass(frozen=True)
class BinanceClockStatus:
    """Observed local-vs-venue clock relationship used for safety decisions."""

    offset_ms: int
    round_trip_ms: int
    is_within_tolerance: bool
    checked_at: datetime
    server_time_ms: int | None = None
    local_time_ms: int | None = None
    is_uncertain: bool = False
    recalibration_attempts: int = 0
    source: str = "direct_check"
    alert: str | None = None


@dataclass(frozen=True)
class BinanceServerTimeSample:
    """Placeholder sample for Binance server-time retrieval."""

    server_time_ms: int
    local_time_ms: int
    round_trip_ms: int


@dataclass(frozen=True)
class BinanceClockCalibrationResult:
    """Operator-visible recalibration outcome across one or more time samples."""

    final_status: BinanceClockStatus
    samples: tuple[BinanceServerTimeSample, ...]
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinanceRequestWeightSnapshot:
    """Operator-visible request-weight state for REST control-plane traffic."""

    used_weight: int
    max_weight: int
    remaining_weight: int
    window_started_at: datetime
    endpoint: str | None = None
    is_throttled: bool = False
    alert: str | None = None


@dataclass(frozen=True)
class BinancePrivateStreamEvent:
    """Normalized private-stream event metadata.

    This remains adapter-internal until translated into canonical contracts like
    `OrderState` or `FillEvent`.
    """

    event_type: str
    event_family: BinancePrivateEventFamily
    event_time: datetime
    account_scope: str
    sequence_id: str | None = None
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    payload_summary: dict[str, str] | None = None


@dataclass(frozen=True)
class BinancePrivateStreamBatch:
    """Batch returned by a placeholder private-stream ingestion step."""

    events: tuple[BinancePrivateStreamEvent, ...]
    source: str
    cursor: str | None = None
    has_gap: bool = False
    alerts: tuple[str, ...] = ()
    stream_state: BinancePrivateStreamState = BinancePrivateStreamState.STREAMING
    family_counts: dict[str, int] | None = None
    last_event_time: datetime | None = None
    last_sequence_id: str | None = None


@dataclass(frozen=True)
class BinancePrivateStreamSubscription:
    """Transport-local authenticated subscription receipt.

    This is the adapter-local result of the current Binance Spot user data
    stream subscription flow. It replaces the older listenKey bootstrap
    assumption with an explicit authenticated subscription outcome.
    """

    subscription_id: str
    stream_key: str
    bootstrap_method: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class BinancePrivateStreamSession:
    """Authenticated private-stream session metadata."""

    stream_key: str
    state: BinancePrivateStreamState
    account_scope: str
    started_at: datetime
    expires_at: datetime | None = None
    connection_id: str | None = None
    subscription_id: str | None = None
    bootstrap_method: str = "userDataStream.subscribe.signature"
    last_message_at: datetime | None = None
    last_keepalive_at: datetime | None = None
    reconnect_attempts: int = 0
    alerts: tuple[str, ...] = ()

    @property
    def listen_key(self) -> str:
        """Compatibility alias for older test and reporting helpers.

        The private stream now bootstraps from a WS-API subscription rather than
        a REST listenKey. This property remains only so older adapter-local
        helpers can read the current stream/session key without leaking the old
        bootstrap model into runtime contracts.
        """

        return self.stream_key


@dataclass(frozen=True)
class BinancePrivateStreamHealth:
    """Operator-visible health for the private websocket lifecycle."""

    state: BinancePrivateStreamState
    reconnect_attempts: int
    last_message_at: datetime | None = None
    last_reconnect_at: datetime | None = None
    session_expires_at: datetime | None = None
    is_authoritative: bool = False
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinanceAccountSyncSummary:
    """Normalized account/balance update summary for portfolio sync wiring."""

    account_scope: str
    event_time: datetime
    updated_assets: tuple[str, ...]
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinancePrivatePayloadTranslation:
    """Canonical result of translating one Binance private payload.

    This is the authoritative bridge from Binance-native private payloads into
    internal runtime models. Raw exchange field names stop at this boundary.
    """

    translation_version: str
    status: BinancePrivateTranslationStatus
    source_event_type: str
    event_family: BinancePrivateEventFamily
    occurred_at: datetime | None
    order_state: OrderState | None = None
    fill_event: FillEvent | None = None
    account_snapshot: AccountSnapshot | None = None
    stream_invalidated: bool = False
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinanceStatusQueryHealth:
    """Operator-visible summary of one signed order-status lookup attempt."""

    lookup_field: str
    lookup_value: str
    state: BinanceStatusQueryState
    checked_at: datetime
    transport: str
    http_status: int | None = None
    alert: str | None = None
    request_weight_used: int | None = None
    request_weight_limit: int | None = None
    endpoint_profile_name: str | None = None


@dataclass(frozen=True)
class BinanceOrderLookupResult:
    """Result of placeholder order lookup by client id or exchange id."""

    found: bool
    lookup_field: str
    lookup_value: str
    source: str
    status_summary: str | None = None
    alert: str | None = None
    recovered_order_state: OrderState | None = None
    recovered_fill_events: tuple[FillEvent, ...] = ()
    attempt_number: int = 1


@dataclass(frozen=True)
class BinanceReportOnlyMarketContext:
    """Closed execution/context candle inputs for report-only runtime cycles."""

    execution_bar_slice: BarSlice
    context_bar_slice: BarSlice


@dataclass(frozen=True)
class BinanceKlineStreamMessage:
    """Normalized Binance public kline stream payload."""

    venue_symbol: str
    timeframe: str
    event_time: datetime
    candle: Candle
    is_closed_bar: bool


@dataclass(frozen=True)
class BinanceMarketDataHealth:
    """Operator-visible status for the public websocket market-data path."""

    state: BinancePublicStreamState
    reconnect_attempts: int
    failover_active: bool
    last_heartbeat_at: datetime | None = None
    last_message_at: datetime | None = None
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinancePublicMarketDataEvent:
    """Normalized public market-data event after websocket parsing."""

    event_type: str
    venue_symbol: str | None = None
    timeframe: str | None = None
    kline: BinanceKlineStreamMessage | None = None
    health: BinanceMarketDataHealth | None = None
    alerts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BinanceOrderReconciliationResult:
    """Reconciliation summary before canonical portfolio updates occur."""

    matched_order_ids: tuple[str, ...]
    missing_order_ids: tuple[str, ...]
    unknown_execution_ids: tuple[str, ...]
    alerts: tuple[str, ...]
    unknown_execution_client_order_ids: tuple[str, ...] = ()
    unknown_execution_exchange_only_ids: tuple[str, ...] = ()
    recovery_actions: tuple[BinanceRecoveryAction, ...] = ()


@dataclass(frozen=True)
class BinanceRecoveryPlan:
    """Recovery plan for unknown execution or stream/status divergence."""

    reason: str
    actions: tuple[BinanceRecoveryAction, ...]
    order_lookup_requests: tuple[tuple[str, str], ...] = ()
    alerts: tuple[str, ...] = ()
    trigger_reason: BinanceRecoveryTriggerReason = BinanceRecoveryTriggerReason.NOT_REQUIRED
    automatic_triggered: bool = False
    gap_detected: bool = False
    resumed_from_snapshot: bool = False


@dataclass(frozen=True)
class BinanceRecoverySummary:
    """Per-order reconciliation convergence summary for operator review."""

    order_id: str
    attempts: int
    convergence_state: BinanceRecoveryConvergenceState
    last_lookup_field: str | None = None
    last_lookup_source: str | None = None
    terminal_status: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class BinancePreLiveBlocker:
    """Explicit blocker record for production trading readiness reviews."""

    area: str
    blocker: str
    mitigation: str
    is_resolved: bool = False
