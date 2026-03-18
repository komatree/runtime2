# Upbit Testing Plan

## Purpose

This document defines the minimum test plan expected before any Upbit live-facing work is considered.

## Test Layers

### Contract And Mapping Tests

- market metadata normalization
- KRW market constraint mapping to `Instrument`
- `VenueProfile` capability mapping
- order/account/fill payload normalization

### Auth Tests

- JWT creation
- nonce uniqueness
- `query_hash` determinism
- requests with and without params

### Rate Limit Tests

- `Remaining-Req` parsing
- throttle state updates
- degraded / exhausted budget signaling

### Public WS Tests

- message normalization
- closed-bar detection
- reconnect behavior
- keepalive degradation handling

### Private WS Tests

- auth/init lifecycle
- subscribe lifecycle
- reconnect lifecycle
- termination / invalidation handling
- normalized order/account event mapping

### Reconciliation Tests

- order lookup behavior
- unknown execution handling
- restart recovery expectations

## Regression Priorities

Minimum high-value scenarios:

- clean no-action market
- KRW market order validation failure
- public WS degraded but explicit
- private WS invalidation and reinit
- reconciliation after delayed private update

## Exit Gate For Implementation

Upbit implementation should not be considered phase-ready unless:

- adapter unit tests exist for auth, rate limits, and WS lifecycle
- reconciliation tests exist
- operator docs are updated
- open gaps are disclosed conservatively
