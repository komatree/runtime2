# runtime2 Gate Schema

## Purpose

This document defines the minimum useful bounded-stage evidence pack shape for `runtime2`.

This schema is now materialized by a small bounded-stage helper:
- [`scripts/build_runtime2_gate_artifacts.py`](/home/terratunes/code/trading/runtime2/scripts/build_runtime2_gate_artifacts.py)

## Current Stage Scope

Use this schema for:
- bounded operator runs
- short env-check runs when a compact review pack is still useful

Do not treat this as a production observability stack.

## Suggested Layout

For a reviewed run, keep a compact evidence pack under:

```text
reports/gates/<run_id>/
```

Suggested files:
- `gate_manifest.json`
- `gate_scorecard.md`
- `operator_decision.md`

Optional:
- `notes.md`

## gate_manifest.json

Suggested fields:

```json
{
  "run_id": "binance-bounded-r6-8h",
  "run_type": "bounded",
  "verdict": "PASS WITH CAUTION",
  "reviewed_at": "2026-03-27T00:00:00+09:00",
  "evidence": {
    "runtime": [
      "reports/soak_sessions/<run_id>/soak_summary.json",
      "reports/soak_sessions/<run_id>/finalization_debug.json",
      "reports/soak_sessions/<run_id>/reconciliation_events.jsonl",
      "reports/soak_sessions/<run_id>/reconnect_events.jsonl"
    ],
    "scheduler": [
      "reports/event_exercises/<run_id>-scheduler/scheduler_events.jsonl"
    ],
    "actions": [
      "reports/event_exercises/<run_id>-a1/action_driver/action_driver_result.json",
      "reports/event_exercises/<run_id>-a2/action_driver/action_driver_result.json",
      "reports/event_exercises/<run_id>-a3/action_driver/action_driver_result.json"
    ]
  },
  "known_cautions": [
    "PERCENT_PRICE_BY_SIDE",
    "reconnect_heartbeat_churn"
  ]
}
```

## gate_scorecard.md

Should summarize only the current bounded-stage decision points:
- clean stop or not
- finalization completed or not
- scheduler complete or not
- reconciliation converged or not
- blocked mutation count
- reconnect / heartbeat counts
- `PERCENT_PRICE_BY_SIDE` presence in action-driver results

## operator_decision.md

Should record:
- verdict
- key evidence
- caution or failure class
- next required action

## Current Rule

The evidence pack should reference the retained ground-truth artifacts.
It should not replace them or invent derived metrics beyond the current bounded-stage needs.

Current helper usage:

```bash
python scripts/build_runtime2_gate_artifacts.py <run_id>
```

Current helper behavior:
- reads only retained runtime, scheduler, and action artifacts already produced by the bounded run
- writes:
  - `reports/gates/<run_id>/gate_manifest.json`
  - `reports/gates/<run_id>/gate_scorecard.md`
  - `reports/gates/<run_id>/operator_decision.md`
- does not alter runtime, scheduler, or lineage behavior
