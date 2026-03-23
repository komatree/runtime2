# runtime2 Artifact Sync

## Purpose

This document defines exactly what artifacts should be collected on Operations PC and transferred back to Development PC after each run.

## Forward vs Backward Transfer

- Development PC to Operations PC:
  - code moves by Git
  - runtime data bundle moves by file transfer
  - credentials never move; inject them locally on Operations PC
- Operations PC to Development PC:
  - run artifacts move back as an artifact bundle after execution
- Keep the directions separate:
  - forward transfer is for runnable inputs
  - backward transfer is for retained outputs and review evidence

### Forward Transfer Inputs

- Code by Git:
  - approved branch
  - approved commit hash
- Runtime data bundle by file transfer:
  - required local files under `data/binance/`
  - current concrete minimum for the active testnet config:
    - `data/binance/btcusdt_4h.json`
    - `data/binance/btcusdt_1d.json`
- Credentials by local operator entry only:
  - hidden prompt flow
  - never Git
  - never tarball
  - never shell history

### Forward Transfer Example Commands

- Create a minimal data bundle on Development PC:

```bash
tar -czf runtime2-data-binance-minimal.tgz \
  data/binance/btcusdt_4h.json \
  data/binance/btcusdt_1d.json
```

- Copy the bundle to Operations PC:

```bash
scp runtime2-data-binance-minimal.tgz ops-pc:~/runtime2/
```

- Unpack it on Operations PC from repo root:

```bash
tar -xzf ~/runtime2/runtime2-data-binance-minimal.tgz
```

- Verify it before any run:

```bash
ls -l data/binance
test -f data/binance/btcusdt_4h.json
test -f data/binance/btcusdt_1d.json
```

### Backward Transfer Outputs

- Backward transfer is run-artifacts only.
- Do not routinely send `data/binance/` back as part of run review.
- Do not treat the runtime data bundle as a generated artifact.

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
- `data/binance/`
- forward-transfer tarballs used only to seed Operations PC

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
