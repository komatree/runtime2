# runtime2 r5 Broader Baseline Summary

## Authoritative Evidence Set

Use the following as the authoritative broader `restricted_live_rehearsal` baseline:

- runtime:
  - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
- scheduler:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
- action windows:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

## Final Result

- broader-stage classification: `PASS WITH CAUTION`
- broader-stage readiness verdict: sufficient to exit the broader `restricted_live_rehearsal` stage

## What r5 Proved

### Safety proof

- `stop_reason: completed`
- `aborted: false`
- `blocked_mutation_count: 0`
- final exchange health `healthy`
- reconciliation remained automatic with no manual attention

### Continuity proof

- one lineage-valid `6h` runtime session completed
- the session remained reviewable despite reconnect and heartbeat churn
- reconnect churn stayed non-destructive

### Lineage proof

- `runtime_session.json` bound the scheduler to the runtime session
- `scheduler_manifest.json` and `scheduler_events.jsonl` preserved per-session action lineage
- `r5-a1`, `r5-a2`, and `r5-a3` remained clearly bound to runtime run `r5`

### Active-window proof

- all three planned windows executed inside the same runtime session
- all three windows produced reviewable action-driver artifacts
- runtime correlation was preserved for all three windows
- account-update visibility remained adequate across the broader session

## Why Broader Stage Is Closed

The broader stage is closed because `r5` answered the broader-stage question directly:

- repeated active windows can be sustained within one session
- runtime/session lineage remains clean
- reconciliation remains clean
- blocked mutation remained absent
- reconnect churn did not become destructive

This means broader repeated-window `restricted_live_rehearsal` no longer remains an open gate question unless later evidence shows regression.

## Why The Result Is PASS WITH CAUTION

The result is not a plain pass because two non-blocking cautions remained:

- `a2` and `a3` completed as `PARTIAL_SUCCESS_NONBLOCKING` due to `-1013 PERCENT_PRICE_BY_SIDE` on the resting create leg
- reconnect and heartbeat churn remained high during the session

These cautions did not block stage closure because they did not break lineage, did not create blocked mutations, did not require manual attention, and did not prevent repeated in-session evidence.

## Next Stage

The next stage is a bounded operator / bounded micro-live stage.

What remains unchanged:

- fail-closed posture
- stale-output fail-if-exists behavior
- runtime/session lineage model
- scheduler late-start abort behavior
- blocked-mutation and reconciliation stop rules

What should be monitored explicitly:

- scheduler completion
- per-window `action_driver_result.json`
- reconciliation convergence
- account-update visibility
- reconnect / `eventStreamTerminated` handling
- final exchange health
