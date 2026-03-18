# Cutover Checklist

Use this checklist before moving between `report_only`, `paper`, and any restricted-live rehearsal.

## Purpose

This is an operator-facing cutover list for rehearsal execution. It complements:

- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md)
- [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md)
- [`docs/binance_known_gaps.md`](/home/terratunes/code/trading/runtime2/docs/binance_known_gaps.md)

## Preflight

- config file present
- execution data path present
- context data path present
- report path writable
- log path writable
- expected exchange mode selected for the target runner
- rehearsal scripts invoked instead of ad hoc commands
- `--confirm-rehearsal-only` supplied for run commands
- config file matches the selected mode and data file names
- automated dry-run completed for the target mode when operator rehearsal is required
- dry-run used the authoritative Python launcher path rather than duplicated shell logic

## Launcher Verification

- operator used `scripts/runtime2_rehearsal.py` or the thin wrapper scripts only
- selected runner mode matches config mode exactly
- launcher completed without `launch_error`
- latest launcher summaries were generated in the expected output directory
- restricted-live rehearsal used the explicit safety flags and still kept order submission disabled

## Mode-Specific Cutover

### Report-Only

- use `exchange_mode=read_only`
- credentials may be absent, but warnings should be reviewed
- confirm structured rehearsal summary was appended
- confirm latest rehearsal markdown summary was generated
- confirm latest launch summaries were generated
- confirm dry-run run directory contains `runtime_cycles.jsonl` and `runtime_cycle_summaries.jsonl`
- confirm `reports/dry_runs/<run_id>/run_summary.md` and `run_summary.json` were generated
- confirm `latest_launch_summary.json` names `ReportOnlyRunner`

### Paper

- use `exchange_mode=paper`
- confirm prior report-only path is healthy
- confirm structured rehearsal summary was appended
- confirm latest rehearsal markdown summary was generated
- confirm latest launch summaries were generated
- confirm dry-run run directory contains `runtime_cycles.jsonl` and `runtime_cycle_summaries.jsonl`
- confirm paper dry-run generated `paper_state_transitions.jsonl`
- confirm final portfolio in the dry-run summary is explainable from simulated fills
- confirm `latest_launch_summary.json` names `PaperRunner`

### Restricted-Live Rehearsal

- use `exchange_mode=restricted_live_rehearsal`
- Binance credentials present
- `--confirm-rehearsal-only` supplied
- `--allow-restricted-live-rehearsal` supplied
- `--confirm-no-order-submission` supplied
- order submission remains disabled
- confirm latest launch summaries were generated
- confirm dry-run uses `--mode restricted_live` only when explicitly intended
- confirm `latest_launch_summary.json` names `RestrictedLiveRunner`
- Binance private stream, reconciliation, and clock sync blockers reviewed explicitly
- open gaps recorded before any go/no-go note

## Binance Verification

- credentials
  - verify Binance credentials are present only where required
  - verify credentials presence does not bypass restricted-live gates
- private stream health
  - verify lifecycle visibility for init, subscribe, reconnect, rollover, and termination
  - verify invalidation or termination would surface operator alerts
- reconciliation visibility
  - verify unknown execution and recovery outcomes are inspectable
  - verify unresolved recovery remains manual-attention visible
- degraded mode behavior
  - verify degraded states remain explicit in persisted artifacts
  - verify restricted-live still fails closed on defined quality blockers
- dry-run output review
  - verify `run_summary.json` and `run_summary.md` were generated
  - verify `latest_launch_summary.json` agrees with the requested mode
  - verify runtime artifacts exist inside the run directory before any operator sign-off

## Binance Promotion Status

- `report_only`: allowed
- `paper`: allowed
- restricted-live rehearsal: allowed only under current gates
- production promotion: blocked until Binance known gaps are closed

## Cutover Decision

- proceed
- hold
- rollback to `paper`
- rollback to `report_only`
