# Binance Known Gaps

This document lists the Binance-specific gaps that still block production promotion.

Launcher readiness and dry-run readiness are not the blocking issue now. They support rehearsal and operator review, but they do not close the transport, reconciliation, and portfolio-safety gaps below.

## Transport Gaps

- no production-proven websocket reconnect scheduler
- no production-proven long-running heartbeat watchdog behavior for private transport
- no production-proven long-running WebSocket API user-data subscription renewal behavior
- no replay-safe fallback from private-stream gaps to status-query recovery
- request-weight throttling exists, but no operator-default threshold policy or alert routing exists yet
- endpoint-profile isolation exists, but no broader multi-environment config management layer exists yet

## Current Migration Note

- the old REST listenKey bootstrap path returned HTTP `410 Gone` during real restricted-live bootstrap because Binance Spot user-data subscription has moved away from that deprecated bootstrap assumption
- the adapter now uses `userDataStream.subscribe.signature` over the Spot WebSocket API instead of REST listenKey acquisition
- this fixes the observed bootstrap failure, but it does not by itself prove production durability

## Known Gaps / Not In Scope For The Next Bounded Run

These items should remain visible, but they are not reasons to redesign the current broader-baseline code before the next bounded run:

- `executionRules` / `referencePrice` additions beyond current watchpoint handling
- `expiryReason` / `eR` operator surfacing beyond current tolerance
- parser/model expansion for `permissionSets`, `amendAllowed`, `quoteOrderQtyMarketAllowed`, and STP-related fields
- explicit handling for `MAX_ASSET` or `myFilters` beyond current gap awareness
- deeper unknown execution hardening beyond the current fail-closed recovery path
- reconnect / heartbeat subsystem redesign
- new request-weight, order-count, or timeout automation
- Demo Mode execution or Demo Mode-specific hardening

For the next bounded run, these are watchpoints and future-hardening items, not immediate refactor targets.

## Recovery And Reconciliation Gaps

- no fully automated convergence between private stream and REST status lookup
- no fully wired restricted-live path that consumes transport-backed lookup and translation outputs end-to-end

## Portfolio Safety Gaps

- no production-safe live fill application path in restricted-live runtime wiring
- no operator-approved live discrepancy threshold workflow

## Clock And Timing Gaps

- clock-sync contract exists, but live operational tolerance enforcement is incomplete
- no shared production clock-health service feeding all exchange-facing actions

## Market Data Gaps

- public websocket normalization exists, but real transport lifecycle remains incomplete
- REST failover is modeled as a degraded state, not a completed production transport path

## Operational Gaps

- no production promotion should be approved on current Binance state
- restricted-live rehearsal remains a gated rehearsal, not a production cutover
- launcher-backed dry-run success does not clear Binance transport blockers
- any go/no-go summary must disclose these gaps explicitly
