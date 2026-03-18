# Upbit Auth And Rate Limits

## Scope

This document defines the future Upbit auth and throttling boundary for `runtime2`.

## Auth Requirements

Upbit implementation should isolate:

- JWT token construction
- access key usage
- nonce generation
- request parameter canonicalization
- `query_hash` generation
- `query_hash_alg` handling

None of these should leak outside `app/exchanges/upbit`.

## Query Hash Rules

Design expectations:

- requests with query/body params must produce a canonical serialized query form
- `query_hash` must be deterministic for identical request inputs
- requests without params should avoid unnecessary query-hash work where Upbit rules allow
- signing code should expose operator-debuggable summaries without exposing secrets

## Rate Limit Requirements

Upbit throttling should be driven by `Remaining-Req` headers rather than a Binance-style fixed request model.

The adapter should eventually support:

- parsing `Remaining-Req`
- tracking remaining budget by scope
- surfacing low-budget or exhausted-budget states
- bounded backoff and retry decisions
- operator-visible throttle degradation alerts

## Runtime Boundary

Suggested separation:

- `auth.py`
  - JWT and `query_hash`
- `rate_limits.py`
  - `Remaining-Req` parsing and throttle state
- `order_client.py`
  - uses auth + throttle state, but does not own either policy

## Operator Visibility

Future implementation should expose:

- last auth/signature success time
- last throttle header seen
- current remaining budget summary
- retry / block decision reason

## Non-Goals

- storing secrets in runtime decision objects
- sharing JWT/query-hash logic with Binance
- hiding throttling behind generic retry wrappers with no Upbit-specific visibility
