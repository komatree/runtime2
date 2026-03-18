# Upbit Phase-2 Design

## Purpose

This document defines the phase-2 design package for a future Upbit adapter in `runtime2`.

This is a design/spec artifact only. It is not a claim that Upbit trading is implemented or ready.

## Why Upbit Is Not A Binance Copy

Upbit should not be implemented by copying the Binance adapter.

Key differences:

- JWT auth is request-scoped rather than API-key header plus signature flow
- authenticated requests may require `query_hash`
- throttling is driven by `Remaining-Req` response headers
- KRW markets require venue-specific market metadata and constraint handling
- websocket conventions, keepalive expectations, and session handling differ
- order/account semantics and payload shapes differ

The shared runtime contracts should remain intact. Differences belong inside the Upbit adapter boundary.

## Required Runtime Boundaries

### Auth

- JWT signing must stay inside `app/exchanges/upbit`
- request payload hashing must not leak into execution or strategy code
- nonce generation must be explicit and auditable

### REST Signing

- `query_hash` generation must be isolated in an auth/signing component
- signing must handle requests with and without query/body parameters
- request builders should emit canonical adapter requests, not raw strategy payloads

### Throttling

- `Remaining-Req` parsing must be isolated in a throttle component
- rate state should be operator-visible
- retry/backoff policy should be bounded and explicit

### WebSocket Separation

- public market data and private order/account streams must stay separate
- private WS auth/subscription flow must not be mixed into public market data code
- transport state should emit canonical adapter health signals

### Market Constraints

- KRW market rules belong in venue metadata loaders and order validation helpers
- tick-size and minimum-order rules should map into canonical `Instrument` fields where possible
- any remaining venue-only rule must stay in the Upbit adapter layer

## Expected Adapter Modules

Phase-2 implementation should likely include:

- `app/exchanges/upbit/models.py`
- `app/exchanges/upbit/auth.py`
- `app/exchanges/upbit/rate_limits.py`
- `app/exchanges/upbit/public_ws_client.py`
- `app/exchanges/upbit/private_ws_client.py`
- `app/exchanges/upbit/order_client.py`
- `app/exchanges/upbit/reconciliation.py`

## Contract Compatibility Review

Current exchange-neutral contracts are mostly sufficient for Upbit:

- `Instrument`
  - usable for KRW and crypto quote markets
  - `price_increment` and `quantity_increment` are the right neutral fields for venue rules
- `VenueProfile`
  - usable for capability differences and throughput hints
- `ExecutionIntent`
  - venue-explicit only at the adapter boundary
- `OrderState` / `FillEvent`
  - already canonical enough for future Upbit normalization

## Known Contract Gaps To Revisit During Phase 2

These are review items, not immediate blockers:

- `VenueProfile`
  - may need richer market-order or cancel/replace capability flags
- `Instrument`
  - may need explicit minimum-price-unit documentation by market family if Upbit metadata cannot map cleanly to current fields
- `OrderState`
  - may need adapter translation notes for Upbit-specific intermediate states
- portfolio/account sync
  - account update normalization should confirm current `PortfolioState` granularity is sufficient

No strategy, feature, or risk contract change should be the default answer.

## Phase-2 Exit Criteria

Upbit should not advance beyond design until all of the following are specified:

- auth and `query_hash` flow
- `Remaining-Req` throttle handling
- public/private WS lifecycle handling
- KRW market metadata normalization
- normalized order/account/fill mapping plan
- reconciliation and restart recovery plan
