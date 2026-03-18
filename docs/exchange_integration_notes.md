# Exchange Integration Notes

## Exchange Boundary Rules

- Binance and Upbit integrations live under `app/exchanges/*`.
- Shared authentication, clock, retry, throttling, and normalization utilities belong in `app/exchanges/common`.
- No exchange client object should be imported directly into strategies, features, or risk code.
- Future venues such as Upbit, Bybit, KuCoin, and Bithumb should map into the existing canonical contracts rather than extending strategy or risk interfaces.
- Venue onboarding should prefer small adapter modules plus metadata loaders over new cross-cutting abstraction layers.

## Future Venue Extension Points

- Add venue-specific symbol mapping inside the adapter layer only.
- Map venue order types and time-in-force semantics into canonical `OrderType` and `TimeInForce`.
- Populate `VenueProfile` with capability differences instead of branching inside strategies.
- Populate `Instrument.price_increment`, `Instrument.quantity_increment`, `min_quantity`, and `min_notional` from venue metadata loaders.
- Keep account, order, and fill payload normalization inside `app/exchanges/<venue>`.
- Reuse the same reconciliation workflow states for any venue that can produce unknown execution or delayed status convergence.

## Binance Notes

- Phase-1 target
  - public market data ingestion scaffold
  - public websocket kline normalization scaffold
  - private account and order stream contract scaffold
  - clock-sync status contract scaffold
  - order lookup and unknown execution recovery contract scaffold
  - order submission readiness validation only
  - reconciliation summary and recovery-plan hooks only
- Model exchange-specific filters such as lot size, tick size, and notional limits inside the adapter layer.
- Translate Binance order states into canonical `OrderState` values before storage or portfolio reconciliation.
- Public market-data path
  - public websocket parsing is isolated from private order/account events
  - closed-bar detection is the primary correctness target
  - reconnect, heartbeat degradation, and session rollover are explicit health states
  - WS degradation may fail over to REST polling only as an explicit degraded path
- Private stream requirement
  - live readiness requires authoritative private account/order/fill ingestion
  - REST polling alone is insufficient for timely reconciliation and unknown execution detection
  - future websocket and status-query convergence should meet at the same normalized event/recovery contracts
  - authenticated lifecycle states are explicit: auth/init, subscribe, reconnect, session rollover, terminate, shutdown
  - real authenticated transport now exists inside the adapter boundary for WS-API connection open/close, signed user-data subscription, reconnect, and payload read
  - endpoint-profile validation now fails closed when REST and websocket hosts do not match the configured Binance environment
  - request-weight-aware control-plane throttling now blocks signed lookup and WS-API private-stream subscription calls before budget exhaustion
  - old REST `POST /api/v3/userDataStream` listenKey bootstrap is deprecated for current Spot user-data subscription and now returns HTTP `410 Gone` on the failing path we observed locally
  - the adapter now bootstraps private truth with `userDataStream.subscribe.signature` over the Spot WebSocket API instead of assuming a REST listenKey lifecycle
- Private stream normalized event families
  - `order_update`
  - `account_update`
  - `stream_status`
  - raw Binance payloads stay inside the adapter boundary
- Reconciliation workflow states
  - `submit_sent`
  - `unknown_execution`
  - `status_query_pending`
  - `recovered_terminal_state`
  - `unreconciled_manual_attention`
  - these states are explicit audit artifacts, not hidden transport internals
- Pre-live blockers
  - signed REST order submission is not implemented
  - websocket lifecycle management, reconnect logic, and sequence-gap recovery transport are not implemented
  - reconciliation fallback transport for sequence gaps and missed events is not implemented
  - no fully automated replay scheduler or operator-default persistence path is in place yet
- What is now scaffolded
  - transport boundary for authenticated WS-API connect, signed subscribe, renewal/reconnect, and close
  - private stream ingestion batch contract
  - private stream session lifecycle contracts and health states
  - bootstrap, reconnect, subscription renewal, and shutdown session handling
  - request-weight-aware throttling for signed order-status lookup and private-stream WS-API control calls
  - endpoint profile validation for REST and websocket environment isolation
  - normalized mapping for order/execution updates
  - normalized mapping for account/balance updates
  - normalized stream termination/invalidation events
  - canonical private-payload translator from Binance raw events into `OrderState`, `FillEvent`, and `AccountSnapshot`
  - explicit translation result versioning and malformed-payload visibility
  - real signed REST order-status lookup transport with adapter-local request signing and normalized lookup results
  - transport-backed reconciliation orchestration that combines private payload ingestion, canonical translation, signed lookup attempts, and explicit convergence output
  - batch-level family counts, last sequence id, and operator-facing health snapshots
  - watchdog-based private-stream heartbeat overdue and subscription-expiry degradation
  - schema-resilient status-query parsing for non-object and Binance error payloads
  - schema-resilient private websocket parsing for wrapped `data` payloads and missing event-type rejection
  - account-sync summary wiring for future portfolio reconciliation
  - reconciliation-event filtering from normalized private batches
  - public websocket kline message normalization
  - closed-bar event detection and bar-slice assembly from normalized closed candles
  - reconnect, heartbeat, and session-rollover health hooks
  - explicit failover-to-REST state when WS is unavailable
  - order lookup contract shape for client id and exchange id
  - unknown execution recovery plan contract
  - reconciliation coordinator that turns missing/unknown execution into explicit recovery states
  - repeated status-lookup attempts with explicit convergence vs pending vs manual-attention outcomes
  - explicit automatic recovery trigger metadata for:
    - private-stream gap
    - restart resume with unresolved reconciliation state
    - missing private-stream updates
    - unknown execution
  - automatic multi-attempt signed status-query recovery when gap or unresolved-state policy allows
  - append-only recovery logging for lookup attempts and outcomes
  - replay-safe reconciliation state storage for unresolved orders, cursor state, deduplicated recovery attempts across restart, and last recovery trigger/convergence metadata
  - explicit persistence of:
    - gap detection state
    - automatic recovery trigger reason
    - attempt sequence
    - convergence result
    - manual-attention escalation timing
  - automatic restart-safe continuation from persisted unresolved reconciliation state
  - server-time sample and offset evaluation contract
  - repeated clock recalibration attempts with explicit uncertain-state exposure
  - operator-facing clock status summary rendering
  - portfolio-safe live fill aggregation with duplicate-fill protection
  - explicit blocking of portfolio mutation for recovering, unreconciled, or account-mismatched live state
  - recovery actions that hold portfolio mutation until confidence is restored
- Still not production-ready
  - no production-proven websocket runtime loop or reconnect scheduler yet
  - no production-proven long-running heartbeat watchdog behavior yet
  - no production-proven long-running WS-API subscription renewal behavior yet
  - no operator-default runtime wiring yet for reconciliation state snapshot paths
  - no fully wired canonical private-payload translator path into restricted-live mutation yet
  - no fully wired live portfolio mutation path from translated fills and account sync yet
  - no production server-time transport implementation yet
- Unknown execution handling plan
  - treat missing private-stream updates as reconciliation alerts
  - move order tracking through explicit reconciliation states instead of inferring success from silence
  - hold portfolio mutation behind reconciliation confirmation
  - keep repeated recovery attempts inspectable rather than hidden behind silent retries
  - persist every recovery lookup attempt and terminal/unresolved outcome in append-only logs
  - keep the latest unresolved cursor snapshot restart-safe and operator-visible
  - persist gap-triggered automatic recovery metadata so restart continuation remains explainable
  - add stronger operational thresholds and real long-running durability evidence before enabling production trading
  - escalate operator visibility when unknown execution ids appear

## Upbit Notes

- Treat market metadata, symbol conventions, and authentication flow as venue-specific concerns isolated inside the adapter.
- Normalize quote asset conventions and timestamp formats before publishing contracts upstream.
- Handle venue throttling and temporary maintenance states with explicit adapter-level status signals.
- Upbit remains phase 2. No strategy, risk, or feature contract changes should be required to add it.

## Other Future Venues

- Bybit
  - likely needs derivative-capability handling through `VenueProfile`, not strategy rewrites
- KuCoin
  - likely needs adapter-specific symbol and auth handling only
- Bithumb
  - likely needs KRW quote conventions and instrument metadata normalization only

## Shared Requirements

- Clock skew handling must be explicit.
- Retries must be bounded and observable.
- Every submission, cancellation, and reconciliation step must emit auditable events.
- Sandbox/test environments should use the same canonical contracts as live trading.
