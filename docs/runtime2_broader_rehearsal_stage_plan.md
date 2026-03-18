# runtime2 Broader Rehearsal Stage Plan

## Stage Outcome

This stage is now complete.

Authoritative broader-stage baseline:

- runtime:
  - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
- scheduler:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
- action windows:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

Final classification:

- `PASS WITH CAUTION`

Final readiness verdict:

- sufficient to exit the broader `restricted_live_rehearsal` stage

What `r5` proved:

- one fresh lineage-valid `6h` runtime session completed
- scheduler/action lineage remained clean and bound to the same runtime run id
- all three planned active windows executed inside the same session
- blocked mutation remained `0`
- reconciliation remained automatic with no manual attention
- account-update visibility remained adequate across the broader session
- reconnect / heartbeat churn was high but non-destructive

Why the classification remains `PASS WITH CAUTION`:

- `a2` and `a3` completed as `PARTIAL_SUCCESS_NONBLOCKING`, not full create/cancel/fill success
- both partial windows hit `-1013 PERCENT_PRICE_BY_SIDE` on the resting create leg
- reconnect / heartbeat churn remained elevated during the session

This document remains useful as the record of the broader-stage purpose and operating shape, but it should no longer be read as an open planning document for the next run. The next stage is a bounded operator / bounded micro-live stage.

## Purpose

Define the broader `restricted_live` rehearsal stage that followed the narrow active-event and signed-path proofs, and record the operating shape that is now closed by the authoritative `r5` evidence set.

This stage is not trying to re-prove the smallest active-event questions that are already answered.

Its purpose is to build confidence in a broader, longer, still fail-closed operating shape:

- longer continuous runtime
- repeated active windows inside one session
- cleaner session-wide artifact continuity
- broader operator confidence in the documented bounded procedure under a less toy-like session shape

It is still a rehearsal stage, not a production-rehearsal approval.

## What Is Already Proven

The following are already reviewably established and should not be treated as the primary question of this next stage:

- standalone signed-path verification baseline on Spot testnet
  - signed REST lookup
  - signed WS subscription
  - shared `timestamp` / `recvWindow` assumptions
- create acknowledgement proof from paired `a5/r5`
- cancel acknowledgement proof from paired `a5/r5`
- fill-related private-event handling from paired `a6/r6`
- direct account/balance-update proof from paired `a2/r2`
- reconciliation under active conditions for reviewed `cancelled` and `filled` terminal outcomes
- bounded driver-backed operator flow for the narrow rehearsal path

This means the broader stage should not be framed as:

- "does signing work at all"
- "can runtime2 ingest any private event at all"
- "can runtime2 reconcile one create/cancel or one fill at all"

Those questions are already answered narrowly.

## What Broader Scope Still Needs Confidence

The next stage should build confidence in areas that are broader than the reviewed one-window proofs:

- one longer restricted-live session with mixed idle and active periods
- repeated active windows within the same runtime session
- session-wide health and artifact continuity across more elapsed time
- operator execution of the documented flow without ad hoc recovery steps
- repeated reconciliation cleanliness under multiple active windows, not just one isolated window
- confidence that runtime2 remains fail-closed and reviewable when the session is longer and less tightly bounded around a single event

This stage is about breadth and continuity, not about adding new exchange capabilities.

## Recommended Runtime Duration And Scope

Recommended shape:

- Spot testnet only
- `restricted_live_rehearsal` only
- one medium-length session:
  - target `6h`
- three intentionally small active windows inside that session:
  - early create/cancel window
  - mid-session fill-enabled window
  - later fill-enabled or account-update-focused window
- no broadening into arbitrary manual trading or open-ended action generation

Why `6h` is the right next step:

- it is materially broader than the `1h` bounded proofs
- it is still reviewable without turning into an uncontrolled soak
- it leaves room to observe:
  - idle continuity
  - repeated active handling
  - reconciliation behavior across separated windows
  - artifact continuity over time

## Recommended Paired Flow

### 1. Session Start

Before the broader session:

1. run credential sanity check
2. run standalone signed-path verification
3. start the `restricted_live_rehearsal` runtime session

### 2. Runtime Session

Run one `6h` session with a dedicated runtime run id, for example:

- runtime run id: `binance-testnet-broader-rehearsal-r1`

Keep the same posture already used in the bounded rehearsals:

- rehearsal-only
- no runtime order submission
- same mutation gate and fail-closed behavior

### 3. Active Windows

During the same runtime session, run three small action-driver windows with run ids derived from the runtime run id:

- runtime run id:
  - `binance-testnet-broader-rehearsal-r1`
- derived action run ids:
  - `binance-testnet-broader-rehearsal-r1-a1`
  - `binance-testnet-broader-rehearsal-r1-a2`
  - `binance-testnet-broader-rehearsal-r1-a3`
- derived scheduler run id:
  - `binance-testnet-broader-rehearsal-r1-scheduler`

Spacing guidance:

- place them in separated windows rather than back-to-back
- leave meaningful idle time between them so the session exercises both:
  - quiet continuity
  - repeated active transitions

## Artifact Classes To Review

### Signed-Path Baseline

- `reports/signed_path_verification/latest/signed_path_summary.json`
- `reports/signed_path_verification/latest/signed_path_summary.md`

### Action Windows

For each action run id:

- `reports/event_exercises/<action_run_id>/action_driver/action_driver_events.jsonl`
- `reports/event_exercises/<action_run_id>/action_driver/action_driver_summary.md`

### Session-Wide Runtime Artifacts

- `reports/soak_sessions/<runtime_run_id>/soak_summary.json`
- `reports/soak_sessions/<runtime_run_id>/soak_summary.md`
- `reports/soak_sessions/<runtime_run_id>/runtime_cycles.jsonl`
- `reports/soak_sessions/<runtime_run_id>/runtime_health.json`
- `reports/soak_sessions/<runtime_run_id>/runtime_status.md`
- `reports/soak_sessions/<runtime_run_id>/health_transitions.jsonl`
- `reports/soak_sessions/<runtime_run_id>/reconciliation_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/reconnect_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/account_update_events.jsonl`

Any additional relevant session artifacts under the same runtime run directory should also be reviewed if they contain:

- account-side state transitions
- exchange-health transitions
- reconciliation or reconnect signals

## What Counts As Success

Success for this broader stage means:

- the full `6h` session completes without fatal abort
- signed-path precheck is preserved as a clean reviewed artifact
- each planned action window produces preserved action-driver artifacts
- the session shows reviewable correlation for the repeated active windows, not just one
- reconciliation remains automatic and clean where triggered
- account-update artifacts remain operator-reviewable during fill windows
- no unsafe mutation behavior appears
- no ad hoc undocumented operator recovery is needed to complete the flow

Stronger success:

- all three active windows are reviewably correlated against the same session-wide runtime artifacts
- runtime health remains understandable and stable across the session
- the session demonstrates that the documented bounded flow scales to a broader but still controlled rehearsal shape

## What Counts As Ambiguity

Ambiguous, not sufficient:

- one active window is clearly correlated, but later windows are missing or weakly evidenced
- the session completes, but critical artifact classes are missing for one or more windows
- reconciliation triggers but the evidence chain is not clean enough to distinguish expected behavior from noise
- health degrades transiently in a way that is not fatal, but the cause/effect trail is too weak to review confidently
- the broader session is mostly idle and does not actually exercise the intended repeated active windows
- one action window is only a partial success, but later windows still run and preserve clean lineage and correlation

## What Counts As A Blocker

Blocker-level outcomes:

- signed-path precheck fails at session start
- one or more intended action windows cannot be reviewably correlated because the evidence chain is broken
- runtime enters a fatal or unclear degraded state that requires undocumented manual intervention
- reconciliation requires manual attention or fails to converge for the reviewed active windows
- fail-closed behavior is bypassed or becomes unclear
- critical session artifacts are absent, truncated, or not operator-reviewable
- a true fatal action-window outcome stops the scheduler before the intended repeated-window structure completes

## What Must Remain Fail-Closed

The broader stage must keep the same conservative posture:

- Spot testnet only
- `restricted_live_rehearsal` only
- no runtime-side live order submission
- existing mutation gate remains active
- ambiguous or mismatched account/order state must remain mutation-blocking
- repeated unexplained exchange errors must remain halt-worthy
- no broad live-trading interpretation should be inferred from a successful run

This stage is intentionally broader in duration and evidence breadth, not broader in risk posture.

## How This Differs From Full Production Rehearsal

This broader stage is still narrower than a full production rehearsal:

- it remains testnet-only
- it remains explicitly rehearsal-only
- it still uses intentionally small bounded action windows
- it is still an evidence-gathering stage, not a promotion decision
- it is not trying to prove unrestricted operational readiness under all day-to-day conditions

A full production rehearsal would ask broader questions about:

- operator readiness across a fuller runbook surface
- readiness breadth across longer and messier sessions
- go/no-go confidence beyond the currently reviewed bounded and medium-length rehearsal shapes

## Historical Recommended Run Shape

The following run shape is retained as the historical broader-stage plan that was ultimately satisfied by `r5`.

Recommended execution target at the time:

- signed-path artifact refresh at session start
- runtime run id:
  - `binance-testnet-broader-rehearsal-r1`
- action windows:
  - `binance-testnet-broader-rehearsal-r1-a1`
  - `binance-testnet-broader-rehearsal-r1-a2`
  - `binance-testnet-broader-rehearsal-r1-a3`

Recommended session structure:

1. start the runtime session
2. let terminal 1 write `reports/soak_sessions/<runtime_run_id>/runtime_session.json`
3. start the scheduler in terminal 2 using `--runtime-run-id`, not a copied timestamp
4. run one early create/cancel or fill-enabled window
5. leave idle time
6. run one mid-session fill-enabled window
7. leave idle time
8. run one later fill-enabled window
9. review the full session as one broader rehearsal, not as three isolated bounded proofs

Operator safeguards for the scheduler:

- `runtime_session.json` is the source of truth for runtime start time
- every broader rehearsal must use a fresh runtime run id so derived `a1/a2/a3` and scheduler output directories are fresh
- reusing an existing scheduler directory is a fail-closed error
- reusing an existing action-driver directory is a fail-closed error
- default late-start policy remains `abort`
- if terminal 2 starts after the first planned window is already late beyond grace, the scheduler must stop instead of collapsing windows together
- non-fatal partial window outcomes may continue to later windows when artifacts remain reviewable
- true fatal window outcomes still abort the broader session

## Next Stage Handoff

The broader-stage handoff is now:

- use `r5` as the authoritative broader baseline
- do not reopen broader-stage questions unless regression appears in later evidence
- carry forward the same fail-closed posture, runtime/session lineage model, and stale-output protection
- move to one bounded operator / bounded micro-live stage with a short, explicit, artifact-driven scope

The next stage should remain bounded:

- one fresh runtime run id per session
- one scheduler plan derived from that runtime run id
- no ad hoc timestamp copying
- no bypass of fail-if-exists behavior
- no loosening of blocked-mutation or reconciliation stop rules

## Exact Review Task After Execution

After execution, review the full session with this question:

"Did runtime2 preserve clean signed-path, repeated active-window handling, direct account-update visibility, and fail-closed session continuity across one broader `restricted_live` rehearsal?"

The review should:

1. confirm the signed-path artifact set used at session start
2. confirm each action window definitely happened
3. correlate each action window against the single runtime session artifact set
4. classify reconciliation as:
   - unused
   - clean
   - problematic
5. classify the broader stage as:
   - success
   - ambiguous
   - blocker

If the result is successful, the next gate discussion should shift from narrow active-event confidence to broader rehearsal-readiness scope only.
