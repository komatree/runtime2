# runtime2 Release Notes

## 2026-03-19

### Broader restricted-live rehearsal baseline established

- Broader restricted-live session lineage is now anchored by `runtime_session.json`, `scheduler_manifest.json`, and runtime-derived action run ids.
- Scheduler and action-window output reuse now fails closed instead of silently reusing stale directories.
- Broader scheduler continuity now distinguishes:
  - `SUCCESS`
  - `PARTIAL_SUCCESS_NONBLOCKING`
  - `FATAL_FAILURE`
- Non-fatal reviewable windows no longer stop the broader session by default.

### Authoritative broader baseline

The authoritative broader `restricted_live_rehearsal` baseline is:

- runtime:
  - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
- scheduler:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
- action windows:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

Recorded result:

- broader-stage classification: `PASS WITH CAUTION`
- broader-stage readiness verdict: sufficient to exit the broader `restricted_live_rehearsal` stage

Known cautions carried forward:

- `a2` and `a3` remained `PARTIAL_SUCCESS_NONBLOCKING` due to `PERCENT_PRICE_BY_SIDE`
- reconnect / heartbeat churn remained high but non-destructive

### Next stage framing

The next stage is a bounded operator / bounded micro-live stage using:

- the same lineage/session model
- the same stale-output protection
- the same fail-closed restricted-live safeguards
