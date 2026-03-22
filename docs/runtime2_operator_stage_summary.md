# runtime2 Operator Stage Summary

## Purpose

This document freezes the current `runtime2` bounded operator stage before splitting work between Development PC and Operations PC.

It records:
- the currently validated state
- the current execution constraints
- the known caution classes
- the known bounded-stage incident
- what is allowed and not allowed at this stage

## Current Validated State

Broader rehearsal stage:
- closed on authoritative `r5` baseline
- baseline summary:
  - [`docs/runtime2_r5_broader_baseline_summary.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_r5_broader_baseline_summary.md)

Authoritative broader baseline evidence:
- runtime:
  - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
- scheduler:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
- action windows:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

Bounded operator results recorded so far:
- `binance-bounded-preflight-r1-30m`: `PASS WITH CAUTION`
- `binance-bounded-r1-4h`: `PASS WITH CAUTION`
- `binance-bounded-r2-4h`: `PASS WITH CAUTION`
- `binance-bounded-r3-4h`: `PASS WITH CAUTION`
- `binance-bounded-r4-8h`: `PASS WITH CAUTION`
- `binance-bounded-r5-8h`: `FAIL`
- `binance-envcheck-r0-1h`: `ENV-CHECK PASS WITH CAUTION`

## Current Constraints

Current execution model must remain unchanged:
- runtime:
  - [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py)
- scheduler:
  - [`scripts/run_broader_action_windows.py`](/home/terratunes/code/trading/runtime2/scripts/run_broader_action_windows.py)
- action driver:
  - [`scripts/run_testnet_event_action_driver.py`](/home/terratunes/code/trading/runtime2/scripts/run_testnet_event_action_driver.py)

Current operator constraints:
- keep the same runtime/session lineage model
- keep fail-closed scheduler late-abort behavior
- keep stale-output fail-if-exists behavior
- keep restricted-live rehearsal order-submission protections
- do not resume interrupted runs
- do not reuse interrupted run ids

## Known Caution Classes

Known non-destructive caution classes at this stage:
- `PERCENT_PRICE_BY_SIDE` causing `PARTIAL_SUCCESS_NONBLOCKING` action windows
- reconnect / heartbeat churn during longer sessions

Operator meaning:
- these caution classes are known and reviewable
- they do not count as success blockers by themselves when:
  - runtime completes cleanly
  - scheduler completes the intended window plan
  - lineage remains complete
  - blocked mutation remains zero

## Known Incident Summary

Known bounded-stage incident:
- run id:
  - `binance-bounded-r5-8h`
- observed issues:
  - scheduler recorded `window_aborted_late` for `a2`
  - `a3` did not execute
  - `scheduler_complete` was absent
  - final runtime artifact set was missing
- retained evidence:
  - [`reports/event_exercises/binance-bounded-r5-8h-scheduler/scheduler_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-bounded-r5-8h-scheduler/scheduler_events.jsonl)
  - [`reports/soak_sessions/binance-bounded-r5-8h/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r5-8h)

Current evidence-based interpretation:
- the failure pattern is most consistent with an interruption class affecting the execution environment or session continuity
- the run is not valid success evidence
- interrupted or incomplete runs must be treated as failed runs, not partial passes

## Allowed At This Stage

Allowed:
- bounded operator runs
- short env-check runs
- repeated bounded retries with fresh run ids
- artifact-driven review on Development PC
- wrapper and preflight use that preserves the current execution model

Not allowed:
- treating interrupted runs as successful evidence
- manually editing or reconstructing missing run artifacts
- resuming scheduler windows inside an interrupted run id
- resuming runtime finalization for a partially retained run
- redesigning runtime, scheduler, or lineage behavior during this stage-freeze window

## Valid vs Invalid Retained Evidence

Valid retained bounded-run evidence includes:
- `runtime_session.json`
- `runtime_cycles.jsonl`
- `runtime_health.json`
- `runtime_status.md`
- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `reconciliation_events.jsonl`
- `listen_key_refresh.jsonl`
- `account_update_events.jsonl`
- `soak_summary.json`
- `soak_summary.md`
- `scheduler_manifest.json`
- `scheduler_events.jsonl`
- per-window `action_driver_result.json`

Invalid interrupted-run evidence includes:
- missing `soak_summary.json`
- missing `soak_summary.md`
- missing scheduler completion for a normal bounded run
- missing planned action-window result artifacts
- `window_aborted_late` under default fail-closed policy

## Next-Step Items

Current next-step items:
- preserve the current execution model
- keep operator review artifact-based
- keep host power and sleep discipline explicit for long runs
- use fresh run ids after any interruption
- keep Development PC focused on code, analysis, and docs
- keep Operations PC focused on exchange-connected execution and artifact collection
