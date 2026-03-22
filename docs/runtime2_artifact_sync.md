# runtime2 Artifact Sync

## Purpose

This document defines exactly what artifacts should be collected on Operations PC and transferred back to Development PC after each run.

## Runtime Artifact Folder

Collect:
- [`reports/soak_sessions/<run_id>/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions)

Expected contents for a completed bounded run:
- `runtime_session.json`
- `runtime_cycles.jsonl`
- `runtime_cycle_summaries.jsonl`
- `runtime_health.json`
- `runtime_status.md`
- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `listen_key_refresh.jsonl`
- `reconciliation_events.jsonl`
- `account_update_events.jsonl`
- `soak_summary.json`
- `soak_summary.md`
- `latest_rehearsal_summary.md`
- `rehearsal_run_summaries.jsonl`

## Scheduler Artifact Folder

Collect:
- [`reports/event_exercises/<run_id>-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)

Expected contents:
- `scheduler_manifest.json`
- `scheduler_events.jsonl`

## Action Artifact Folders

Collect:
- [`reports/event_exercises/<run_id>-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)

Expected contents per completed action window:
- `action_driver_events.jsonl`
- `action_driver_result.json`
- `action_driver_summary.md`
- `scheduler_stdout.log`
- `scheduler_stderr.log`

## Naming Conventions

Runtime:
- `<run_id>`

Scheduler:
- `<run_id>-scheduler`

Actions:
- `<run_id>-a1`
- `<run_id>-a2`
- `<run_id>-a3`

Examples:
- `binance-bounded-r4-8h`
- `binance-bounded-r4-8h-scheduler`
- `binance-bounded-r4-8h-a1`

## What To Transfer Back To Development PC

Transfer:
- the runtime artifact folder
- the scheduler artifact folder
- all action-driver folders that were actually created

For interrupted runs:
- still transfer the incomplete artifact set
- do not try to “clean it up” first
- preserve the failure evidence exactly as retained

## What Not To Transfer

Do not transfer:
- shell history
- credential files
- `.venv/`
- local environment dumps
- raw tmux server data
- clipboard exports
- any file containing raw secrets

## Suggested Archive Commands

Archive one run from Operations PC:

```bash
RUN_ID="binance-bounded-r4-8h"
tar -czf "${RUN_ID}-artifacts.tgz" \
  "reports/soak_sessions/${RUN_ID}" \
  "reports/event_exercises/${RUN_ID}-scheduler" \
  "reports/event_exercises/${RUN_ID}-a1/action_driver" \
  "reports/event_exercises/${RUN_ID}-a2/action_driver" \
  "reports/event_exercises/${RUN_ID}-a3/action_driver"
```

Archive a short env-check run:

```bash
RUN_ID="binance-envcheck-r0-1h"
tar -czf "${RUN_ID}-artifacts.tgz" \
  "reports/soak_sessions/${RUN_ID}" \
  "reports/event_exercises/${RUN_ID}-scheduler" \
  "reports/event_exercises/${RUN_ID}-a1/action_driver"
```

## Invalid Artifact Bundles

Examples of invalid or incomplete transfer practice:
- transferring only screenshots instead of raw artifacts
- transferring only `soak_summary.json` without runtime and scheduler lineage files
- discarding incomplete interrupted-run artifacts
- renaming folders after the run
