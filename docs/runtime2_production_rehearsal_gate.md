# runtime2 Production-Rehearsal Gate

## Purpose

This document defines the final go/no-go gate before `runtime2` can be treated as ready for a production-rehearsal review.

It is intentionally strict.

- It is not a production approval.
- It is not a substitute for [`docs/production_gate_pre_audit.md`](/home/terratunes/code/trading/runtime2/docs/production_gate_pre_audit.md).
- It is a checklist for deciding whether the project has enough evidence and operator discipline to begin a serious production-rehearsal decision.

## Current Gate Verdict

Current verdict: `BLOCKED`

Reason:
- the architecture baseline is strong
- the fail-closed baseline is strong
- operator/runbook coverage is improving
- create/cancel active private-event proof is now established from a paired driver-backed rehearsal
- fill-related private-event proof is now established from a paired fill-attempt rehearsal
- reconciliation under active conditions is now strongly evidenced across both `cancelled` and `filled` terminal outcomes
- direct account/balance-update proof is now established from a paired account-update rehearsal
- the broader `restricted_live_rehearsal` stage is now closed by the authoritative `r5` evidence set
- but the evidence baseline is still incomplete in the areas that still matter most:
  - the next bounded operator / bounded micro-live stage
  - remaining production-rehearsal readiness items outside the now-cleared narrow active-event, signed-path, and broader repeated-window evidence classes

This means:
- `report_only`: allowed
- `paper`: allowed
- `restricted_live` rehearsal: allowed under current fail-closed gates
- production-rehearsal gate: not yet cleared

Broader-stage status:
- authoritative broader baseline: `r5`
- broader-stage classification: `PASS WITH CAUTION`
- broader-stage readiness verdict: sufficient to exit the broader `restricted_live_rehearsal` stage

## Latest Reassessment

Latest reviewed evidence:
- paired create/cancel active-event proof:
  - action driver:
    - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_events.jsonl)
    - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_summary.md)
  - runtime rehearsal:
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_cycles.jsonl)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_health.json)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/reconciliation_events.jsonl)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/soak_summary.md)
- paired fill-attempt active-event proof:
  - action driver:
    - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_events.jsonl)
    - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_summary.md)
  - runtime rehearsal:
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_cycles.jsonl)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_health.json)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/reconciliation_events.jsonl)
    - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/soak_summary.md)
- paired account-update proof:
  - action driver:
    - [`reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_events.jsonl)
    - [`reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_summary.md)
  - runtime rehearsal:
    - [`reports/soak_sessions/binance-testnet-account-update-r2/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/runtime_cycles.jsonl)
    - [`reports/soak_sessions/binance-testnet-account-update-r2/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/runtime_health.json)
    - [`reports/soak_sessions/binance-testnet-account-update-r2/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/reconciliation_events.jsonl)
    - [`reports/soak_sessions/binance-testnet-account-update-r2/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/soak_summary.md)
    - [`reports/soak_sessions/binance-testnet-account-update-r2/account_update_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/account_update_events.jsonl)
- authoritative broader repeated-window baseline:
  - runtime:
    - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
  - scheduler:
    - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
  - action windows:
    - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
    - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
    - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

Blocked-item reassessment:

| Previously blocked item | Reassessment | Why |
| --- | --- | --- |
| Signed-path verification baseline | cleared | the latest standalone artifact set under [`reports/signed_path_verification/latest/`](/home/terratunes/code/trading/runtime2/reports/signed_path_verification/latest/) verifies both the WS signed subscription class and the REST signed lookup class on Spot testnet |
| Active private-event evidence baseline | cleared for create/cancel, fill, and direct account-update scenarios | `a5/r5` proves paired create/cancel handling for order id `17384129`; `a6/r6` proves paired fill handling for order id `17387064`; `a2/r2` adds direct persisted `outboundAccountPosition` account-update evidence for `BTC,USDT` during the paired fill window |
| Reconcile/fault recovery baseline under active conditions | strongly evidenced / effectively cleared across reviewed terminal outcomes | `r5` converged terminal `cancelled` and `r6`/`r2` converged terminal `filled`, all with automatic recovery and no manual attention |
| Operator runbook baseline, missing practical items closed | improved and broadened, but not fully cleared | the `r5` broader session proves the lineage-valid multi-window operating flow, but the next bounded operator / bounded micro-live stage is still required before a production-rehearsal decision |
| Broader repeated-window restricted-live rehearsal baseline | cleared with caution | `r5` completed a fresh lineage-valid `6h` session with three in-session action windows, `blocked_mutation_count = 0`, clean reconciliation, and non-destructive reconnect churn; `a2/a3` remained `PARTIAL_SUCCESS_NONBLOCKING`, so the result is `PASS WITH CAUTION` |

Net effect:
- one previously blocked gate item is now cleared narrowly:
  - create/cancel active private-event proof
- one additional active-event gate item is now cleared narrowly:
  - fill-related private-event proof
- one additional active-event gate item is now cleared narrowly:
  - direct account/balance-update proof
- one previously blocked gate item is now strongly evidenced and effectively cleared:
  - reconciliation under active conditions for the reviewed `cancelled` and `filled` terminal scenarios
- one broader-stage gate item is now cleared with caution:
  - repeated-window broader `restricted_live_rehearsal` baseline
- remaining gate blockers are now about the bounded operator / bounded micro-live stage and broader production-rehearsal completeness, not whether runtime2 can handle any active private event at all

## Gate Categories

### 1. Already Passed

| Gate item | Current status | Evidence |
| --- | --- | --- |
| Architecture baseline | passed | [`docs/runtime2_project_state_and_next_steps.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_project_state_and_next_steps.md), [`docs/runtime_flow.md`](/home/terratunes/code/trading/runtime2/docs/runtime_flow.md), [`docs/data_contracts.md`](/home/terratunes/code/trading/runtime2/docs/data_contracts.md) |
| Launcher/config discipline | passed | [`scripts/runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py), [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md) |
| Fail-closed behavior baseline | passed | [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md), [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md) |
| Deprecated Binance bootstrap removal | passed | [`docs/binance_change_compliance_audit.md`](/home/terratunes/code/trading/runtime2/docs/binance_change_compliance_audit.md), [`reports/binance_deprecated_usage_scan.md`](/home/terratunes/code/trading/runtime2/reports/binance_deprecated_usage_scan.md) |
| Parser tolerance baseline for `executionReport` optional fields | passed | [`docs/execution_report_tolerance_note.md`](/home/terratunes/code/trading/runtime2/docs/execution_report_tolerance_note.md) |
| Idle-session soak durability baseline | passed with narrow scope | reviewed `2h` and `6h` soak artifacts under [`reports/soak_sessions/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions) |
| Shared exchange-health visibility | passed | [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md), [`docs/debugging_playbook.md`](/home/terratunes/code/trading/runtime2/docs/debugging_playbook.md) |
| Operational inheritance baseline, core items | passed with noted gaps | [`docs/micro_live_to_runtime2_inheritance_audit.md`](/home/terratunes/code/trading/runtime2/docs/micro_live_to_runtime2_inheritance_audit.md) |

### 2. Required But Not Yet Passed

These items are mandatory. The gate stays blocked until all are passed.

| Gate item | Current status | Why it still blocks |
| --- | --- | --- |
| Signed-path verification baseline | passed | the latest preserved standalone artifact set verifies WS signed subscription, REST signed lookup, and the shared timestamp/`recvWindow` assumptions on Spot testnet; see [`docs/binance_signed_path_verification_plan.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_plan.md) and [`docs/binance_signed_path_verification_results.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_results.md) |
| Active private-event evidence baseline | passed for the reviewed bounded scenarios | paired `a5/r5` evidence establishes create/cancel proof for exchange order id `17384129`, paired `a6/r6` evidence establishes fill-related proof for exchange order id `17387064`, and paired `a2/r2` evidence adds direct persisted account-update proof through `account_update_events.jsonl` |
| Reconcile/fault recovery baseline under active conditions | passed for the reviewed bounded scenarios | paired `a5/r5`, `a6/r6`, and `a2/r2` evidence show automatic recovery, terminal convergence, and no manual-attention escalation across reviewed `cancelled` and `filled` outcomes |
| Operator runbook baseline, missing practical items closed | not yet passed | runtime2-specific operator docs are now supported by the broader `r5` rehearsal baseline, but the next bounded operator / bounded micro-live stage is still needed before this gate item can pass fully; see [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md) and [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md) |

### 3. Informational But Non-Blocking

These items matter, but they do not block the production-rehearsal gate by themselves if the required gates are passed.

| Item | Current status | Why it is non-blocking here |
| --- | --- | --- |
| Longer soak progression beyond 6h | useful but not sufficient alone | longer idle durability helps confidence, but does not substitute for active-event proof |
| Artifact naming drift such as `listen_key_refresh.jsonl` | informational | can confuse operators, but does not alter runtime correctness by itself |
| Partial-fill scenario automation | useful but optional for the first gate | partial fills are valuable evidence, but the first gate can be cleared by simpler active-event proof if it is strong and unambiguous |
| Additional helper scripts | useful | helpers improve operator workflow, but lack of a helper is not the core blocker if the documented process is executable |

### 4. Explicit Blockers

These are the concrete blockers right now.

1. The next bounded operator / bounded micro-live stage is still not completed.
2. The broader production-rehearsal gate is still not cleared end-to-end across all remaining validation classes.

## Baseline Checklist

### Architecture Baseline

- [x] Strategy-facing code is separated from exchange-native payloads.
- [x] `report_only`, `paper`, and `restricted_live` remain separate runner paths.
- [x] Canonical contracts exist for order, fill, account, and runtime-cycle reporting.
- [x] Exchange-specific logic remains under [`app/exchanges/binance`](/home/terratunes/code/trading/runtime2/app/exchanges/binance).
- [x] Private translation, reconciliation, and live mutation gating are explicit.

Minimum acceptable evidence:
- current code and docs stay consistent with the above boundaries
- no known exchange payload leakage into strategy/risk/portfolio contracts

Not enough:
- “the code looks clean”
- “the private translator exists”

### Operational Inheritance Baseline

- [x] Thin wrapper and launcher discipline carried forward.
- [x] Preflight-before-action discipline carried forward.
- [x] Fail-closed posture carried forward.
- [x] Soak/evidence collection practice carried forward.
- [ ] Signed auth-check is proven as a repeatable operator step.
- [ ] Operating-PC checklist is exercised in a real signed-path plus active-event run.
- [ ] Explicit graceful stop convention is proven in use.
- [ ] Explicit repeated exchange-error halt policy is exercised in operator workflow.

Minimum acceptable evidence:
- operator can follow the documented runtime2-specific runbook/checklists without ad hoc interpretation

Not enough:
- “the docs exist”
- “the operator already knows the old micro-live habits”

### Signed-Path Verification Baseline

- [x] Local harness exists for signed REST and signed WS-API path construction.
- [x] Local artifacts are produced.
- [x] Live Spot testnet run succeeds for the signed REST path used by runtime2.
- [x] Live Spot testnet run succeeds for the WS-API `userDataStream.subscribe.signature` path.
- [x] Timestamp and `recvWindow` assumptions are reviewed from the live harness output.
- [x] No `-1022 INVALID_SIGNATURE` or equivalent signature rejection is observed in the live verification run.

Minimum acceptable evidence before this gate can pass:
- reviewed artifacts from the live testnet signed-path harness
- clear pass/fail summary stored under the normal reports path

Not enough:
- local request construction only
- manual eyeballing of code
- “it probably works because the HMAC logic is standard”

### Parser Tolerance Baseline

- [x] `executionReport` without `eR` / `expiryReason` is covered.
- [x] `executionReport` with `eR` / `expiryReason` is covered.
- [x] unexpected extra fields are tolerated without translator crash.
- [x] malformed required-field payloads still fail visibly.
- [ ] optional expiry metadata is not yet surfaced in an operator-visible normalized form, if future exchange behavior makes it semantically important.

Minimum acceptable evidence:
- focused passing tests at the translator boundary

Not enough:
- assumptions based only on Binance docs

### Active Private-Event Evidence Baseline

- [x] Real order-create acknowledgement observed in runtime2 artifacts for the paired create/cancel scenario.
- [x] Real cancel acknowledgement observed in runtime2 artifacts for the paired create/cancel scenario.
- [x] Real account/balance update observed in runtime2 artifacts through a direct persisted account-update artifact.
- [x] At least one real active private-event run reviewed end-to-end.
- [x] Driver-backed action evidence now maps the action sequence to resulting runtime artifacts for the paired create/cancel and fill scenarios.

Minimum acceptable evidence:
- reviewed active-event exercise artifacts generated by the dedicated harness or equivalent bounded procedure
- proof that private events were actually observed, not inferred

Not enough:
- idle soak success
- signed-path-only success
- operator claim without artifacts

Latest reviewed attempt:
Latest reviewed paired proofs:
- action run id: `binance-testnet-active-private-driver-20260315-a5`
- runtime run id: `binance-testnet-active-private-driver-20260315-r5`
- result: `proven` for create/cancel active private-event proof
- what was proven:
  - action driver recorded successful create and cancel for exchange order id `17384129`
  - runtime reconciliation artifacts referenced the same order id `17384129`
  - runtime recovered terminal `cancelled` automatically with no manual attention
  - reconciliation recovery success rate was `1.0000`
- what remains not fully proven:
  - none within the narrow create/cancel scenario itself
- action run id: `binance-testnet-active-private-driver-20260315-a6`
- runtime run id: `binance-testnet-active-private-driver-20260315-r6`
- result: `proven` for fill-related private-event handling
- what was proven:
  - action driver recorded successful fill attempt for exchange order id `17387064`
  - runtime reconciliation artifacts referenced the same order id `17387064`
  - runtime recovered terminal `filled` automatically with no manual attention
  - reconciliation remained clean under the richer active scenario
- what remains not fully proven:
  - direct account-update proof was established separately in the paired account-update run below
- action run id: `binance-testnet-account-update-a2`
- runtime run id: `binance-testnet-account-update-r2`
- result: `proven` for direct account/balance-update proof
- what was proven:
  - action driver recorded a successful fill attempt for exchange order id `17393758`
  - runtime reconciliation artifacts referenced the same order id `17393758`
  - runtime persisted a direct `account_update_events.jsonl` row with `source_event_type: outboundAccountPosition`
  - the persisted account-update artifact captured `BTC` and `USDT` balances in the paired active fill window
- what remains not fully proven:
  - broader production-rehearsal readiness outside the narrow active-event evidence classes

### Reconcile / Fault Recovery Baseline

- [x] Deterministic simulated reconciliation disruption scenarios exist.
- [x] Replay-safe and restart-safe reconciliation persistence exists.
- [x] Real active-event exercise has shown clean convergence under benign `cancelled` and `filled` conditions.
- [x] Recovery attempt artifacts from live testnet exercises have been reviewed for paired create/cancel and fill scenarios.

Minimum acceptable evidence:
- at least one reviewed active-condition artifact set showing reconciliation behavior in practice

Not enough:
- test-only disruption harnesses by themselves

### Operator Runbook Baseline

- [x] Runtime2-specific operator runbook exists.
- [x] Operating-PC checklist exists.
- [x] Repeated exchange-error halt policy is documented.
- [x] Graceful external stop convention is documented.
- [ ] These runbook steps have been exercised during signed-path verification and active private-event exercise without ambiguity.

Minimum acceptable evidence:
- operator can execute the signed-path and active-event procedures from docs alone

Not enough:
- “the author understands how to run it”

### Fail-Closed Behavior Baseline

- [x] Mutation gate is mandatory in restricted-live.
- [x] Invalidation-driven recovery alone cannot authorize mutation.
- [x] Ambiguous, unreconciled, malformed, and snapshot-mismatched states block mutation.
- [x] Blocked-mutation reasons are operator-visible.
- [x] Restricted-live remains rehearsal-only and does not open unrestricted live trading.

Minimum acceptable evidence:
- latest code path and artifacts still show blocked mutation as explicit success when appropriate

Not enough:
- lack of crashes
- lack of fills

## Minimum Acceptable Evidence Before Production-Rehearsal Review

All of the following must be true:

1. Live Spot testnet signed-path harness has been run and reviewed successfully.
2. At least one bounded active private-event exercise has produced reviewed artifacts showing real private-event ingestion.
3. Those artifacts show the expected path separation:
   - bootstrap/auth succeeded
   - private subscription succeeded
   - canonical translation did not crash
   - operator artifacts were written
4. At least one active-condition reconciliation or status-truth path has been observed and reviewed, even if the result is “no recovery needed.”
5. Operator notes exist and explain the exact manual actions and wall-clock timing.
6. No contradictory evidence exists between the artifacts, runbooks, and readiness docs.

If any one of these is missing, the gate is not cleared.

## Explicit Not-Enough Cases

The following do not clear the gate by themselves:

- one more idle soak pass
- longer idle soak duration alone
- successful preflight only
- successful signed-path local capture only
- passing unit tests only
- simulated failure injection only
- simulated reconciliation disruption only
- operator statement without persisted artifacts

## False Confidence To Avoid

Do not treat the following as equivalent:

- idle soak success = active private-event proof
- transport continuity = runtime correctness
- compliance audit pass = live exchange correctness
- parser tolerance tests = order lifecycle proof
- strong architecture = operational readiness
- micro-live operational success = runtime2 proof by default

runtime2 is not re-learning everything from scratch, but it still must earn its own evidence for the exchange-facing paths that changed materially.

## Current Blockers To Rehearsal Gate Clearance

1. Live Spot testnet signed-path acceptance is still not cleared as a separately reviewed dedicated harness result.
2. Runtime2-specific operator procedures now have a broader `r5` baseline, but they still need to be proven in the next bounded operator / bounded micro-live stage.
3. Broader repeated-window rehearsal evidence now exists, but it does not by itself clear the production-rehearsal gate.

## Next Evidence Needed To Clear The Gate

1. Execute the next bounded operator / bounded micro-live stage using the same lineage/session model proven in `r5`.
2. Confirm the operator/runbook procedure remains unambiguous under that bounded next-stage flow.
3. Only after that step, reassess whether runtime2 is ready for a production-rehearsal decision.

## Recommendation

Current recommendation: `continue restricted-live rehearsal evidence gathering`

This is not a hold on development or rehearsal.
It is a block on declaring the production-rehearsal gate cleared.
