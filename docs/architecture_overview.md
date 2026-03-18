# Architecture Overview

## Intent

`runtime2` is a candle-based trading runtime organized around strict module boundaries. The system consumes exchange data, normalizes it into canonical contracts, computes features, evaluates strategies, applies risk controls, routes execution intents to exchange adapters, and persists state for observability and recovery.

## Boundary Model

- `app/contracts` defines stable internal contracts. Other packages depend on contracts rather than each other’s concrete implementations.
- `app/runtime` coordinates lifecycle, scheduling, dependency wiring, and shutdown.
- `app/datafeeds` owns ingestion of trades, order book snapshots, ticker state, and candle streams from exchanges or replay sources.
- `app/features/*` owns feature production and exposes a unified `FeatureSnapshot` to downstream consumers. Candle features are locally computed; index suite and stablecoin features are upstream snapshot adapters.
- `app/strategies/*` transforms features and portfolio state into trade intents. Strategies must not call exchanges directly.
- `app/risk` evaluates trade intents against account, symbol, and portfolio constraints.
- `app/execution` translates approved intents into executable order plans.
- `app/exchanges/*` implements venue-specific APIs under shared exchange contracts.
- `app/portfolio` maintains balances, positions, exposures, and realized/unrealized PnL views.
- `app/storage` persists snapshots, fills, configuration, and backtest/live audit trails.
- `app/monitoring` surfaces runtime health, cycle summaries, degradation flags, and operator alerts without depending on exchange payload JSON.
- `app/config` loads and validates typed configuration for all runtime components.

## Dependency Direction

Preferred dependency flow:

`config -> runtime -> contracts -> datafeeds/features/portfolio/storage/monitoring`

`strategies -> contracts + features + portfolio`

`risk -> contracts + portfolio`

`execution -> contracts + risk`

`exchanges -> contracts`

Concrete exchange adapters and storage backends are outer-layer implementations and should not leak vendor-specific types into strategy or feature code.

## Venue Extension Points

- `Instrument` remains canonical and venue-neutral.
  - `instrument_id`, `base_asset`, and `quote_asset` stay internal identifiers.
  - `price_increment` and `quantity_increment` are neutral execution hints that can map Binance, Upbit, Bybit, KuCoin, and Bithumb filters without changing strategy contracts.
- `VenueProfile` remains a capability contract rather than a payload mirror.
  - generic fields such as `supports_post_only`, `supports_reduce_only`, `supports_client_order_ids`, and `supported_time_in_force` allow venue differences to stay inside `risk`, `execution`, and `app/exchanges/*`
- `DecisionContext`, `SignalDecision`, `RiskDecision`, and `FeatureSnapshot` are intentionally venue-blind.
- `ExecutionIntent`, `OrderState`, and `FillEvent` are the only canonical contracts that should name a venue directly.
- New venues should add adapter modules and metadata loaders, not new strategy/risk contracts.

## Feature Ownership

- Candle feature ownership stays in `app/features/candle/service.py`.
  - producer: normalized candle slices from `datafeeds` and `runtime`
  - consumer: `strategies`, `risk`, `monitoring`
- Index suite ownership stays in `app/features/index_suite/service.py`.
  - producer: upstream precomputed index snapshots
  - consumer: `strategies`, `router`, `risk`, `monitoring`
  - rule: strategies do not compute index-suite values locally
- Stablecoin ownership stays in `app/features/stablecoin/service.py`.
  - producer: upstream stablecoin health snapshots
  - consumer: `strategies`, `risk`, `monitoring`
  - rule: strategies do not compute stablecoin direction signals locally

`FeatureSnapshot` is the single strategy-facing feature contract. Producers compute or adapt features before strategy evaluation; consumers read the unified snapshot only.

## Report-Only First

The initial vertical slice is report-first. Feature services must support report-only runtime mode before any exchange-coupled execution path. This keeps feature ownership independent from venue submission logic and preserves clean producer/consumer separation as paper and restricted-live modes are added.

## Observability Boundary

- `app/storage` owns durable cycle records and append-only audit logs.
- `app/monitoring` owns operator-facing summaries derived from canonical runtime contracts.
- Monitoring reads normalized runtime context and cycle results only.
- Degraded but non-fatal states, such as missing Index Suite or stablecoin context, are surfaced as explicit flags rather than hidden in free-form logs.

## Selective Migration

Small, low-coupling components were migrated selectively from the local legacy reference code into `runtime2`:

- `app/exchanges/common/precision.py`
  - selected because step-size rounding and min-notional checks are pure utility logic
  - adapted to `Decimal` and venue-neutral helper names
- `app/exchanges/common/retry.py`
  - selected because retry/backoff calculation is pure and reusable
  - adapted to allow deterministic tests through injected jitter
- `app/exchanges/binance/error_classifier.py`
  - selected because Binance error classification is isolated adapter logic with high debugging value
  - adapted to return `runtime2` adapter models instead of legacy exceptions

Intentionally not migrated:

- legacy runners and orchestration
- grid or micro-live trading logic
- large execution engine paths
- legacy config sprawl
- direct legacy model imports or compatibility bridges

`runtime2` remains authoritative. Migrated code is treated as rewritten input material, not a compatibility dependency.

## Runtime Modes

- Live trading
- Paper trading
- Historical replay / simulation

All modes should share the same contracts, with source adapters and side-effect handlers swapped at the edges.
