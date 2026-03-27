# runtime2 Current Status

## Executive Summary

`runtime2` is currently in a bounded operator validation stage.

Current evidence supports:
- bounded-stage operation is usable
- scheduler continuity is stable on the latest retained bounded success baseline
- runtime finalization failure is no longer the defining failure class
- known bounded-stage cautions remain:
  - `PERCENT_PRICE_BY_SIDE`
  - reconnect / heartbeat churn

This is not yet a micro-live promotion document.

## Architecture State

Current execution shape remains:
- runtime:
  - [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py)
- scheduler:
  - [`scripts/run_broader_action_windows.py`](/home/terratunes/code/trading/runtime2/scripts/run_broader_action_windows.py)
- action driver:
  - [`scripts/run_testnet_event_action_driver.py`](/home/terratunes/code/trading/runtime2/scripts/run_testnet_event_action_driver.py)

Current stage rule:
- no scheduler model change
- no lineage model change
- no broad runtime redesign

## Execution State

Current bounded-stage baseline:
- `binance-bounded-r6-8h`

Retained evidence:
- runtime completed cleanly:
  - [`reports/soak_sessions/binance-bounded-r6-8h/soak_summary.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r6-8h/soak_summary.json)
- finalization completed:
  - [`reports/soak_sessions/binance-bounded-r6-8h/finalization_debug.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r6-8h/finalization_debug.json)
- scheduler completed:
  - [`reports/event_exercises/binance-bounded-r6-8h-scheduler/scheduler_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-bounded-r6-8h-scheduler/scheduler_events.jsonl)
- reconciliation converged without manual attention:
  - [`reports/soak_sessions/binance-bounded-r6-8h/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r6-8h/reconciliation_events.jsonl)

## Validation State

What is currently proven:
- bounded wrapper launch works on the current path
- runtime finalization can complete normally
- scheduler can complete all planned windows
- retained artifact family can be complete
- reconciliation can converge cleanly on the bounded baseline

What is currently not yet proven:
- repeatable low-churn private-stream behavior over bounded long runs
- reduced or eliminated `PERCENT_PRICE_BY_SIDE` action-window caution
- micro-live readiness

## Current Operational Readiness

Current readiness statement:
- bounded operator stage: operationally usable
- micro-live: not yet promoted

This is supported by the retained `r6` baseline and by the current fail-closed review posture in:
- [`docs/runtime2_run_classification.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_run_classification.md)
- [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md)

## Current Main Open Issues

- reconnect / heartbeat churn remains high in the retained `r6` bounded baseline:
  - `reconnect_count = 234`
  - `heartbeat_overdue_events = 233`
- `PERCENT_PRICE_BY_SIDE` remains present in retained `r6` action-window results
- repeatability still matters even though finalization completed on `r6`

## Evidence Gaps

Retained artifact gaps still exist for some earlier bounded-stage runs:
- `binance-bounded-preflight-r1-30m`: retained runtime artifact directory not found locally
- `binance-bounded-r1-4h`: retained runtime artifact directory not found locally

Those runs are still recorded in existing operator-stage docs, but the local retained artifact set is incomplete for independent re-review.
