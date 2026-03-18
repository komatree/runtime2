# runtime2 Account Update Rehearsal Plan

## Objective

Produce one bounded paired rehearsal that yields explicit, reviewable account/balance-update evidence from Binance Spot testnet for `runtime2`.

This plan is narrower than general active-event rehearsal. It is only trying to answer:

- did runtime2 observe clear account-side private update evidence
- not just order-state change
- not just inferred balance effect from a snapshot mismatch alert

## Why Account/Balance Proof Is Still Only Partial

Current reviewed evidence is already strong for:
- create/cancel active private-event proof
- fill-related private-event handling
- reconciliation convergence across `cancelled` and `filled`

But account-side proof is still partial because the strongest account-related signal so far is:
- `account snapshot mismatch after projected portfolio translation: BTC,USDT`

That is useful, but it is still weaker than an explicitly reviewable account-side private update surface. It proves something account-related happened, but not as cleanly as:
- a directly attributable account/private update
- or an isolated artifact sequence showing order fill followed by account/balance-side change

## Recommended Scenario

Use one bounded paired rehearsal where the action driver only needs to produce one successful fill attempt, and the runtime rehearsal window is kept short and reviewable.

Recommended shape:
- no requirement for a successful resting create/cancel in this scenario
- one successful small `MARKET BUY` fill attempt on `BTCUSDT`
- bounded runtime rehearsal that spans the fill and the immediate post-fill account-side processing window

Why this is the best smallest scenario:
- a successful fill is the cleanest likely trigger for both:
  - fill-related order evidence
  - balance/account-side evidence
- it reuses the existing driver and bounded rehearsal path
- it avoids broadening into general trading automation
- it keeps the evidence window small enough to review manually

## Exact Paired Flow

### 1. Runtime Rehearsal

Start the bounded runtime rehearsal first:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/run_runtime2_testnet_event_exercise.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --run-id binance-testnet-account-update-r1 \
  --duration-hours 1 \
  --cycles 4 \
  --poll-interval-seconds 30 \
  --output-subdir soak_sessions \
  --max-blocked-mutations 3 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

### 2. Action Driver

During that bounded window, run the driver with fill attempt enabled:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/run_testnet_event_action_driver.py \
  --run-id binance-testnet-account-update-a1 \
  --config configs/runtime2_restricted_live_testnet.toml \
  --symbol BTCUSDT \
  --qty 0.01 \
  --enable-fill-attempt
```

Interpretation:
- if the resting create fails due to price-band filter again, that does not invalidate this scenario
- the critical success condition is the fill-attempt action succeeding and recording an exchange order id

## What Action Shape Is Most Likely To Surface Explicit Account-Side Evidence

Most likely:
- one successful small `MARKET BUY`

Why:
- it should immediately change balances on Spot testnet
- it already proved fill-related runtime evidence in the reviewed paired fill scenario
- it is more likely than a passive resting order to create an account-side delta that can be reviewed nearby in time

Less useful for this specific goal:
- resting create alone
- cancel alone

Those are already proven for order-state purposes, but they are weaker triggers for explicit balance-side proof.

## Required Artifacts To Inspect

Action side:
- `reports/event_exercises/<action_run_id>/action_driver/action_driver_events.jsonl`
- `reports/event_exercises/<action_run_id>/action_driver/action_driver_summary.md`

Runtime side:
- `reports/soak_sessions/<runtime_run_id>/runtime_cycles.jsonl`
- `reports/soak_sessions/<runtime_run_id>/account_update_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/runtime_health.json`
- `reports/soak_sessions/<runtime_run_id>/reconciliation_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/reconnect_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/soak_summary.md`
- `reports/soak_sessions/<runtime_run_id>/runtime_status.md`

Any additional relevant runtime artifacts under the same run directory should also be inspected if they contain account/account-snapshot references.

## Pass / Fail Criteria

### Pass

Minimum pass requires all of the following:
- action driver records a successful fill attempt with a concrete exchange order id
- runtime artifacts show active handling for the same order id or the same fill window
- runtime artifacts contain explicit account-side evidence stronger than order-state-only recovery

Examples of acceptable explicit account-side evidence:
- one or more rows in `account_update_events.jsonl` tied to the active fill window
- a clearly attributable account-update/account-snapshot artifact beyond a generic mismatch alert
- a runtime artifact showing account-side change tied to the same active window and assets affected by the fill

### Fail

Fail if any of the following is true:
- fill attempt does not succeed
- runtime never moves beyond idle private-stream alerts
- only order-state recovery is visible and no account-side evidence appears
- artifacts are incomplete or ambiguous enough that account-side proof still depends on guesswork

## What Counts As Explicit Account-Update Proof

Explicit account-update proof means one of:
- a runtime artifact directly showing account/balance-side private update handling
- a clearly isolated account snapshot or account-update surface tied to the active fill window

For the current bounded rehearsal artifact set, the preferred direct source is:
- `reports/soak_sessions/<runtime_run_id>/account_update_events.jsonl`

Review guidance:
- if `account_update_events.jsonl` contains rows whose timestamps and assets line up with the paired fill window, treat that as explicit account-update proof
- if the only account-side signal is still an `account snapshot mismatch after projected portfolio translation` alert, treat that as inferred balance effect only

This is stronger than:
- `account snapshot mismatch after projected portfolio translation`

That mismatch alert is still useful, but by itself it is only inferred balance effect, not explicit proof.

## Distinguishing The Evidence Classes

### Order-State-Only Evidence

Examples:
- `unknown execution ids observed`
- reconciliation converged to `filled` or `cancelled`
- same order id appears in recovery artifacts

This proves order lifecycle handling, not account-side proof by itself.

### Inferred Balance Effect

Examples:
- account snapshot mismatch after projected translation
- asset symbols like `BTC,USDT` appear in a safety-gate alert

This is stronger than nothing, but still partial.

### Explicit Account-Update / Private Account Evidence

Examples:
- clearly attributable account-side runtime artifact during the fill window
- a direct account/balance update surface in persisted runtime artifacts such as `account_update_events.jsonl`

This is the target for this rehearsal.

## Review Outcome Categories

- `PROVEN`
  - fill happened
  - runtime captured fill-related handling
  - runtime also captured explicit account-side evidence

- `PARTIALLY PROVEN`
  - fill happened
  - runtime captured fill-related handling
  - only inferred balance/account effect is visible

- `NOT PROVEN`
  - fill did not happen
  - or runtime remained idle
  - or account-side evidence is absent/ambiguous

## Exact Next Execution Target

Use this paired target:
- action run id: `binance-testnet-account-update-a1`
- runtime run id: `binance-testnet-account-update-r1`

This keeps the scenario bounded, reuses the current driver and rehearsal flow, and focuses the remaining evidence gap on the smallest unresolved account-side question.
