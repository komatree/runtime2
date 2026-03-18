# runtime2 Event Exercise Harness Usage

## Purpose

This document explains the minimal testnet-only helper harness for the first active private-event exercise.

Helper:
- [`scripts/run_runtime2_testnet_event_exercise.py`](/home/terratunes/code/trading/runtime2/scripts/run_runtime2_testnet_event_exercise.py)

This helper does not automate general trading.
It only orchestrates:
- preflight use
- signed-path precheck
- bounded restricted-live soak execution
- artifact summary creation

## What The Harness Automates

The harness automates:

1. testnet-only config validation
2. environment safety checks for the exercise path
3. optional signed-path precheck via the existing signed-path harness
4. launch of the bounded restricted-live soak session
5. creation of an exercise summary under:
   - `reports/event_exercises/<run_id>/`

The harness does not automate:

1. order submission
2. cancel submission
3. exchange-side manual action timing
4. final proof judgement of event correctness

## Recommended Command

```bash
env BINANCE_API_KEY='your_testnet_key' BINANCE_API_SECRET='your_testnet_secret' \
python scripts/run_runtime2_testnet_event_exercise.py \
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

## Prepare-Only Mode

If the operator wants the plan/instructions written without launching the soak:

```bash
env BINANCE_API_KEY='your_testnet_key' BINANCE_API_SECRET='your_testnet_secret' \
python scripts/run_runtime2_testnet_event_exercise.py \
  --prepare-only \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

## Manual Event Sequence

The harness expects the operator to perform this manual sequence during the bounded soak:

1. create one small order intended to produce acknowledgement
2. cancel one resting order intended to produce cancel acknowledgement
3. create one order intended to fill fully if realistically achievable
4. record approximate wall-clock time for each action

## Output Paths

Harness-specific output:
- `reports/event_exercises/<run_id>/exercise_plan.json`
- `reports/event_exercises/<run_id>/exercise_instructions.md`
- `reports/event_exercises/<run_id>/exercise_summary.json`
- `reports/event_exercises/<run_id>/exercise_summary.md`

Signed-path output:
- `reports/event_exercises/<run_id>/signed_path_verification/`

Soak output:
- `reports/soak_sessions/<run_id>/`

## Pass / Fail Interpretation

Harness pass means:
- preflight succeeded
- signed-path precheck succeeded if enabled
- soak launched and completed without process-level failure
- exercise summary artifacts were written

Harness pass does not automatically mean:
- active private-event proof is complete
- canonical event behavior is fully proven

The harness summary intentionally keeps:
- `operator_review_required = true`

## Remaining Scenarios Not Yet Automated

Not automated yet:
- explicit cancel automation
- partial-fill-targeting logic
- balance/account update targeting logic
- active-event proof judgement beyond a simple heuristic

That is intentional.
The helper remains narrow and evidence-focused.
