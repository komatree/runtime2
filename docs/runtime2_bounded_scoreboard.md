# runtime2 Bounded Scoreboard

## Purpose

This scoreboard defines the compact review view for the current `runtime2` bounded operator stage.

Use it after each bounded run.
Use [`docs/runtime2_run_classification.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_run_classification.md) as the authoritative verdict rule.

## Core Scoreboard

| Area | Check | Source | Pass shape |
| --- | --- | --- | --- |
| Runtime stop | `stop_reason`, `aborted` | `soak_summary.json` | `completed`, `false` |
| Finalization | `phase`, `status` | `finalization_debug.json` | `artifact_writer.persist`, `completed` |
| Scheduler continuity | final scheduler event | `scheduler_events.jsonl` | `scheduler_complete` |
| Action continuity | `a1/a2/a3` results present | `action_driver_result.json` | all planned windows present |
| Reconciliation | `manual_attention` | `reconciliation_events.jsonl` | no manual attention |
| Mutation safety | `blocked_mutation_count` | `soak_summary.json` | `0` |

## Current Caution Scoreboard

| Caution | Current meaning | Current evidence source |
| --- | --- | --- |
| `PERCENT_PRICE_BY_SIDE` | known action-window caution; can still produce `PARTIAL_SUCCESS_NONBLOCKING` | `action_driver_result.json` |
| reconnect / heartbeat churn | known bounded-stage caution if non-destructive | `soak_summary.json`, `reconnect_events.jsonl` |

## Current Baseline Reference

Reference bounded run:
- `binance-bounded-r6-8h`

Key retained evidence:
- clean stop and finalization completed:
  - [`reports/soak_sessions/binance-bounded-r6-8h/soak_summary.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r6-8h/soak_summary.json)
  - [`reports/soak_sessions/binance-bounded-r6-8h/finalization_debug.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-bounded-r6-8h/finalization_debug.json)
- scheduler complete:
  - [`reports/event_exercises/binance-bounded-r6-8h-scheduler/scheduler_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-bounded-r6-8h-scheduler/scheduler_events.jsonl)
- known cautions:
  - `reconnect_count = 234`
  - `heartbeat_overdue_events = 233`
  - `a1/a2/a3` all show `PERCENT_PRICE_BY_SIDE` on the resting create leg while still ending `PARTIAL_SUCCESS_NONBLOCKING`

## Review Notes

- High reconnect count by itself is not an automatic fail in the current bounded stage.
- `PERCENT_PRICE_BY_SIDE` by itself is not an automatic fail in the current bounded stage.
- Missing final runtime artifacts, failed finalization, manual attention, or incomplete scheduler lineage remain fail conditions.
