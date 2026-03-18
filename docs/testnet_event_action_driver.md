# Testnet Event Action Driver

`scripts/run_testnet_event_action_driver.py` is a narrow Binance Spot testnet-only helper for producing reviewable private-event evidence without depending on freeform operator notes.

## What It Does

- fails closed unless the config points to `binance_spot_testnet`
- uses `BINANCE_API_KEY` and `BINANCE_API_SECRET` from the current shell
- writes artifacts under `reports/event_exercises/<run_id>/action_driver/`
- records timestamped action results into:
  - `action_driver_events.jsonl`
  - `action_driver_summary.md`

The mandatory core flow is:

1. place one small resting `LIMIT BUY` order intended to create an acknowledgement event
2. cancel that same resting order to create a cancel acknowledgement event

Optional flow:

3. place one small `MARKET BUY` fill-attempt order when `--enable-fill-attempt` is set

## Why This Exists

The earlier bounded manual-event rehearsals created `operator_action_notes.md`, but the `Actual actions` section remained empty. That made the runs hard to review:

- the runtime path was healthy enough to subscribe and cycle
- but the evidence trail could not prove whether exchange actions were actually performed

This driver closes that evidence gap by automating both:

- action generation on Spot testnet
- timestamped action-result recording in the run directory

It does not replace the runtime2 rehearsal path. It only makes the event-generation side reviewable.

## Usage

Run the action driver first:

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

Then run the existing bounded runtime rehearsal with the same `run_id` family:

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

## Review Expectations

The action driver proves that testnet actions were actually submitted and records:

- action timestamp
- action type
- symbol
- side
- order type
- quantity
- success or failure class
- exchange order identifiers needed for later correlation

Client order ids are generated in a Binance-safe form:

- allowed characters only: `[a-zA-Z0-9-_]`
- maximum length: `36`
- deterministic short hash from `run_id`
- action suffix:
  - `c` for create
  - `f` for fill attempt

That closes the weakest reviewability gap from the manual-note workflow. It does not, by itself, prove that runtime2 ingested the resulting private events. That still requires reviewing the bounded runtime artifacts under `reports/soak_sessions/<run_id>/`.

## Failure Diagnostics

When Binance returns HTTP `4xx` or `5xx`, the driver now captures the response body and records sanitized exchange error detail in:

- `action_driver_events.jsonl`
- `action_driver_summary.md`

If Binance returns a standard JSON error such as:

```json
{"code": -1013, "msg": "Filter failure: LOT_SIZE"}
```

the recorded action detail will include that `code/msg` instead of only a generic HTTP status.
