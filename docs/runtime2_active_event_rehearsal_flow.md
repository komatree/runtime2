# runtime2 Active Event Rehearsal Flow

This flow replaces the earlier manual-note workflow for bounded active private-event rehearsal on Binance Spot testnet.

The goal is not broad live execution. The goal is to produce a reviewable evidence set that answers two questions:

1. were real testnet actions actually generated?
2. did runtime2 ingest the resulting private events?

## Prerequisites

- Spot testnet config is in use:
  - [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml)
- local bootstrap inputs exist:
  - [`data/binance/btcusdt_4h.json`](/home/terratunes/code/trading/runtime2/data/binance/btcusdt_4h.json)
  - [`data/binance/btcusdt_1d.json`](/home/terratunes/code/trading/runtime2/data/binance/btcusdt_1d.json)
- real Spot testnet credentials are loaded into the current shell:
  - `BINANCE_API_KEY`
  - `BINANCE_API_SECRET`
- operator has reviewed:
  - [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md)
  - [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md)
  - [`docs/testnet_event_action_driver.md`](/home/terratunes/code/trading/runtime2/docs/testnet_event_action_driver.md)

## Credential / Testnet Prechecks

1. Confirm the shell has plausible credentials:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/check_binance_testnet_credentials.py \
  --config configs/runtime2_restricted_live_testnet.toml
```

Required interpretation:
- status must be locally plausible
- do not proceed if the helper reports missing env vars, placeholder-like values, or invalid apiKey shape

2. Confirm signed-path acceptance on current Spot testnet:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/verify_binance_signed_paths_testnet.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --allow-live-testnet \
  --output-dir reports/signed_path_verification/latest
```

Required interpretation:
- REST signed path must not fail with auth/signature error
- WS signed path must be accepted
- do not proceed to active-event rehearsal if the signed-path gate is still blocked

## Start runtime2 Bounded Rehearsal

Use a bounded run that keeps the rehearsal small and reviewable.

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/run_runtime2_testnet_event_exercise.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --run-id binance-testnet-active-private-driver-1-runtime \
  --duration-hours 1 \
  --cycles 4 \
  --poll-interval-seconds 30 \
  --output-subdir soak_sessions \
  --max-blocked-mutations 3 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

Required interpretation:
- the bounded rehearsal must stay in `restricted_live_rehearsal`
- this path still does not submit live runtime2 orders

## Run the Testnet Event Action Driver

Run the automated action driver during the bounded rehearsal window.

Mandatory core flow:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/run_testnet_event_action_driver.py \
  --run-id binance-testnet-active-private-driver-1 \
  --config configs/runtime2_restricted_live_testnet.toml \
  --symbol BTCUSDT \
  --qty 0.010
```

Optional fill attempt:

```bash
env BINANCE_API_KEY='your_real_testnet_key' BINANCE_API_SECRET='your_real_testnet_secret' \
python scripts/run_testnet_event_action_driver.py \
  --run-id binance-testnet-active-private-driver-1 \
  --config configs/runtime2_restricted_live_testnet.toml \
  --symbol BTCUSDT \
  --qty 0.010 \
  --enable-fill-attempt
```

Recommended convention:
- keep the action-driver run id and runtime run id obviously related
- example:
  - action driver: `binance-testnet-active-private-driver-1`
  - runtime rehearsal: `binance-testnet-active-private-driver-1-runtime`

## Expected Artifact Locations

Signed-path verification:
- `reports/signed_path_verification/latest/signed_path_summary.json`
- `reports/signed_path_verification/latest/signed_path_summary.md`

Action driver:
- `reports/event_exercises/<action_run_id>/action_driver/action_driver_events.jsonl`
- `reports/event_exercises/<action_run_id>/action_driver/action_driver_summary.md`

Bounded runtime rehearsal:
- `reports/event_exercises/<runtime_run_id>/exercise_summary.json`
- `reports/event_exercises/<runtime_run_id>/exercise_summary.md`
- `reports/soak_sessions/<runtime_run_id>/soak_summary.json`
- `reports/soak_sessions/<runtime_run_id>/soak_summary.md`
- `reports/soak_sessions/<runtime_run_id>/runtime_cycles.jsonl`
- `reports/soak_sessions/<runtime_run_id>/runtime_health.json`
- `reports/soak_sessions/<runtime_run_id>/reconciliation_events.jsonl`
- `reports/soak_sessions/<runtime_run_id>/reconnect_events.jsonl`

## What Counts As Success

Minimum evidence success requires both sides:

Action side:
- action driver records a successful create action
- action driver records a successful cancel action
- if fill attempt was enabled, its result is explicitly recorded as success or failure
- order ids/client order ids are present for correlation where available

Runtime side:
- bounded runtime rehearsal completes without bootstrap failure
- runtime artifacts do not show fatal stop or abort
- runtime artifacts show evidence of live private payload ingestion, not only idle private-stream subscription

Stronger success:
- create acknowledgement is reviewable in runtime evidence
- cancel acknowledgement is reviewable in runtime evidence
- balance/account update or fill-related event is reviewable if it actually happened

## What Counts As Ambiguous

Ambiguous, not sufficient:
- action driver shows successful actions, but runtime artifacts still only show:
  - `no private payloads available for restricted-live mutation gate`
  - `restricted-live portfolio mutation gate observed no live updates`
- runtime rehearsal completes cleanly, but no correlatable private-event evidence appears
- fill attempt was requested, but testnet behavior leaves it unclear whether a fill occurred

Not enough:
- signed-path gate was not cleared first
- action driver was not run
- action driver failed before create/cancel completed
- runtime artifacts are missing

## How Codex Should Review The Resulting Artifacts

Codex review should compare both evidence streams together.

Required review set:
- action driver:
  - `reports/event_exercises/<action_run_id>/action_driver/action_driver_events.jsonl`
  - `reports/event_exercises/<action_run_id>/action_driver/action_driver_summary.md`
- bounded runtime:
  - `reports/event_exercises/<runtime_run_id>/exercise_summary.json`
  - `reports/event_exercises/<runtime_run_id>/exercise_summary.md`
  - `reports/soak_sessions/<runtime_run_id>/soak_summary.json`
  - `reports/soak_sessions/<runtime_run_id>/runtime_cycles.jsonl`
  - `reports/soak_sessions/<runtime_run_id>/runtime_health.json`
  - `reports/soak_sessions/<runtime_run_id>/reconciliation_events.jsonl`
  - `reports/soak_sessions/<runtime_run_id>/reconnect_events.jsonl`

Codex should answer:
1. did the action driver prove real testnet actions were generated?
2. did runtime2 show private-event evidence after those actions?
3. did reconciliation remain unused, remain clean, or show an issue?
4. is the dominant interpretation:
   - active private-event captured
   - operator/action-generation gap closed but runtime ingestion still not proven
   - likely runtime ingestion gap

## When To Suspect Operator Gap vs Runtime Ingestion Gap

Suspect operator gap or evidence gap when:
- the action driver was not run
- the action driver failed before create/cancel completed
- action-driver artifacts are missing

Suspect runtime ingestion gap more seriously when:
- signed-path gate is cleared
- action driver clearly records successful create and cancel actions
- runtime rehearsal stays subscribed and cycles cleanly
- runtime artifacts still show only idle private-stream alerts with no private-event evidence

Do not call it a runtime defect from console output alone. Use the persisted artifacts.

## Checklist

1. Run credential sanity check.
2. Run signed-path live verification.
3. Start bounded runtime rehearsal.
4. Run the testnet event action driver during the rehearsal window.
5. Preserve both action-driver and runtime artifact paths.
6. Review the combined artifact set.
7. Only then classify the run as proven, partially proven, or not proven.
