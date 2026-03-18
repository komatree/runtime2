# Upbit Phase-2 Go/No-Go

## Decision

No-Go for implementation now.

Recommendation:

- keep Upbit implementation gated behind Binance cutover readiness
- allow only design-level clarification work if needed
- do not start full Upbit adapter implementation yet

## Basis For Decision

The current `runtime2` state is strong enough for venue-neutral architecture work, but not strong enough to justify splitting execution focus across Binance and Upbit at the same time.

The decisive issue is not contract readiness. It is unfinished Binance production-path work.

## Current Prerequisites Met

### Runtime And Contract Prerequisites

- exchange-neutral contracts are already in place for:
  - `Instrument`
  - `VenueProfile`
  - `ExecutionIntent`
  - `OrderState`
  - `FillEvent`
- strategy, feature, and risk layers are already isolated from exchange payload details
- shared runtime flow is explicit and documented
- degraded-state handling is explicit
- shared order lifecycle model already exists

### Upbit Design Prerequisites

- phase-2 design package exists:
  - [`docs/upbit_phase2_design.md`](/home/terratunes/code/trading/runtime2/docs/upbit_phase2_design.md)
  - [`docs/upbit_auth_and_rate_limits.md`](/home/terratunes/code/trading/runtime2/docs/upbit_auth_and_rate_limits.md)
  - [`docs/upbit_ws_lifecycle.md`](/home/terratunes/code/trading/runtime2/docs/upbit_ws_lifecycle.md)
  - [`docs/upbit_testing_plan.md`](/home/terratunes/code/trading/runtime2/docs/upbit_testing_plan.md)
- key Upbit-specific boundaries are already identified:
  - JWT auth
  - `query_hash`
  - `Remaining-Req`
  - public/private WS separation
  - KRW market constraints

## Prerequisites Not Met

### Binance Cutover Prerequisites Not Met

From the current Binance cutover package:

- production cutover is still blocked
- signed order submission is still blocked
- portfolio-safe live fill translation is still blocked
- private stream transport is incomplete
- reconciliation convergence is incomplete
- clock-sync hardening is incomplete

Supporting references:

- [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md)
- [`docs/binance_known_gaps.md`](/home/terratunes/code/trading/runtime2/docs/binance_known_gaps.md)

### Operational Prerequisites Not Met

- restricted-live remains a rehearsal path, not a production-ready venue path
- Binance incident recovery still depends on scaffolding plus operator procedures rather than complete live transport maturity
- production promotion criteria are not yet satisfied even for the phase-1 venue

## Cost Of Context Switching Now

Starting Upbit implementation now would impose concrete costs:

### Engineering Focus Cost

- Binance private stream, reconciliation, and clock-sync hardening would compete with Upbit auth, throttling, and WS lifecycle work
- the most operationally important unfinished work would slow down

### Validation Cost

- a second venue would expand the test matrix before the first venue has cleared production cutover gates
- operator documentation and incident procedures would split across two incomplete exchange implementations

### Risk Of Premature Generalization

- there would be pressure to broaden shared abstractions before Binance transport and recovery gaps have stabilized
- this would increase the chance of abstraction churn instead of reusing a proven Binance path

### Operational Clarity Cost

- cutover messaging would become less clear
- the current operator stance is simple: Binance is the only phase-1 venue, and even Binance is not yet production-ready
- beginning Upbit implementation now weakens that discipline

## Recommendation With Rationale

Recommendation:

- No-Go for starting Upbit implementation now

Rationale:

1. Binance is still the phase-1 cutover bottleneck.
2. The missing work is operationally central:
   - private stream maturity
   - reconciliation convergence
   - clock-sync hardening
   - portfolio-safe live state translation
3. Upbit design work is already sufficiently prepared, so there is no immediate planning emergency.
4. The highest-value next step is to finish one venue's production path cleanly before broadening venue count.

## What Is Reasonable To Do Now

- keep Upbit in design/spec mode
- allow minor design clarifications if Binance work reveals contract gaps
- avoid adapter implementation, transport work, or venue-specific test expansion until Binance cutover blockers are materially reduced

## Trigger For Revisit

Revisit this decision when all of the following are true:

- Binance production cutover is no longer marked blocked
- private stream transport is operationally credible
- reconciliation and unknown execution recovery are transport-backed and testable
- clock-sync hardening is operationally credible
- operator runbooks and cutover procedures are stable for one venue first
