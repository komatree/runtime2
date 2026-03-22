# runtime2 Development PC / Operations PC Split Plan

## Purpose

This document defines the current practical split between Development PC and Operations PC for `runtime2`.

It freezes the current collaboration model before further bounded operator work.

## Role Split

### Development PC

Use Development PC for:
- code changes
- tests
- repo analysis
- documentation
- run artifact review
- classification writeups
- git commits and tags

Development PC should not be the primary exchange-connected long-run host once the split is active.

### Operations PC

Use Operations PC for:
- exchange-connected runs
- bounded operator runs
- short env-check runs
- bounded retries
- future bounded micro-live execution
- credential entry
- artifact collection after runs

Operations PC should stay focused on stable runtime execution and clean artifact capture.

## What Moves By Git

Move by Git:
- code changes
- docs updates
- tests
- scripts
- config changes that are intentionally committed

Do not move by Git:
- `reports/`
- `logs/`
- local credentials
- ad hoc operator notes containing secrets
- retained run outputs created on Operations PC

## What Moves By Artifact Bundle

Move from Operations PC back to Development PC as artifact bundles:
- `reports/soak_sessions/<run_id>/`
- `reports/event_exercises/<run_id>-scheduler/`
- `reports/event_exercises/<run_id>-a1/action_driver/`
- `reports/event_exercises/<run_id>-a2/action_driver/`
- `reports/event_exercises/<run_id>-a3/action_driver/`

Optional if retained:
- wrapper watch outputs or local operator notes that do not contain secrets

## What Must Never Move

Must never move between PCs:
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- shell history containing credential material
- tmux pane dumps containing credential entry
- copied raw environment dumps

## Run / Review Feedback Loop

1. Development PC prepares the code/docs state and commits it.
2. Operations PC checks out that Git state.
3. Operations PC runs the bounded session with a fresh run id.
4. Operations PC collects the artifact bundle only.
5. Development PC reviews and classifies the run from retained artifacts.
6. Development PC updates docs and next-step guidance.
7. Operations PC executes the next approved bounded run only after review is complete.

## Host Power / Sleep Discipline

For runs longer than `4h`:
- use stable AC power
- disable sleep
- disable hibernate
- disable lid-close sleep behavior if applicable
- avoid unattended host policies that suspend WSL, tmux, or the terminal session

Operator meaning:
- interruption-class failures invalidate bounded evidence
- interrupted runs must be retained for review and then replaced with a fresh run id

## Credential Handling Rules

Use only the current supported credential path:
- hidden prompt entry
- current-shell export behavior

Rules:
- start from a fresh shell
- use:
  - [`scripts/preflight_broader_rehearsal_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_broader_rehearsal_wsl.sh)
  - or [`scripts/preflight_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_wsl.sh)
- do not paste credentials into inline shell commands
- do not record or share terminal capture during credential entry
- unset credentials after the run:
  - `unset BINANCE_API_KEY BINANCE_API_SECRET`

## Run-Id Discipline

Use a fresh run id for every new attempt.

Examples:
- `binance-bounded-r6-8h`
- `binance-envcheck-r1-1h`

Never reuse:
- interrupted run ids
- aborted run ids
- partially retained run ids

## Current Recommended Split State

Before the split:
- freeze docs and current run classification

After the split:
- Development PC owns repository state
- Operations PC owns exchange-connected execution
- classification authority stays with retained artifacts, not operator memory
