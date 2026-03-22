# runtime2 Dev/Ops Split Checklist

## Purpose

Use this checklist before running `runtime2` with a Development PC / Operations PC split.

This checklist is practical and operator-facing.
It does not change the current execution model.

Read together with:
- [`docs/runtime2_operator_stage_summary.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_stage_summary.md)
- [`docs/runtime2_execution_model.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_execution_model.md)
- [`docs/runtime2_run_classification.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_run_classification.md)
- [`docs/runtime2_dev_ops_split_plan.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_dev_ops_split_plan.md)
- [`docs/runtime2_artifact_sync.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_artifact_sync.md)
- [`docs/runtime2_operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operator_runbook.md)

## Development PC

- confirm Git working tree is clean enough for release preparation
- confirm current branch name
- confirm current commit hash
- confirm the approved run target and exact `run_id`
- confirm current bounded operator stage is documented
- confirm the intended classification standard is documented
- commit and push code and docs only
- do not commit:
  - `reports/`
  - `logs/`
  - `.venv/`
  - secrets

## Operations PC Setup

- install WSL
- install `git`
- install `tmux`
- install `python3`
- install Python venv support
- clone the repo from GitHub
- checkout the approved branch
- create a fresh `.venv`
- install repo dependencies into `.venv`
- confirm wrappers will use `.venv/bin/python`
- syntax-check the relevant scripts:

```bash
bash -n scripts/preflight_broader_rehearsal_wsl.sh \
  scripts/preflight_wsl.sh \
  scripts/run_broader_rehearsal_6h_wsl.sh \
  scripts/run_broader_rehearsal_smoke30_wsl.sh
```

## Credential Handling

- use hidden prompt entry only
- do not use inline credential-bearing commands
- duplicate prompt skip behavior should work when credentials are already present in the current shell
- do not share terminal capture during credential entry
- unset credentials after the run:
  - `unset BINANCE_API_KEY BINANCE_API_SECRET`

## Long-Run Host Discipline

- AC power connected
- sleep disabled
- hibernate disabled
- lid-close sleep disabled if applicable
- old `tmux` sessions cleared
- do not leave long runs on a host likely to suspend WSL or terminal sessions

## Run Execution

1. Source preflight.
2. Confirm the second source skips prompting when credentials are already present.
3. Run credential sanity check:

```bash
python scripts/check_binance_testnet_credentials.py
```

4. Run signed-path verification if that is part of the approved gate for the session:

```bash
python scripts/verify_binance_signed_paths_testnet.py
```

5. Launch the approved bounded wrapper or runtime/scheduler pair.
6. Run post-run verify/check helper.
7. Collect short operator notes.

## Artifacts To Sync Back

Sync back:
- [`reports/soak_sessions/<run_id>/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions)
- [`reports/event_exercises/<run_id>-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- [`reports/event_exercises/<run_id>-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises)
- verify/check output
- operator notes that do not contain secrets

## Do Not Sync

- `.venv/`
- secrets
- shell history
- `tmux` state
- machine-local temp data
- raw terminal captures containing credential entry
- `logs/` unless specifically requested for an investigation
