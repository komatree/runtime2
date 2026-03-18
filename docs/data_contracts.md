# Data Contracts

## Contract Philosophy

Contracts in `app/contracts` are canonical, typed, and venue-neutral unless they sit explicitly on the execution or exchange boundary. Exchange payloads are normalized before they enter these contracts. Strategy-facing layers consume instruments, candles, features, portfolio state, and decisions without vendor-specific fields.

## Ownership Summary

- `app/datafeeds` owns production of normalized market contracts such as `Candle`.
- `app/features` owns `IndexSnapshot`, `StablecoinSnapshot`, and `FeatureSnapshot`.
- `app/strategies` consumes `DecisionContext` and emits `SignalDecision`.
- `app/risk` consumes `SignalDecision` and emits `RiskDecision`.
- `app/execution` consumes `RiskDecision` and emits `ExecutionIntent`.
- `app/exchanges` consumes `ExecutionIntent` and emits normalized `OrderState` and `FillEvent`.
- `app/exchanges` also emits normalized `AccountSnapshot` values for portfolio/account synchronization.
- `app/portfolio` produces `PortfolioState`.
- `app/runtime` aggregates cycle outputs in `RuntimeCycleResult`.
- `app/storage` persists append-only report records for report-only mode.

## Contracts

### `Instrument`

- Ownership layer: `contracts`, produced by `config` or instrument catalog loaders, consumed by `features`, `strategies`, `risk`, `execution`
- Purpose: canonical tradable instrument identity and precision constraints
- Fields:
  - `instrument_id`: venue-neutral identifier such as `BTC-USDT`
  - `base_asset`: base asset code
  - `quote_asset`: quote asset code
  - `price_precision`: normalized display and rounding precision for prices
  - `quantity_precision`: normalized display and rounding precision for size
  - `price_increment`: optional neutral tick-size style price step
  - `quantity_increment`: optional neutral lot-size style quantity step
  - `min_quantity`: minimum executable size when known
  - `min_notional`: minimum executable notional when known
  - `is_active`: instrument lifecycle flag
  - venue-expansion note: symbol formatting and venue ticker codes stay outside this contract

### `VenueProfile`

- Ownership layer: `exchanges`, produced by exchange adapters or venue metadata loaders, consumed by `risk`, `execution`, `runtime`
- Purpose: normalized venue capability profile without raw exchange payloads
- Fields:
  - `venue`: canonical venue id
  - `account_scope`: venue account segment such as `spot`
  - `maker_fee_bps`: maker fee in basis points
  - `taker_fee_bps`: taker fee in basis points
  - `supports_market_orders`: whether market orders are supported
  - `supports_post_only`: whether post-only placement is supported
  - `supports_reduce_only`: whether reduce-only style semantics are supported
  - `supports_client_order_ids`: whether the venue supports caller-provided client order ids
  - `default_time_in_force`: normalized default order validity
  - `supported_time_in_force`: explicit supported time-in-force set when known
  - `max_requests_per_second`: optional venue throughput guideline
  - venue-expansion note: authentication headers, websocket topics, and raw status codes do not belong here

### `Candle`

- Ownership layer: `datafeeds`, produced by candle aggregation/normalization, consumed by `features`, `strategies`, `storage`, `monitoring`
- Purpose: canonical OHLCV bar
- Fields:
  - `instrument_id`: canonical instrument identifier
  - `timeframe`: normalized bar interval such as `1m` or `15m`
  - `open_time`: UTC start timestamp
  - `close_time`: UTC close timestamp
  - `open`, `high`, `low`, `close`: Decimal OHLC prices
  - `volume`: base-asset volume
  - `quote_volume`: quote-asset volume when available
  - `trade_count`: normalized trade count
  - `is_closed`: whether the candle is final and immutable

### `BarSlice`

- Ownership layer: `features` or `runtime`, produced by candle window assembly, consumed by `features`, `strategies`
- Purpose: ordered candle window for feature extraction and strategy evaluation
- Fields:
  - `instrument_id`: canonical instrument identifier
  - `timeframe`: shared timeframe for the slice
  - `end_time`: close time of the most recent candle
  - `candles`: ordered tuple of canonical candles

### `IndexSnapshot`

- Ownership layer: `features`, produced by index pipelines, consumed by `strategies`, `router`, `monitoring`
- Purpose: cross-market regime or breadth metric
- Fields:
  - `name`: index name
  - `instrument_id`: canonical instrument id this snapshot is resolved against
  - `index_version`: explicit snapshot version used by the read-only lookup path
  - `as_of`: UTC snapshot time
  - `value`: normalized index value
  - `constituents`: instrument ids contributing to the index
  - `methodology`: human-readable calculation description

### `IndexSuiteLookupResult`

- Ownership layer: `features/index_suite`, produced by the read-only snapshot repository/provider, consumed by runtime orchestration and storage/debugging
- Purpose: explicit result of resolving the latest valid Index Suite snapshot by instrument/date/version
- Fields:
  - `status`: one of `ok`, `missing`, `stale`, or `version_mismatch`
  - `requested_instrument_id`: target instrument id
  - `requested_index_version`: configured version for this decision
  - `requested_as_of`: decision timestamp
  - `snapshot`: resolved snapshot when present
  - `detail`: operator-readable explanation when resolution is not `ok`

### `StablecoinSnapshot`

- Ownership layer: `features`, produced by stablecoin health pipeline, consumed by `strategies`, `risk`, `monitoring`
- Purpose: report-only stablecoin observability snapshot with explicit source freshness and source type
- Fields:
  - `pair`: normalized stablecoin reference pair
  - `reference_asset`: reference asset code, usually fiat-like
  - `snapshot_version`: explicit schema/version id for the snapshot source
  - `source_type`: source classification such as `report_only_ingest`
  - `as_of`: UTC snapshot time
  - `source_fresh_until`: freshness boundary for report-only use
  - `stablecoin_net_mint_24h`: normalized 24h net mint amount
  - `stablecoin_net_burn_24h`: normalized 24h net burn amount
  - `stablecoin_supply_change_pct_24h`: normalized 24h supply change percentage
  - `stablecoin_chain_supply_delta_24h`: normalized 24h chain supply delta
  - `stablecoin_abnormal_transfer_count`: abnormal transfer count over the observation window
  - `price`: optional observed price
  - `premium_bps`: optional premium or discount versus reference in basis points
  - `volume_24h`: optional 24h volume measure
  - `liquidity_score`: optional normalized liquidity score
  - `is_depegged`: explicit peg-health flag

### `StablecoinSnapshotLookupResult`

- Ownership layer: `features/stablecoin`, produced by the read-only stablecoin snapshot repository/provider, consumed by runtime orchestration and debugging
- Purpose: explicit result of resolving the latest stablecoin observability snapshot
- Fields:
  - `status`: one of `ok`, `missing`, or `stale`
  - `requested_as_of`: requested decision timestamp
  - `snapshot`: resolved snapshot when fresh
  - `detail`: operator-readable reason when resolution is not `ok`

### `FeatureSnapshot`

- Ownership layer: `features`, produced by feature pipelines, consumed by `strategies`, `monitoring`, `storage`
- Purpose: strategy-ready numeric feature vector
- Fields:
  - `instrument_id`: canonical instrument identifier
  - `timeframe`: timeframe that produced the features
  - `as_of`: UTC snapshot time
  - `feature_values`: mapping of canonical feature names to Decimal values
  - `source_bar_count`: number of bars used to produce the features
  - `is_complete`: whether the feature set is safe for trading decisions
  - note: Index Suite integration may add explicit diagnostic fields for presence, staleness, version-match, and snapshot age

### `DecisionContext`

- Ownership layer: `runtime`, produced by runtime orchestration, consumed by `strategies`
- Purpose: complete venue-neutral input bundle for one strategy evaluation
- Fields:
  - `cycle_id`: runtime cycle identifier
  - `as_of`: decision timestamp
  - `instrument`: canonical instrument metadata
  - `latest_candle`: most recent closed or active candle
  - `bar_slice`: ordered candle history window
  - `features`: strategy-facing feature snapshot
  - `portfolio_state`: latest canonical portfolio view
  - `index_snapshot`: optional regime context
  - `stablecoin_snapshot`: optional stablecoin context
  - `index_snapshot_status`: optional read-only Index Suite lookup status
  - `index_snapshot_detail`: optional explanation for missing/stale/version-mismatched snapshots
  - `index_snapshot_requested_version`: requested Index Suite version for this cycle

### `SignalDecision`

- Ownership layer: `strategies`, produced by strategy modules, consumed by `risk`, `storage`, `monitoring`
- Purpose: venue-neutral trade preference before risk shaping
- Fields:
  - `strategy_name`: producing strategy id
  - `instrument_id`: target instrument
  - `timeframe`: decision timeframe
  - `as_of`: strategy decision time
  - `side`: `buy`, `sell`, or `flat`
  - `confidence`: normalized score in `[0, 1]`
  - `rationale`: human-readable reason
  - `target_notional`: optional notional sizing hint
  - `target_quantity`: optional size hint in base units

### `RiskDecision`

- Ownership layer: `risk`, produced by risk engine, consumed by `execution`, `storage`, `monitoring`
- Purpose: auditable outcome of risk evaluation
- Fields:
  - `signal`: original strategy output
  - `status`: `allow`, `adjust`, or `reject`
  - `evaluated_at`: UTC evaluation time
  - `reasons`: operator-visible reasons for the outcome
  - `approved_notional`: optional post-risk notional
  - `approved_quantity`: optional post-risk quantity
  - `rule_hits`: identifiers of triggered risk rules

### `ExecutionIntent`

- Ownership layer: `execution`, produced by execution planner, consumed by `exchanges`, `storage`, `monitoring`
- Purpose: exchange-bound instruction after strategy and risk processing
- Fields:
  - `intent_id`: execution intent identifier
  - `venue`: canonical target venue id
  - `instrument_id`: target instrument
  - `side`: canonical order side
  - `order_type`: `market` or `limit`
  - `time_in_force`: normalized order validity mode
  - `quantity`: executable quantity
  - `submitted_at`: UTC planning time
  - `source_strategy`: originating strategy id
  - `rationale`: operator-readable context
  - `limit_price`: required for limit orders
  - `reduce_only`: whether intent is exposure-reducing only
  - venue-expansion note: the venue id is explicit here because venue routing happens only after strategy and risk are complete

### `OrderState`

- Ownership layer: `exchanges`, produced by exchange reconciliation, consumed by `portfolio`, `storage`, `monitoring`
- Purpose: normalized order lifecycle view independent of venue payload shape
- Lifecycle states:
  - `new`
  - `acknowledged`
  - `partially_filled`
  - `filled`
  - `canceled`
  - `expired`
  - `rejected`
  - `recovering`
  - `unreconciled`
- Fields:
  - `venue`: canonical venue id
  - `order_id`: venue order identifier
  - `client_order_id`: runtime-generated id for correlation
  - `instrument_id`: target instrument
  - `side`: canonical order side
  - `order_type`: canonical order type
  - `status`: normalized order lifecycle state
  - `requested_quantity`: original requested quantity
  - `filled_quantity`: cumulative executed quantity
  - `remaining_quantity`: unfilled quantity
  - `last_update_time`: UTC update time
  - `limit_price`: limit price when applicable
  - `average_fill_price`: normalized average fill price
  - `reconciliation_state`: optional canonical recovery state for unknown execution handling
  - `reconciliation_detail`: operator-readable recovery detail
  - lifecycle note: partial fills remain non-terminal and must not be collapsed into `filled`
  - restricted-live note: live portfolio mutation may use this contract only after canonical payload translation and safeguard gating

### `FillEvent`

- Ownership layer: `exchanges`, produced by exchange adapters, consumed by `portfolio`, `storage`, `monitoring`
- Purpose: canonical execution fill record
- Fields:
  - `venue`: canonical venue id
  - `order_id`: associated order identifier
  - `fill_id`: unique fill identifier
  - `instrument_id`: filled instrument
  - `side`: canonical side
  - `quantity`: executed quantity
  - `price`: execution price
  - `fee`: normalized fee amount
  - `fee_asset`: fee asset code
  - `occurred_at`: UTC fill timestamp
  - `liquidity_role`: maker/taker classification when known
  - lifecycle note: fill events advance `OrderState` through the shared order lifecycle state machine

### `AssetBalanceSnapshot`

- Ownership layer: `exchanges`, produced by exchange payload translators, consumed by `portfolio`, `storage`, `monitoring`
- Purpose: canonical per-asset balance view after adapter normalization
- Fields:
  - `asset`: canonical asset code
  - `free`: spendable balance when provided
  - `locked`: reserved balance when provided
  - `delta`: signed balance change when the exchange provides delta-only updates
  - `updated_at`: UTC update time when known

### `AccountSnapshot`

- Ownership layer: `exchanges`, produced by exchange payload translators, consumed by `portfolio`, `storage`, `monitoring`
- Purpose: canonical account/balance snapshot independent of venue-native payload shape
- Fields:
  - `venue`: canonical venue id
  - `account_scope`: venue account partition such as `spot`
  - `as_of`: UTC snapshot time
  - `balances`: canonical balance entries only
  - `source_event_type`: normalized origin family such as account position or balance delta
  - `translation_version`: explicit translator version for auditability
  - `is_partial`: whether the snapshot is delta-oriented rather than a full account view
  - `alerts`: operator-visible translation warnings
  - translation note: Binance private payloads must be mapped into this contract before portfolio/account sync logic consumes them
  - restricted-live note: full snapshots may be used as the cash/balance cross-check inside the mandatory live mutation gate

### `PortfolioState`

- Ownership layer: `portfolio`, produced by portfolio service and reconciliation, consumed by `runtime`, `strategies`, `risk`, `monitoring`
- Purpose: canonical account and exposure view
- Fields:
  - `as_of`: UTC portfolio timestamp
  - `cash_by_asset`: free or effective cash balances by asset
  - `position_qty_by_instrument`: signed position quantities by instrument
  - `average_entry_price_by_instrument`: normalized entry prices by instrument
  - `realized_pnl`: realized profit and loss
  - `unrealized_pnl`: unrealized profit and loss
  - `gross_exposure`: absolute exposure measure
  - `net_exposure`: signed exposure measure

### `RuntimeCycleResult`

- Ownership layer: `runtime`, produced by runtime orchestration, consumed by `monitoring`, `storage`, operators
 - venue-expansion note: runtime summaries stay canonical; exchange-specific diagnostics should be translated before attachment
- Purpose: cycle-level audit summary
- Fields:
  - `cycle_id`: runtime cycle identifier
  - `started_at`: UTC cycle start
  - `completed_at`: UTC cycle end
  - `processed_instruments`: instruments processed in the cycle
  - `signals`: strategy outputs from the cycle
  - `risk_decisions`: risk outcomes from the cycle
  - `execution_intents`: exchange-bound intents created in the cycle
  - `alerts`: operator-visible warnings or failures
  - `success`: overall cycle success flag

### `ReportCycleRecord`

- Ownership layer: `storage`, produced by report-only persistence gateway, consumed by operators, debugging tools, future storage migrations
- Purpose: append-only debugging record that explains one full report-only cycle
- Fields:
  - `schema_version`: explicit schema identifier, currently `report_cycle.v1`
  - `recorded_at`: persistence timestamp
  - `cycle_timestamp`: runtime cycle decision timestamp
  - `instrument_id`: canonical instrument identifier
  - `timeframe`: cycle timeframe
  - `bar_close_time`: close time of the trigger bar
  - `feature_snapshot_summary`: structured summary of feature families and feature names
  - `signal_decisions`: serialized `SignalDecision` values
  - `risk_decisions`: serialized `RiskDecision` values
  - `execution_intents`: serialized generated-but-not-submitted `ExecutionIntent` values
  - `runtime_cycle_result`: serialized `RuntimeCycleResult`
  - `decision_context_summary`: compact context summary with optional snapshot presence flags
  - `index_suite_context`: persisted decision-time Index Suite lookup/result context

### `FeatureSnapshotSummaryRecord`

- Ownership layer: `storage`, produced by report serializer, consumed by debugging tools and operators
- Purpose: summarize the feature snapshot without hiding missing optional sources
- Fields:
  - `feature_count`: number of features present
  - `feature_names`: sorted feature-name list
  - `is_complete`: completeness flag from `FeatureSnapshot`
  - `source_bar_count`: bar count used to create the snapshot
  - `candle_features`: candle-derived features always grouped explicitly
  - `index_features`: optional Index Suite feature section, `null` when absent
  - `stablecoin_features`: optional stablecoin feature section, `null` when absent

### `DecisionContextSummaryRecord`

- Ownership layer: `storage`, produced by report serializer, consumed by debugging tools and operators
- Purpose: lightweight context summary for quick diagnosis
- Fields:
  - `cycle_id`: runtime cycle id
  - `instrument_id`: canonical instrument id
  - `timeframe`: cycle timeframe
  - `as_of`: decision timestamp
  - `bar_close_time`: trigger candle close
  - `has_index_snapshot`: whether an optional index snapshot was present
  - `has_stablecoin_snapshot`: whether an optional stablecoin snapshot was present

## Producer / Consumer Flow

1. `config` and metadata loaders publish `Instrument`; exchange edges publish `VenueProfile`.
2. `datafeeds` publish `Candle`.
3. `runtime` assembles `BarSlice` and injects `PortfolioState`.
4. `features/index_suite` resolves the latest valid precomputed `IndexSnapshot` by instrument/date/version.
5. `features/stablecoin` resolves the latest fresh `StablecoinSnapshot` for report-only observability.
6. `features` publish `IndexSnapshot`, `StablecoinSnapshot`, and `FeatureSnapshot`.
7. `runtime` bundles the above into `DecisionContext`.
8. `strategies` emit `SignalDecision`.
9. `risk` emits `RiskDecision`.
10. `execution` emits `ExecutionIntent`.
11. `exchanges` translate venue-private payloads into canonical `OrderState`, `FillEvent`, and `AccountSnapshot`.
12. `runtime` records `RuntimeCycleResult`.
13. `storage` records append-only `ReportCycleRecord` entries for report-only mode, including Index Suite context.

## Validation Guidance

- Reject non-UTC timestamps at contract boundaries.
- Reject incomplete or inconsistent candle windows before feature generation.
- Reject strategy decisions without rationale or traceable strategy identity.
- Reject execution intents that require venue-specific raw fields outside adapter boundaries.
- Keep additive evolution preferred; breaking schema changes should be versioned deliberately.
- Report-only persistence should keep optional sections explicit rather than omitting the top-level schema fields entirely.
- Treat stale or version-mismatched Index Suite snapshots as invalid for feature enrichment while preserving their lookup status for debugging.
- Treat stale stablecoin snapshots as invalid for feature enrichment while preserving source freshness and source type in observability outputs.
