"""Canonical runtime contracts for candle-based trading workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_aware_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be normalized to UTC")


def _require_non_negative(value: Decimal, field_name: str) -> None:
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


def _require_probability(value: Decimal, field_name: str) -> None:
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be within [0, 1]")


class SignalSide(str, Enum):
    """Venue-neutral directional preference emitted by a strategy."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


class RiskDecisionStatus(str, Enum):
    """Allowed outcomes after risk policy evaluation."""

    ALLOW = "allow"
    ADJUST = "adjust"
    REJECT = "reject"


class OrderSide(str, Enum):
    """Canonical execution side understood by execution and exchange layers."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Canonical order style requested from the execution layer."""

    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    """Execution validity window independent of venue-specific API fields."""

    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    POST_ONLY = "post_only"


class OrderStatus(str, Enum):
    """Canonical order lifecycle status after venue normalization."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    RECOVERING = "recovering"
    UNRECONCILED = "unreconciled"


class ReconciliationState(str, Enum):
    """Canonical reconciliation workflow state for order recovery."""

    SUBMIT_SENT = "submit_sent"
    UNKNOWN_EXECUTION = "unknown_execution"
    STATUS_QUERY_PENDING = "status_query_pending"
    RECOVERED_TERMINAL_STATE = "recovered_terminal_state"
    UNRECONCILED_MANUAL_ATTENTION = "unreconciled_manual_attention"


class LiquidityRole(str, Enum):
    """Liquidity interaction role reported for a fill after normalization."""

    MAKER = "maker"
    TAKER = "taker"
    UNKNOWN = "unknown"


class DataQualityState(str, Enum):
    """Canonical data quality and freshness states across runtime inputs."""

    MISSING_DATA = "missing_data"
    STALE_DATA = "stale_data"
    VERSION_MISMATCH = "version_mismatch"
    INCOMPLETE_BAR = "incomplete_bar"
    TIME_SYNC_UNCERTAIN = "time_sync_uncertain"


@dataclass(frozen=True)
class Instrument:
    """Tradable instrument metadata used by strategy, risk, and execution layers.

    Invariants:
    - `instrument_id`, `base_asset`, and `quote_asset` are canonical identifiers.
    - Precision fields are non-negative integers.
    - Tick/step constraints are venue-neutral execution hints when known.
    - Minimum quantity and notional constraints, when present, are non-negative.
    """

    instrument_id: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    price_increment: Decimal | None = None
    quantity_increment: Decimal | None = None
    min_quantity: Decimal | None = None
    min_notional: Decimal | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.base_asset, "base_asset")
        _require_non_empty(self.quote_asset, "quote_asset")
        if self.price_precision < 0:
            raise ValueError("price_precision must be non-negative")
        if self.quantity_precision < 0:
            raise ValueError("quantity_precision must be non-negative")
        if self.price_increment is not None and self.price_increment <= Decimal("0"):
            raise ValueError("price_increment must be positive when provided")
        if self.quantity_increment is not None and self.quantity_increment <= Decimal("0"):
            raise ValueError("quantity_increment must be positive when provided")
        if self.min_quantity is not None:
            _require_non_negative(self.min_quantity, "min_quantity")
        if self.min_notional is not None:
            _require_non_negative(self.min_notional, "min_notional")


@dataclass(frozen=True)
class VenueProfile:
    """Venue capability and account policy metadata owned by edge adapters.

    Invariants:
    - Fields describe normalized venue capabilities rather than raw API payloads.
    - Fee values are represented in basis points and are non-negative.
    - Capability fields remain generic enough to map Binance, Upbit, Bybit, KuCoin, and Bithumb.
    - Strategy code should not depend on this contract directly.
    """

    venue: str
    account_scope: str
    maker_fee_bps: Decimal
    taker_fee_bps: Decimal
    supports_market_orders: bool
    supports_post_only: bool
    default_time_in_force: TimeInForce
    supports_reduce_only: bool = False
    supports_client_order_ids: bool = True
    supported_time_in_force: tuple[TimeInForce, ...] = ()
    max_requests_per_second: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.venue, "venue")
        _require_non_empty(self.account_scope, "account_scope")
        _require_non_negative(self.maker_fee_bps, "maker_fee_bps")
        _require_non_negative(self.taker_fee_bps, "taker_fee_bps")
        if self.supported_time_in_force:
            for value in self.supported_time_in_force:
                if not isinstance(value, TimeInForce):
                    raise TypeError("supported_time_in_force must contain TimeInForce values")
            if self.default_time_in_force not in self.supported_time_in_force:
                raise ValueError("default_time_in_force must be included in supported_time_in_force")
        if self.max_requests_per_second is not None and self.max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be positive when provided")


@dataclass(frozen=True)
class Candle:
    """Canonical OHLCV candle used as the primary strategy input.

    Invariants:
    - Timestamps are UTC-aware and `open_time < close_time`.
    - `high` is not lower than `open`, `close`, or `low`.
    - `low` is not higher than `open`, `close`, or `high`.
    - Volume fields and trade counts are non-negative.
    """

    instrument_id: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    trade_count: int = 0
    is_closed: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _require_aware_utc(self.open_time, "open_time")
        _require_aware_utc(self.close_time, "close_time")
        if self.open_time >= self.close_time:
            raise ValueError("open_time must be earlier than close_time")
        for field_name in ("open", "high", "low", "close", "volume"):
            _require_non_negative(getattr(self, field_name), field_name)
        if self.quote_volume is not None:
            _require_non_negative(self.quote_volume, "quote_volume")
        if self.trade_count < 0:
            raise ValueError("trade_count must be non-negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, close, and high")


@dataclass(frozen=True)
class BarSlice:
    """Ordered candle window consumed by feature pipelines and strategies.

    Invariants:
    - All candles reference the same instrument and timeframe.
    - Candles are strictly ordered by `open_time`.
    - `end_time` equals the latest candle close time in the slice.
    """

    instrument_id: str
    timeframe: str
    end_time: datetime
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _require_aware_utc(self.end_time, "end_time")
        if not self.candles:
            raise ValueError("candles must contain at least one candle")
        previous_open_time: datetime | None = None
        for candle in self.candles:
            if candle.instrument_id != self.instrument_id:
                raise ValueError("all candles must share instrument_id")
            if candle.timeframe != self.timeframe:
                raise ValueError("all candles must share timeframe")
            if previous_open_time is not None and candle.open_time <= previous_open_time:
                raise ValueError("candles must be ordered by increasing open_time")
            previous_open_time = candle.open_time
        if self.end_time != self.candles[-1].close_time:
            raise ValueError("end_time must equal the last candle close_time")


@dataclass(frozen=True)
class IndexSnapshot:
    """Snapshot of a derived market index used for regime and routing decisions.

    Invariants:
    - Snapshot time is UTC-aware.
    - `value` is non-negative.
    - Constituents list canonical instrument identifiers only.
    - `index_version` is explicit so read-only consumers can reject mismatches.
    """

    name: str
    instrument_id: str
    index_version: str
    as_of: datetime
    value: Decimal
    constituents: tuple[str, ...]
    methodology: str

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.index_version, "index_version")
        _require_aware_utc(self.as_of, "as_of")
        _require_non_negative(self.value, "value")
        _require_non_empty(self.methodology, "methodology")
        if not self.constituents:
            raise ValueError("constituents must contain at least one instrument")
        for constituent in self.constituents:
            _require_non_empty(constituent, "constituent")


@dataclass(frozen=True)
class StablecoinSnapshot:
    """Normalized stablecoin observability snapshot produced by report-only inputs.

    Invariants:
    - `pair`, `reference_asset`, `snapshot_version`, and `source_type` are explicit identifiers.
    - Freshness is explicit via `source_fresh_until`.
    - Observability fields are descriptive report inputs, not direct trading signals.
    """

    pair: str
    reference_asset: str
    snapshot_version: str
    source_type: str
    as_of: datetime
    source_fresh_until: datetime
    stablecoin_net_mint_24h: Decimal
    stablecoin_net_burn_24h: Decimal
    stablecoin_supply_change_pct_24h: Decimal
    stablecoin_chain_supply_delta_24h: Decimal
    stablecoin_abnormal_transfer_count: int
    price: Decimal | None = None
    premium_bps: Decimal | None = None
    volume_24h: Decimal | None = None
    liquidity_score: Decimal | None = None
    is_depegged: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.pair, "pair")
        _require_non_empty(self.reference_asset, "reference_asset")
        _require_non_empty(self.snapshot_version, "snapshot_version")
        _require_non_empty(self.source_type, "source_type")
        _require_aware_utc(self.as_of, "as_of")
        _require_aware_utc(self.source_fresh_until, "source_fresh_until")
        _require_non_negative(self.stablecoin_net_mint_24h, "stablecoin_net_mint_24h")
        _require_non_negative(self.stablecoin_net_burn_24h, "stablecoin_net_burn_24h")
        if self.stablecoin_abnormal_transfer_count < 0:
            raise ValueError("stablecoin_abnormal_transfer_count must be non-negative")
        if self.price is not None:
            _require_non_negative(self.price, "price")
        if self.volume_24h is not None:
            _require_non_negative(self.volume_24h, "volume_24h")
        if self.liquidity_score is not None:
            _require_non_negative(self.liquidity_score, "liquidity_score")


@dataclass(frozen=True)
class FeatureSnapshot:
    """Strategy-facing feature vector derived from normalized market inputs.

    Invariants:
    - All features are numeric and keyed by canonical feature names.
    - `source_bar_count` indicates how many bars contributed to the snapshot.
    - `is_complete` must be `True` before strategies treat the snapshot as tradable.
    """

    instrument_id: str
    timeframe: str
    as_of: datetime
    feature_values: dict[str, Decimal]
    source_bar_count: int
    is_complete: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _require_aware_utc(self.as_of, "as_of")
        if self.source_bar_count <= 0:
            raise ValueError("source_bar_count must be positive")
        if not self.feature_values:
            raise ValueError("feature_values must contain at least one feature")
        for name, value in self.feature_values.items():
            _require_non_empty(name, "feature name")
            if not isinstance(value, Decimal):
                raise TypeError("feature_values must contain Decimal values")


@dataclass(frozen=True)
class DecisionContext:
    """Complete strategy input bundle for a single runtime decision cycle.

    Invariants:
    - The context is venue-neutral and contains only canonical runtime contracts.
    - `latest_candle`, `bar_slice`, and `features` must all reference the same instrument/timeframe.
    - `as_of` must not be earlier than the latest candle close time.
    - Optional upstream context status fields must describe lookup failures without
      leaking exchange payload details.
    """

    cycle_id: str
    as_of: datetime
    instrument: Instrument
    latest_candle: Candle
    bar_slice: BarSlice
    features: FeatureSnapshot
    portfolio_state: PortfolioState
    index_snapshot: IndexSnapshot | None = None
    stablecoin_snapshot: StablecoinSnapshot | None = None
    index_snapshot_status: str | None = None
    index_snapshot_detail: str | None = None
    index_snapshot_requested_version: str | None = None
    stablecoin_snapshot_status: str | None = None
    stablecoin_snapshot_detail: str | None = None
    quality_states: tuple[DataQualityState, ...] = ()
    quality_details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.cycle_id, "cycle_id")
        _require_aware_utc(self.as_of, "as_of")
        if self.instrument.instrument_id != self.latest_candle.instrument_id:
            raise ValueError("instrument and latest_candle must share instrument_id")
        if self.bar_slice.instrument_id != self.instrument.instrument_id:
            raise ValueError("bar_slice must share instrument_id with instrument")
        if self.features.instrument_id != self.instrument.instrument_id:
            raise ValueError("features must share instrument_id with instrument")
        if self.features.timeframe != self.latest_candle.timeframe:
            raise ValueError("features and latest_candle must share timeframe")
        if self.bar_slice.timeframe != self.latest_candle.timeframe:
            raise ValueError("bar_slice and latest_candle must share timeframe")
        if self.as_of < self.latest_candle.close_time:
            raise ValueError("as_of must be on or after latest_candle.close_time")
        for detail in self.quality_details:
            _require_non_empty(detail, "quality_detail")


@dataclass(frozen=True)
class SignalDecision:
    """Strategy output before risk and execution refinement.

    Invariants:
    - The contract is venue-neutral and carries no exchange-specific fields.
    - `confidence` is normalized to the range `[0, 1]`.
    - `target_notional` and `target_quantity`, when provided, are non-negative.
    """

    strategy_name: str
    instrument_id: str
    timeframe: str
    as_of: datetime
    side: SignalSide
    confidence: Decimal
    rationale: str
    target_notional: Decimal | None = None
    target_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.strategy_name, "strategy_name")
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_empty(self.timeframe, "timeframe")
        _require_aware_utc(self.as_of, "as_of")
        _require_probability(self.confidence, "confidence")
        _require_non_empty(self.rationale, "rationale")
        if self.target_notional is not None:
            _require_non_negative(self.target_notional, "target_notional")
        if self.target_quantity is not None:
            _require_non_negative(self.target_quantity, "target_quantity")


@dataclass(frozen=True)
class RiskDecision:
    """Risk evaluation result for a proposed strategy signal.

    Invariants:
    - `status` is one of allow, adjust, or reject.
    - Approved size fields, when present, are non-negative.
    - `reasons` provides operator-visible explanation for the decision.
    """

    signal: SignalDecision
    status: RiskDecisionStatus
    evaluated_at: datetime
    reasons: tuple[str, ...]
    approved_notional: Decimal | None = None
    approved_quantity: Decimal | None = None
    rule_hits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware_utc(self.evaluated_at, "evaluated_at")
        if not self.reasons:
            raise ValueError("reasons must contain at least one entry")
        for reason in self.reasons:
            _require_non_empty(reason, "reason")
        for rule_hit in self.rule_hits:
            _require_non_empty(rule_hit, "rule_hit")
        if self.approved_notional is not None:
            _require_non_negative(self.approved_notional, "approved_notional")
        if self.approved_quantity is not None:
            _require_non_negative(self.approved_quantity, "approved_quantity")


@dataclass(frozen=True)
class ExecutionIntent:
    """Execution-layer instruction generated from a risk-approved decision.

    Invariants:
    - Venue appears only at the execution boundary.
    - Quantity is positive and limit price is present for limit orders.
    - `source_strategy` preserves auditability back to strategy output.
    """

    intent_id: str
    venue: str
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: Decimal
    submitted_at: datetime
    source_strategy: str
    rationale: str
    limit_price: Decimal | None = None
    reduce_only: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.intent_id, "intent_id")
        _require_non_empty(self.venue, "venue")
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_aware_utc(self.submitted_at, "submitted_at")
        _require_non_empty(self.source_strategy, "source_strategy")
        _require_non_empty(self.rationale, "rationale")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError("limit_price is required for limit orders")
            _require_non_negative(self.limit_price, "limit_price")
        elif self.limit_price is not None:
            _require_non_negative(self.limit_price, "limit_price")


@dataclass(frozen=True)
class OrderState:
    """Canonical normalized state of an order after exchange reconciliation.

    Invariants:
    - Quantities are non-negative and `filled + remaining == requested`.
    - Venue-specific status fields are translated into `status`.
    - Average fill price is non-negative when present.
    """

    venue: str
    order_id: str
    client_order_id: str
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    last_update_time: datetime
    limit_price: Decimal | None = None
    average_fill_price: Decimal | None = None
    reconciliation_state: ReconciliationState | None = None
    reconciliation_detail: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("venue", "order_id", "client_order_id", "instrument_id"):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_aware_utc(self.last_update_time, "last_update_time")
        _require_non_negative(self.requested_quantity, "requested_quantity")
        _require_non_negative(self.filled_quantity, "filled_quantity")
        _require_non_negative(self.remaining_quantity, "remaining_quantity")
        if self.filled_quantity + self.remaining_quantity != self.requested_quantity:
            raise ValueError("filled_quantity + remaining_quantity must equal requested_quantity")
        if self.limit_price is not None:
            _require_non_negative(self.limit_price, "limit_price")
        if self.average_fill_price is not None:
            _require_non_negative(self.average_fill_price, "average_fill_price")


@dataclass(frozen=True)
class FillEvent:
    """Canonical fill record consumed by portfolio, storage, and monitoring.

    Invariants:
    - Quantity is positive and fee is non-negative.
    - The contract is normalized and contains no raw exchange payloads.
    - `occurred_at` is the authoritative event time in UTC.
    """

    venue: str
    order_id: str
    fill_id: str
    instrument_id: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_asset: str
    occurred_at: datetime
    liquidity_role: LiquidityRole = LiquidityRole.UNKNOWN

    def __post_init__(self) -> None:
        for field_name in ("venue", "order_id", "fill_id", "instrument_id", "fee_asset"):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_aware_utc(self.occurred_at, "occurred_at")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        _require_non_negative(self.price, "price")
        _require_non_negative(self.fee, "fee")


@dataclass(frozen=True)
class AssetBalanceSnapshot:
    """Canonical balance view for one asset after exchange payload normalization.

    Invariants:
    - `asset` is the canonical asset code.
    - At least one of `free`, `locked`, or `delta` must be present.
    - `free` and `locked` are non-negative when present.
    - `delta` may be signed because some exchange events report changes only.
    """

    asset: str
    free: Decimal | None = None
    locked: Decimal | None = None
    delta: Decimal | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.asset, "asset")
        if self.free is None and self.locked is None and self.delta is None:
            raise ValueError("at least one of free, locked, or delta must be provided")
        if self.free is not None:
            _require_non_negative(self.free, "free")
        if self.locked is not None:
            _require_non_negative(self.locked, "locked")
        if self.updated_at is not None:
            _require_aware_utc(self.updated_at, "updated_at")


@dataclass(frozen=True)
class AccountSnapshot:
    """Canonical account/balance snapshot consumed by portfolio synchronization.

    Invariants:
    - The snapshot is normalized and free of exchange-native field names.
    - `balances` contains canonical asset balance entries only.
    - `translation_version` records which adapter mapping produced the snapshot.
    - `is_partial` is `True` when the update is delta-oriented rather than a full account view.
    """

    venue: str
    account_scope: str
    as_of: datetime
    balances: tuple[AssetBalanceSnapshot, ...]
    source_event_type: str
    translation_version: str
    is_partial: bool = False
    alerts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.venue, "venue")
        _require_non_empty(self.account_scope, "account_scope")
        _require_aware_utc(self.as_of, "as_of")
        _require_non_empty(self.source_event_type, "source_event_type")
        _require_non_empty(self.translation_version, "translation_version")
        if not self.balances:
            raise ValueError("balances must not be empty")


@dataclass(frozen=True)
class ReconciliationEvent:
    """Audit event for recovery attempts and outcomes."""

    venue: str
    order_id: str
    reconciliation_state: ReconciliationState
    occurred_at: datetime
    detail: str

    def __post_init__(self) -> None:
        for field_name in ("venue", "order_id", "detail"):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_aware_utc(self.occurred_at, "occurred_at")


@dataclass(frozen=True)
class PortfolioState:
    """Canonical portfolio snapshot used by strategy, risk, and monitoring layers.

    Invariants:
    - Asset balances and exposures are represented in normalized Decimal quantities.
    - Mapping keys use canonical asset or instrument identifiers.
    - PnL and net exposure may be negative, but gross exposure must be non-negative.
    """

    as_of: datetime
    cash_by_asset: dict[str, Decimal]
    position_qty_by_instrument: dict[str, Decimal]
    average_entry_price_by_instrument: dict[str, Decimal]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal

    def __post_init__(self) -> None:
        _require_aware_utc(self.as_of, "as_of")
        _require_non_negative(self.gross_exposure, "gross_exposure")
        for mapping_name in (
            "cash_by_asset",
            "position_qty_by_instrument",
            "average_entry_price_by_instrument",
        ):
            mapping = getattr(self, mapping_name)
            for key, value in mapping.items():
                _require_non_empty(key, f"{mapping_name} key")
                if not isinstance(value, Decimal):
                    raise TypeError(f"{mapping_name} values must be Decimal")
                if mapping_name != "position_qty_by_instrument" and value < Decimal("0"):
                    raise ValueError(f"{mapping_name} values must be non-negative")


@dataclass(frozen=True)
class PositionState:
    """Canonical per-instrument position snapshot for portfolio continuity.

    Invariants:
    - `instrument_id` is canonical and non-empty.
    - Phase-1 paper mode remains long-only, so quantity and price fields are non-negative.
    - `market_value` and `unrealized_pnl` make session-level state changes inspectable.
    """

    instrument_id: str
    quantity: Decimal
    average_entry_price: Decimal
    mark_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    def __post_init__(self) -> None:
        _require_non_empty(self.instrument_id, "instrument_id")
        _require_non_negative(self.quantity, "quantity")
        _require_non_negative(self.average_entry_price, "average_entry_price")
        _require_non_negative(self.mark_price, "mark_price")
        _require_non_negative(self.market_value, "market_value")


@dataclass(frozen=True)
class RuntimeCycleResult:
    """Summary of one full runtime cycle for audit and monitoring purposes.

    Invariants:
    - Cycle timestamps are UTC-aware and ordered.
    - Output collections are immutable tuples of canonical contracts.
    - `success=False` should correspond to at least one alert or rejected stage.
    """

    cycle_id: str
    started_at: datetime
    completed_at: datetime
    processed_instruments: tuple[str, ...]
    signals: tuple[SignalDecision, ...]
    risk_decisions: tuple[RiskDecision, ...]
    execution_intents: tuple[ExecutionIntent, ...]
    reconciliation_events: tuple[ReconciliationEvent, ...] = ()
    quality_states: tuple[DataQualityState, ...] = ()
    quality_details: tuple[str, ...] = ()
    alerts: tuple[str, ...] = ()
    success: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.cycle_id, "cycle_id")
        _require_aware_utc(self.started_at, "started_at")
        _require_aware_utc(self.completed_at, "completed_at")
        if self.started_at > self.completed_at:
            raise ValueError("started_at must be earlier than or equal to completed_at")
        for instrument_id in self.processed_instruments:
            _require_non_empty(instrument_id, "processed_instrument")
        for detail in self.quality_details:
            _require_non_empty(detail, "quality_detail")
        for alert in self.alerts:
            _require_non_empty(alert, "alert")
        if not self.success and not self.alerts and not any(
            decision.status is RiskDecisionStatus.REJECT for decision in self.risk_decisions
        ):
            raise ValueError("failed cycles must include alerts or rejected risk decisions")
