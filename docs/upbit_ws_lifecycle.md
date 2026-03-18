# Upbit WS Lifecycle

## Scope

This document defines the expected public/private websocket lifecycle design for a future Upbit adapter.

## Separation Rules

- public WS market data and private WS order/account updates must remain separate clients
- public WS code must not parse private account/order payloads
- private WS auth/subscription state must not leak into runtime strategy logic

## Public WS Expectations

- subscribe to market data needed for candle-close decisions
- normalize venue payloads into canonical candles or bar events
- track reconnect attempts
- track keepalive / heartbeat health
- surface degraded and failover states explicitly

## Private WS Expectations

- auth/init handled inside the Upbit adapter
- subscription lifecycle explicit
- reconnect explicit
- session invalidation explicit
- graceful shutdown explicit
- normalize order/account events into internal adapter events first

## Keepalive And Reconnect

Future implementation should specify:

- heartbeat expectations
- reconnect thresholds
- stale-session detection
- operator-visible degraded states
- explicit fallback behavior when WS is unavailable

## Session Rollover

Design should answer:

- whether Upbit requires explicit session refresh or re-subscribe timing
- how public/private channels roll independently
- how rollover events are surfaced to operators

## Failure Handling

Public or private WS failure must not silently degrade into undefined behavior.

The adapter should emit explicit health states such as:

- connecting
- streaming
- degraded
- failover-active
- session-rollover
- terminated
- shutdown

Names can be finalized during implementation, but the state model must be explicit.
