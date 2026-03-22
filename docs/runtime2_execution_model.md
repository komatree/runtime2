# runtime2 Execution Model

## Purpose

This document defines the current `runtime2` bounded operator execution model exactly as it exists in the repository.

It is an implementation-facing description of:
- runtime
- scheduler
- action driver
- artifact lineage
- fail-closed behavior

It is not a redesign document.

## Canonical Entrypoints

Runtime:
- [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py)

Scheduler:
- [`scripts/run_broader_action_windows.py`](/home/terratunes/code/trading/runtime2/scripts/run_broader_action_windows.py)

Action driver:
- [`scripts/run_testnet_event_action_driver.py`](/home/terratunes/code/trading/runtime2/scripts/run_testnet_event_action_driver.py)

Wrapper surface:
- [`scripts/run_broader_rehearsal_6h_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/run_broader_rehearsal_6h_wsl.sh)
- [`scripts/run_broader_rehearsal_smoke30_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/run_broader_rehearsal_smoke30_wsl.sh)

## Runtime / Scheduler / Action Driver Roles

Runtime responsibilities:
- launch one bounded restricted-live rehearsal session
- create `runtime_session.json`
- run repeated cycles
- persist cycle-level runtime artifacts
- write final soak artifacts after the soak run returns

Scheduler responsibilities:
- derive action timing from `runtime_session.json`
- bind action runs to the runtime run id
- launch planned windows at explicit offsets
- fail closed if a window is reached too late under default policy

Action driver responsibilities:
- execute a single planned action window
- persist a machine-readable result artifact
- persist an operator-readable summary

## Artifact Lineage Model

The lineage model is:

1. runtime run id
2. runtime session artifact
3. scheduler run id derived from runtime run id
4. action run ids derived from runtime run id

Example:
- runtime:
  - `binance-bounded-r4-8h`
- scheduler:
  - `binance-bounded-r4-8h-scheduler`
- actions:
  - `binance-bounded-r4-8h-a1`
  - `binance-bounded-r4-8h-a2`
  - `binance-bounded-r4-8h-a3`

Runtime source-of-truth artifact:
- [`reports/soak_sessions/<run_id>/runtime_session.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions)

Scheduler lineage artifacts:
- [`reports/event_exercises/<run_id>-scheduler/scheduler_manifest.json`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-scheduler/scheduler_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises)

Action lineage artifacts:
- [`reports/event_exercises/<run_id>-a1/action_driver/action_driver_result.json`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- same pattern for `a2` and `a3`

## Scheduler Window Logic

Default planned offsets:
- `a1 = 20 minutes`
- `a2 = 140 minutes`
- `a3 = 260 minutes`

Default modes:
- `fill fill fill`

The scheduler computes each planned window time from:
- `runtime_session.json.started_at`
- plus `offset_minutes`

Late-window policy is fail-closed by default:
- `--late-policy abort`
- `--late-grace-seconds 20`

If the scheduler reaches a window more than 20 seconds late:
- it writes `window_aborted_late`
- it exits non-zero
- later windows do not run

Reference:
- [`scripts/run_broader_action_windows.py`](/home/terratunes/code/trading/runtime2/scripts/run_broader_action_windows.py)

## Runtime Finalization Model

Two artifact families are written at different times.

Incremental runtime artifacts:
- written during the run on each cycle
- examples:
  - `runtime_cycles.jsonl`
  - `runtime_health.json`
  - `runtime_status.md`

Final soak artifacts:
- written after the soak runner returns
- examples:
  - `health_transitions.jsonl`
  - `reconnect_events.jsonl`
  - `listen_key_refresh.jsonl`
  - `reconciliation_events.jsonl`
  - `account_update_events.jsonl`
  - `soak_summary.json`
  - `soak_summary.md`

Reference:
- [`scripts/binance_restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/scripts/binance_restricted_live_soak.py)
- [`app/monitoring/restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/app/monitoring/restricted_live_soak.py)

## Fail-Closed Behavior

Current fail-closed behaviors include:
- stale-output fail-if-exists for scheduler and action directories
- late-window abort behavior in the scheduler
- blocked-mutation stop thresholds in the soak runner
- no resumption of interrupted action windows
- no reconstruction of missing final artifacts

## Why Incomplete Runs Must Not Be Resumed

Interrupted or incomplete runs must not be resumed because:
- scheduler timing is anchored to the original `runtime_session.json.started_at`
- action run ids are fixed from the original runtime run id
- stale-output protection requires fresh lineage
- final runtime artifacts represent one completed soak result, not a merge of partial runs

Invalid operator behavior:
- reusing `binance-bounded-r5-8h` after interruption
- manually launching `a2` or `a3` after scheduler late-abort
- treating partial runtime artifacts as completed run evidence

Correct operator behavior:
- treat the interrupted run as failed
- retain artifacts for review
- start a new run with a fresh run id
