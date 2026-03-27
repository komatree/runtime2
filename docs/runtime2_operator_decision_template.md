# runtime2 Operator Decision Template

## Purpose

Use this template when writing the bounded-stage Go/No-Go note for one run.

Keep it short.
Use retained artifacts only.

## Template

```md
# runtime2 Operator Decision

- run_id:
- run_type:
- verdict: PASS / PASS WITH CAUTION / FAIL

## Core Evidence

- soak summary:
- finalization:
- scheduler continuity:
- reconciliation:
- blocked mutation count:

## Known Cautions

- PERCENT_PRICE_BY_SIDE:
- reconnect / heartbeat churn:

## Failure Class

- none / interruption / finalization / reconciliation / scheduler / other

## Decision

- proceed:
- do not proceed:

## Required Next Action

- next step:
```

## Current Bounded-Stage Rule

For the current stage:
- `PASS` requires clean stop, finalization complete, scheduler complete, and no destructive failure
- `PASS WITH CAUTION` allows known caution classes only
- `FAIL` applies to missing final artifacts, failed finalization, incomplete lineage, manual attention, blocked mutation, or scheduler/runtime failure

See:
- [`docs/runtime2_run_classification.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_run_classification.md)
- [`docs/runtime2_bounded_scoreboard.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_bounded_scoreboard.md)
