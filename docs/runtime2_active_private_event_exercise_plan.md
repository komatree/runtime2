# runtime2 Active Private Event Exercise Plan

## Purpose

This document defines the first concrete active private-event exercise plan for `runtime2` on Binance Spot testnet.

The goal is not more idle durability evidence.
The goal is proof that real private order/account events can pass through the current runtime2 path safely and explainably:

- signed bootstrap
- private event ingestion
- canonical translation
- reconciliation visibility
- mutation-gate decisioning
- operator-visible artifacts

This is a rehearsal plan.
It is not unrestricted live trading.

Read together with:
- [`docs/runtime2_project_state_and_next_steps.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_project_state_and_next_steps.md)
- [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md)
- [`docs/binance_signed_path_verification_results.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_results.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md)

## 1. Goals Of The Exercise

The exercise should produce evidence for these questions:

1. Does the signed private bootstrap succeed on current Spot testnet?
2. Does runtime2 ingest real private order/account events without crashing or losing contract boundaries?
3. Does canonical translation produce explainable `OrderState`, `FillEvent`, and account update behavior?
4. Does reconciliation stay explainable if private-event timing is imperfect?
5. Does the mutation safeguard gate remain fail-closed when the event truth is incomplete or ambiguous?

The exercise is successful only if the evidence makes those questions easier to answer with artifacts, not harder.

## 2. Exact Event Classes To Exercise

### Required target events

These are the minimum event classes worth exercising:

1. order create acknowledgement
2. cancel acknowledgement
3. full fill
4. balance/account update

### Opportunistic target events

These are useful if achievable, but should not be over-claimed:

1. partial fill

### Fault-shape observations to record if seen naturally

These are not separate primary goals for the first live exercise, but they should be noted if observed:

1. duplicate private events
2. delayed private events
3. missing private events requiring reconciliation visibility

## 3. Realistic Feasibility Notes

### Likely achievable on Spot testnet

- order create acknowledgement
- cancel acknowledgement
- full fill if the chosen test order crosses immediately
- account/balance update around fills or order reservation release

### Possibly achievable but not reliable

- partial fill

Why:
- Spot testnet liquidity and matching behavior can be inconsistent
- partial fill may require price placement and timing conditions that are not stable enough to make it the first proof target

So:
- partial fill should be attempted only after the simpler scenarios are already proven
- a session that fails to produce partial fill is not automatically a failed exercise

## 4. Preconditions

All of these should be true before the active-event exercise starts.

1. Operating-PC checklist completed:
   - [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md)
2. Spot testnet config is used:
   - [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml)
3. Launcher preflight passes.
4. The signed-path verification harness has been run live on Spot testnet successfully, or the operator has explicitly documented that signed-path proof is still pending.
5. Reports/logs directories are writable.
6. The operator understands this remains rehearsal-only.

Important note:
- if live signed-path verification is still not complete, the exercise may still be run for exploratory evidence
- but the evidence must not be treated as full proof of signed-path correctness

## 5. Operator Steps

### Step 1. Preflight and signed/bootstrap check

Run:

```bash
bash scripts/preflight_runtime2.sh \
  --mode restricted_live \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

Then run the signed-path harness if not already completed for the current credentials/environment:

```bash
env BINANCE_API_KEY='your_testnet_key' BINANCE_API_SECRET='your_testnet_secret' \
python scripts/verify_binance_signed_paths_testnet.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --allow-live-testnet \
  --output-dir reports/signed_path_verification/active-event-precheck
```

### Step 2. Start a short active-event rehearsal window

Use the existing restricted-live soak entrypoint and keep the run bounded.

Recommended starting window:
- `1h` max
- `20` to `40` cycles

Use:

```bash
env BINANCE_API_KEY='your_testnet_key' BINANCE_API_SECRET='your_testnet_secret' \
python scripts/binance_restricted_live_soak.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --run-id binance-testnet-active-private-1h \
  --duration-hours 1 \
  --cycles 40 \
  --poll-interval-seconds 30 \
  --output-subdir soak_sessions \
  --max-blocked-mutations 3 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

### Step 3. During the run, generate real private events

Use the smallest realistic event sequence first.

Recommended manual sequence:

1. create one small order intended to receive a clear acknowledgement
2. cancel one resting order to produce cancel acknowledgement
3. create one order intended to fill fully
4. observe whether account/balance update follows

Do not start by chasing partial fill.

### Step 4. Record operator notes

Record:

- approximate wall-clock time of each manual exchange action
- intended order behavior:
  - create
  - cancel
  - fill attempt
- whether the action was expected to fill immediately or rest

### Step 5. Post-run review

Run:

```bash
bash scripts/check_soak_result.sh binance-testnet-active-private-1h
```

Then inspect:

- `runtime_health.json`
- `runtime_status.md`
- `runtime_cycles.jsonl`
- `runtime_cycle_summaries.jsonl`
- `reconciliation_events.jsonl`
- `soak_summary.json`
- `soak_summary.md`

## 6. Required Artifacts

The exercise should preserve at minimum:

- `reports/soak_sessions/<run_id>/soak_summary.json`
- `reports/soak_sessions/<run_id>/soak_summary.md`
- `reports/soak_sessions/<run_id>/runtime_health.json`
- `reports/soak_sessions/<run_id>/runtime_status.md`
- `reports/soak_sessions/<run_id>/runtime_cycles.jsonl`
- `reports/soak_sessions/<run_id>/runtime_cycle_summaries.jsonl`
- `reports/soak_sessions/<run_id>/health_transitions.jsonl`
- `reports/soak_sessions/<run_id>/reconnect_events.jsonl`
- `reports/soak_sessions/<run_id>/listen_key_refresh.jsonl`
- `reports/soak_sessions/<run_id>/reconciliation_events.jsonl`
- signed-path precheck artifacts if used:
  - `reports/signed_path_verification/<run_id>/signed_path_summary.json`
  - `reports/signed_path_verification/<run_id>/signed_path_summary.md`
- operator notes with action timestamps

## 7. Pass / Fail Criteria

### Exercise pass

The exercise counts as a meaningful active-event pass when all are true:

1. signed bootstrap succeeds
2. at least one real private order/account event is observed in the runtime path
3. canonical translation is explainable from the artifacts
4. no crash or malformed-event cascade occurs
5. mutation behavior is explainable:
   - applied when clearly safe
   - blocked when clearly unsafe or incomplete

### Exercise fail

The exercise is a fail when:

1. private bootstrap never succeeds
2. runtime artifacts are missing or contradictory
3. event arrival causes translator failure or repeated malformed handling without clear cause
4. mutation happens in a way that cannot be explained safely
5. reconciliation escalates to manual attention without a clear and documented reason

### Pass with gaps

Use this when:

- the run proves create/cancel/fill event ingestion
- but partial fill was not achieved
- or balance/account update evidence is weak
- or signed-path live proof was not fully completed before the run

## 8. What Counts As Proof Vs Non-Proof

### Proof

Counts as proof:

- private order/account events appear in runtime artifacts
- their timing can be matched to operator notes
- runtime behavior remains explainable through:
  - `runtime_health.json`
  - `runtime_status.md`
  - `reconciliation_events.jsonl`
  - cycle alerts and summaries

### Non-proof

Does not count as proof:

- another idle run with no private events
- a run where only bootstrap succeeded but no private order/account event arrived
- a run where the operator did not record action timing
- a run where artifacts exist but cannot be matched to the intended manual event sequence

## 9. How To Distinguish Failure Classes

### Signing issue

Likely signing issue if:

- signed-path harness reports `not verified`
- bootstrap or signed lookup fails with `INVALID_SIGNATURE` or `-1022`
- no private session is established at all

### Parser issue

Likely parser/translator issue if:

- private events arrive but translation becomes malformed unexpectedly
- runtime artifacts show event presence with malformed translation alerts
- the event shape is valid from Binance but runtime2 cannot translate it safely

### Exchange behavior issue

Likely exchange behavior issue if:

- testnet simply does not produce the targeted event shape reliably
- partial fill does not occur despite repeated realistic attempts
- order behavior differs from expectation without any runtime parsing/signing error

### Reconcile issue

Likely reconciliation issue if:

- private truth is incomplete
- status lookup path is invoked
- reconciliation remains unexplained or escalates without matching the observed event gap

### Mutation-gate issue

Likely mutation-gate issue if:

- canonical events appear
- translation looks valid
- but mutation remains blocked unexpectedly
- or mutation applies when the state should still be ambiguous

## 10. Recommended Scenario Sequence

Run these in order from simplest to hardest.

### Scenario 1. Create acknowledgement only

Goal:
- prove private order acknowledgement arrives and is translated safely

Why first:
- simplest active private-event proof

### Scenario 2. Cancel acknowledgement

Goal:
- prove a resting order can generate a cancel acknowledgement and the runtime remains explainable

Why second:
- still simple, but exercises another lifecycle branch

### Scenario 3. Immediate full fill

Goal:
- prove a fill-bearing order path produces canonical translation and explainable downstream behavior

Why third:
- this is the first meaningful fill-path proof

### Scenario 4. Balance/account update observation

Goal:
- confirm account/balance update shows up around the event sequence

Why fourth:
- useful, but may depend on testnet behavior timing

### Scenario 5. Partial fill attempt

Goal:
- collect partial-fill evidence if realistically achievable

Why last:
- least reliable on Spot testnet
- should not block earlier success claims for simpler event classes

## 11. Recommended Duration And Capture Window

Recommended first active-event run:
- `1h`
- `20` to `40` cycles

This is long enough to:
- complete signed bootstrap
- perform a small set of manual exchange actions
- capture post-event reconciliation/health artifacts

It is short enough to:
- review quickly
- avoid treating the session as a durability campaign prematurely

## 12. Key Risks In Execution

- testnet partial fill may not be realistically reproducible
- operators may collect an idle run by accident if they do not generate real events
- signed-path proof may still be incomplete if the live verification harness is skipped
- operator notes may be too weak to correlate artifacts to manual actions
- exchange behavior may be blamed on runtime2 without first checking signing/bootstrap and testnet behavior

## 13. Recommended First Live Exercise Scenario

Recommended first scenario:
- create acknowledgement
- cancel acknowledgement
- one immediate full-fill attempt

Reason:
- this is the highest-value, lowest-ambiguity event sequence likely achievable on Spot testnet
- it can prove active private-event ingestion without over-relying on partial-fill behavior

## 14. Conservative Conclusion

The first active private-event exercise should be treated as a short, bounded, evidence-collection rehearsal.

Success means:
- runtime2 finally has proof beyond idle durability

Failure does not automatically mean runtime2 is wrong:
- it may still be a signing issue
- a testnet behavior issue
- an operator workflow issue
- or a reconciliation/mutation-gate issue that now has better evidence than before
