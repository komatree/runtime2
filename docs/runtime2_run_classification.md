# runtime2 Run Classification

## Purpose

This document defines the current evidence-based run classification rules for `runtime2`.

It covers:
- `PASS`
- `PASS WITH CAUTION`
- `FAIL`
- short environment-check interpretation

## Normal Bounded Run Evidence Set

Required runtime evidence:
- `runtime_session.json`
- `runtime_cycles.jsonl`
- `runtime_health.json`
- `runtime_status.md`
- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `listen_key_refresh.jsonl`
- `reconciliation_events.jsonl`
- `account_update_events.jsonl`
- `soak_summary.json`
- `soak_summary.md`

Required scheduler evidence:
- `scheduler_manifest.json`
- `scheduler_events.jsonl`

Required action-window evidence:
- `action_driver_result.json` for each planned window
- `action_driver_summary.md` for each planned window

## PASS

Classify a normal bounded run as `PASS` only if:
- `stop_reason == completed`
- `aborted == false`
- `blocked_mutation_count == 0`
- scheduler completed its intended window plan
- lineage is complete
- reconciliation converged without manual attention
- final runtime artifact set is complete
- caution, if present, is minor and does not materially define the run

## PASS WITH CAUTION

Classify a normal bounded run as `PASS WITH CAUTION` if:
- all core safety conditions passed
- but known caution classes remained meaningful

Known caution classes at the current stage:
- `PERCENT_PRICE_BY_SIDE` causing `PARTIAL_SUCCESS_NONBLOCKING`
- reconnect / heartbeat churn that remained non-destructive
- non-destructive summary/accounting inconsistency where retained event evidence still converges cleanly

## FAIL

Classify as `FAIL` if any of the following apply:
- runtime did not stop cleanly
- required final runtime artifacts are missing
- scheduler did not complete the intended bounded window plan
- lineage is incomplete
- reconciliation evidence is missing or shows manual attention
- blocked mutation is non-zero
- a new destructive failure class appears
- retained artifacts are materially incomplete for safe judgment

Interrupted or incomplete runs are not valid success evidence.

## Short Environment-Check Runs

Short env-check runs are not normal bounded validation runs.

Purpose:
- confirm short-run continuity
- confirm runtime finalization works normally
- detect obvious host/session interruption behavior

Examples:
- `binance-envcheck-r0-1h`

### ENV-CHECK PASS

Use `ENV-CHECK PASS` only if:
- runtime stayed alive for the intended short duration
- final runtime artifact set exists
- finalization completed normally
- no retained evidence suggests interruption during the short run
- scheduler incompleteness is structurally expected from the short duration

### ENV-CHECK PASS WITH CAUTION

Use `ENV-CHECK PASS WITH CAUTION` if:
- runtime continuity and finalization are acceptable
- but known caution classes remain present and meaningful

### ENV-CHECK FAIL

Use `ENV-CHECK FAIL` if:
- runtime continuity is suspect
- finalization failed
- retained artifacts suggest interruption even in the short run

## Valid vs Invalid Evidence Examples

Valid success evidence:
- full final runtime artifact set
- clean runtime summary
- clean scheduler lineage
- expected action-window result artifacts

Invalid interrupted evidence:
- missing `soak_summary.json`
- missing `soak_summary.md`
- `window_aborted_late`
- missing action artifacts for required planned windows
- runtime-only partial artifact retention after an interrupted session
