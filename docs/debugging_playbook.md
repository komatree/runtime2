# Debugging Playbook

## Where To Look First On Failures

1. Confirm the failing layer first:
   - contracts
   - features
   - strategies
   - runtime
   - exchange adapter
2. Check the nearest canonical contract involved in the failure.
3. Verify whether the failure happened before or after closed-bar validation.
4. Inspect the last persisted `RuntimeCycleResult` and related report artifacts.
5. For report-only failures, inspect the latest JSONL record before changing strategy or exchange code.
6. Confirm the persisted schema version matches the expected reader or test.
7. Inspect the latest runtime health snapshot before drilling into exchange-specific logs.

## Quick Triage

- inspect first
  - latest `runtime_health.json`
  - latest `runtime_status.md`
  - latest unified exchange health section in those artifacts
  - latest cycle JSONL record
  - latest reconciliation log if exchange state is involved
- logs and reports live in
  - configured report output path
  - `reports/rehearsal_run_summaries.jsonl`
  - `reports/dry_runs/<run_id>/`
  - paper transition and session summary JSONL outputs
- restart when
  - the fault is transient and persisted artifacts remain internally consistent
  - optional-source degradation is expected for the active mode
- halt when
  - private stream truth is missing in restricted-live rehearsal
  - reconciliation is unresolved
  - clock sync is uncertain in restricted-live
  - runtime artifacts needed for diagnosis are missing

## Contract Mismatch Checklist

- Are timestamps UTC-aware everywhere?
- Does `instrument_id` match across `Instrument`, `Candle`, `BarSlice`, `FeatureSnapshot`, and `DecisionContext`?
- Does timeframe match across candle, bar slice, and feature snapshot?
- Are Decimal-valued fields staying Decimal rather than float?
- Did a venue-specific field leak into a strategy-facing contract?
- Did an incomplete feature bundle get treated as mandatory when it should be optional?

## Runtime Step Failure Checklist

- Closed bar trigger
  - latest candle marked closed
  - `BarSlice.end_time` matches latest candle close
  - no overlapping candle windows
  - `incomplete_bar` quality state absent on valid cycles
- Feature build
  - candle features present
  - real-data 4h execution and 1d context candles are both closed when required
  - Index Suite lookup status is `ok` when index context is expected
  - stale or version-mismatched Index Suite snapshots are visible in persisted diagnostics
  - stablecoin source freshness is valid when stablecoin observability is expected
  - stablecoin source type and snapshot version match the configured collector/read path
  - optional index/stablecoin snapshots handled correctly when absent
  - `FeatureSnapshot` completeness matches expectations
  - quality states explain degraded inputs explicitly:
    - `missing_data`
    - `stale_data`
    - `version_mismatch`
    - `time_sync_uncertain`
- Strategy evaluation
  - strategy consumed only `DecisionContext`
  - output is canonical `SignalDecision`
  - no external I/O inside strategy logic
- Risk evaluation
  - decision reasons populated
  - venue profile only used at the risk/execution boundary
- Persistence/reporting
  - `RuntimeCycleResult` written
  - JSONL report contains schema version, instrument, timeframe, bar close time, feature summary, signals, risk decisions, execution intents, and cycle result
  - optional Index Suite and stablecoin sections appear as explicit `null` fields when absent
  - alerts recorded on failed or degraded cycles
- Exchange stub path
  - order submission still disabled unless explicitly implemented
  - reconciliation gaps surfaced as alerts

## Logging And Report Artifacts To Inspect

- persisted `RuntimeCycleResult`
- persisted `DecisionContext`
- persisted `FeatureSnapshot`
- JSONL report records under the configured report-only output path
- append-only runtime cycle summaries
- latest runtime health/status snapshot
- operator markdown runtime report
- `feature_snapshot_summary`
- `decision_context_summary`
- `index_suite_context`
- real-data context feature keys such as `context.1d.close`
- stablecoin JSONL/CSV/markdown observability outputs
- strategy `SignalDecision` outputs
- risk `RiskDecision` outputs
- generated but non-submitted `ExecutionIntent` outputs
- shared order lifecycle transitions
- adapter clock-sync status
- reconciliation summaries and unknown execution alerts
- parity comparison JSONL artifacts for replay/backtest drift
- dry-run per-session artifacts under `reports/dry_runs/<run_id>/`
- dry-run `run_summary.json` and `run_summary.md`
- dry-run `input_manifest.json` to confirm the launcher used the intended config and data files
- dry-run `latest_launch_summary.json` to confirm the selected runner actually executed

## Parity Drift Checks

- compare `signal_sides` between runtime and reference outputs
- compare `actionable` state before debugging exchange behavior
- compare `risk_posture` before changing execution code
- compare `execution_intent_shape` only after confirming feature and strategy parity
- confirm `has_index_snapshot` and `has_stablecoin_snapshot` match the replay input assumptions
- treat parity mismatches as release-gating diagnostics until explained

## Runtime Health Checks

- `last_closed_bar_processed_at` should advance with each accepted bar
- `last_successful_feature_snapshot_at` should match the latest successful cycle
- `last_strategy_evaluation_at` should lag the bar close by only the expected processing window
- `last_persistence_success_at` should update on every persisted cycle
- degraded flags should be explicit and explainable, even when the cycle itself succeeds
- `exchange_health.overall_state` should distinguish `healthy`, `degraded`, `fatal`, and `unknown`
- `exchange_health.private_stream`, `exchange_health.reconciliation`, `exchange_health.clock_sync`, and `exchange_health.status_query` should agree with the latest adapter artifacts
- for Binance-facing runs, `runtime_health.json` and `runtime_status.md` should always include the exchange-health section even when the provider is absent
- if the provider is absent, the exchange-health section should show explicit `unknown` component states rather than disappearing

## Incident-Specific Checks

### Stale Data

- inspect
  - `quality_states`
  - latest accepted bar close time
  - last successful feature snapshot time
- degraded vs fatal
  - degraded in `report_only` and `paper`
  - fatal in `restricted_live`
- next action
  - restore fresh inputs first
  - do not debug strategy logic before freshness is restored

### Missing Index Suite Snapshot

- inspect
  - `index_suite_context`
  - requested version vs resolved version
  - degradation flags
- degraded vs fatal
  - degraded in `report_only` and `paper`
  - not automatically fatal in current phase-1 policy
- next action
  - confirm repository freshness and version request alignment

### Missing Stablecoin Snapshot

- inspect
  - stablecoin observability outputs
  - `stablecoin_snapshot_status`
  - snapshot freshness metadata
- degraded vs fatal
  - degraded in `report_only` and `paper`
  - non-fatal in current phase-1 policy
- next action
  - restore descriptive snapshot flow before blaming downstream logic

### Binance Private Stream Interruption

- inspect
  - lifecycle state
  - termination or invalidation alerts
  - reconnect count
  - session rollover alerts
  - whether the latest soak cycle ended with no private payload because the bounded read timed out cleanly
  - whether `has_gap` or persisted `gap_active` triggered automatic REST recovery
  - whether the private session failed during deprecated REST `listenKey` bootstrap or during the current WS-API authenticated subscription flow
- degraded vs fatal
  - not fatal for pure report-only and paper paths
  - fatal for restricted-live rehearsal continuation
- next action
  - reinitialize authenticated stream
  - if bootstrap failed with HTTP `410 Gone`, treat that as a deprecated listenKey-path failure and confirm the runtime is using the migrated `userDataStream.subscribe.signature` bootstrap path
  - if a soak overran its configured duration, confirm the current code is not stuck on an old unbounded private read and inspect whether the latest cycle returned a no-payload timeout instead
  - verify automatic signed status-query recovery was triggered or manual attention was raised explicitly
  - keep portfolio mutation blocked until stream truth is restored

### Reconciliation Unresolved State

- inspect
  - append-only reconciliation logs
  - latest reconciliation state snapshot
  - `unknown_execution_ids`
  - recovery action list
  - current reconciliation state
  - persisted unresolved order ids and manual-attention order ids
  - `workflow.recovery_trigger_reason`
  - `workflow.recovery_automatic`
  - `workflow.gap_detected`
  - `workflow.resumed_from_snapshot`
  - `workflow.convergence_state`
  - latest attempt sequence in recovery summaries
  - snapshot `last_recovery_trigger_reason`
  - snapshot `last_recovery_automatic`
  - snapshot `last_convergence_state`
  - snapshot `last_manual_attention_at`
- degraded vs fatal
  - operator-attention state everywhere
  - fatal for restricted-live continuation
- next action
  - reload unresolved reconciliation state before restarting recovery
  - confirm whether recovery was triggered by a private-stream gap, restart resume, unknown execution, or missing private updates
  - confirm whether automatic recovery exhausted its allowed rounds before escalating
  - stop before portfolio mutation if recovery is unresolved

### Restricted-Live Restart Or Crash-Recovery

- inspect
  - `restricted_live_scenarios/<scenario_name>/scenario_summary.json`
  - `restricted_live_scenarios/<scenario_name>/scenario_summary.md`
  - `restricted_live_scenarios/<scenario_name>/reconciliation_state.json` when present
  - `restart_count`
  - `interruption_reason`
  - `restored_unresolved_order_ids`
  - `restored_gap_active`
- degraded vs fatal
  - blocked mutation is a valid safety success path when the scenario expected fail-closed behavior
  - unresolved restored state is fatal for restricted-live continuation until explained
- next action
  - confirm restart artifacts explain why mutation remained blocked or resumed safely
  - preserve the reconciliation state snapshot before retrying the rehearsal
  - do not override blocked mutation just to restore liveness

### Clock Sync Uncertainty

- inspect
  - `offset_ms`
  - `round_trip_ms`
  - `time_sync_uncertain`
- degraded vs fatal
  - degraded in `report_only` and `paper`
  - fatal in `restricted_live`
- next action
  - resample clock state before blaming auth or exchange order flow

## Recovery By Mode

- `report_only`
  - prefer preserving artifacts and rerunning after input recovery
  - no exchange side effect should be assumed
- `paper`
  - preserve portfolio continuity and compare prior ending state before rerun
  - simulated fills remain reproducible and should explain state transitions
- `restricted_live`
  - fail closed on blockers
  - do not restart until private stream, reconciliation, and clock state are explainable
  - after restart, confirm restored unresolved ids and gap state are visible in scenario artifacts before trusting resumed mutation

## Private Bootstrap Note

- old restricted-live bootstrap failures with HTTP `410 Gone` were caused by REST listenKey acquisition against a deprecated Binance Spot user-data bootstrap path
- current runtime2 private bootstrap should use the Spot WebSocket API and `userDataStream.subscribe.signature`
- if a new bootstrap failure appears, inspect whether it is:
  - WS-API authentication/signature failure
  - endpoint-profile mismatch
  - request-weight blocking
  - websocket connection failure before subscribe acknowledgement

## Dry-Run Workflow Checks

- If the dry-run exits with code `1`, inspect preflight failures first.
- If the dry-run exits with code `2`, inspect `run_summary.json`, `latest_launch_summary.json`, and `runtime_status.md` in the run directory.
- Confirm the run directory name matches the operator-intended mode and session.
- Confirm the run directory contains both launcher artifacts and dry-run summary artifacts:
  - `rehearsal_run_summaries.jsonl`
  - `latest_rehearsal_summary.md`
  - `latest_launch_summary.json`
  - `latest_launch_summary.md`
  - `runtime_cycles.jsonl`
  - `runtime_cycle_summaries.jsonl`
- In paper mode, confirm final portfolio state matches `paper_state_transitions.jsonl`.

## Exchange Failure Entrypoints

- Binance private stream
  - inspect private-stream batch alerts
  - check whether a sequence gap was flagged
  - confirm client id / exchange id fields are present in normalized events
  - confirm the private-payload translator is producing `translated` rather than `malformed` results
  - inspect private transport soak artifacts when reconnect or heartbeat durability is in question:
    - `health_transitions.jsonl`
    - `soak_summary.json`
    - `soak_summary.md`
  - inspect restricted-live soak artifacts when the full rehearsal path is under review:
    - `reports/restricted_live_soaks/<run_id>/health_transitions.jsonl`
    - `reports/restricted_live_soaks/<run_id>/reconnect_events.jsonl`
    - `reports/restricted_live_soaks/<run_id>/listen_key_refresh.jsonl`
    - `reports/restricted_live_soaks/<run_id>/reconciliation_events.jsonl`
    - `reports/restricted_live_soaks/<run_id>/soak_summary.json`
    - `reports/restricted_live_soaks/<run_id>/soak_summary.md`
    - `reports/soak_sessions/<session_id>/...` for 6h/12h/24h campaign sessions
  - confirm reconnect count, refresh failures, and authoritative/degraded transitions match the expected failure-injection plan
  - preserve malformed payloads inside the adapter boundary for diagnosis instead of forwarding them downstream
- Binance clock sync
  - inspect `offset_ms`, `round_trip_ms`, `server_time_ms`, and `local_time_ms`
  - inspect `recalibration_attempts`, `is_uncertain`, and `alert`
  - compare offset against configured tolerance before assuming auth or network faults
  - if recalibration was attempted, confirm whether the final state converged or remained uncertain
- Binance reconciliation
  - inspect `missing_order_ids`
  - inspect `unknown_execution_ids`
  - inspect `recovery_actions`
  - inspect `recovery_summaries` for attempt count and convergence state
  - inspect reconciliation state transitions: `submit_sent`, `unknown_execution`, `status_query_pending`, `recovered_terminal_state`, `unreconciled_manual_attention`
  - inspect append-only reconciliation logs for recovery attempts and terminal vs unresolved outcomes
  - inspect the latest reconciliation state snapshot for `private_stream_cursor`, `gap_active`, `unresolved_order_ids`, and `manual_attention_order_ids`
  - if the same lookup result reappears after restart, confirm replay-safe attempt numbering did not increment unexpectedly
  - inspect generated recovery lookup requests before mutating portfolio state
- Unified exchange health surface
  - inspect `runtime_health.json.exchange_health.overall_state`
  - confirm degraded vs fatal matches the latest private-stream, reconciliation, clock-sync, and status-query component state
  - if component state and rollup disagree, treat that as an observability regression
- Order lifecycle drift
  - confirm whether the order is correctly in `new`, `acknowledged`, `partially_filled`, `filled`, `canceled`, `expired`, `rejected`, `recovering`, or `unreconciled`
  - do not collapse `partially_filled` into `filled`
  - confirm fill quantities and average fill price match the latest lifecycle state
- Live portfolio translation
  - confirm duplicate `fill_id` values were either identical or explicitly blocked
  - confirm translated fill quantity does not exceed `order_state.filled_quantity`
  - confirm account-sync code is consuming canonical `AccountSnapshot` values rather than raw Binance payloads
  - confirm restricted-live mutation used the mandatory safeguard gate rather than direct portfolio mutation
  - if account snapshot mismatches projected cash, stop before portfolio mutation
  - if order state is `recovering` or `unreconciled`, require manual attention instead of applying fills
  - if the cycle alert says mutation was blocked by the safeguard gate, treat the cycle as failed closed until explained
  - if the private stream was invalidated by `listenKeyExpired` or equivalent termination, require later canonical private confirmation before mutation even when REST recovery reports a terminal status
- Restricted-live rehearsal scenarios
  - inspect `scenario_summary.json` and `scenario_summary.md` for the generated rehearsal scenario
  - confirm `scenario_passed` reflects the expected outcome, not only `cycle_success`
  - treat blocked mutation as a valid scenario pass only when the expected outcome was blocked mutation
  - if a safe-mutation scenario blocks, or a blocked-mutation scenario applies, treat that as a regression
- Restricted-live failure injection campaign
  - inspect `reports/failure_injection/<scenario_id>/scenario_summary.json`
  - inspect `reports/failure_injection/<scenario_id>/scenario_summary.md`
  - inspect `reports/failure_injection/<scenario_id>/scenario_cycles.jsonl`
  - confirm `recovery_trigger_reasons`, `final_convergence_state`, and `exchange_health_states` match the injected failure
  - confirm reconnect storms stay operator-visible even when mutation is not attempted
  - confirm duplicated fills show ignored fill ids instead of double-applied mutation
  - confirm `listen_key_expiration` blocks mutation until later canonical private confirmation instead of allowing expiry-driven REST recovery to mutate portfolio state
- Reconciliation disruption scenarios
  - inspect `reports/reconciliation_disruption/<scenario_id>/scenario_summary.json`
  - inspect `reports/reconciliation_disruption/<scenario_id>/scenario_summary.md`
  - inspect `reports/reconciliation_disruption/<scenario_id>/workflow_records.jsonl`
  - inspect `reports/reconciliation_disruption/<scenario_id>/reconciliation_workflows.jsonl`
  - inspect `reports/reconciliation_disruption/<scenario_id>/reconciliation_state.json`
  - confirm every recovery attempt in the markdown summary is backed by persisted workflow and state artifacts
  - confirm delayed status-query scenarios retain unresolved ids until convergence or escalation
- Restricted-live soak workflow
  - inspect `health_transitions.jsonl` first if the soak aborted
  - inspect `reconnect_events.jsonl`, `listen_key_refresh.jsonl`, and `reconciliation_events.jsonl` when root cause is not obvious from the rollup
  - inspect `soak_summary.json` for:
    - `stop_reason`
    - `blocked_mutation_count`
    - `reconnect_count`
    - `refresh_attempts`
    - `refresh_failures`
    - `heartbeat_overdue_events`
    - `reconciliation_recovery_attempts`
    - `reconciliation_recovery_success_rate`
  - halt the soak if `stop_reason` is `fatal_exchange_health` or `manual_attention`
  - treat `max_blocked_mutations` as a deliberate safety abort, not a liveness defect
  - do not restart the soak until the latest `runtime_health.json` and `reconciliation_state.json` explain the abort
- Binance order lookup recovery
  - confirm whether lookup attempted by `client_order_id`, `exchange_order_id`, or open-orders fallback
  - treat placeholder lookup alerts as transport-not-implemented, not successful recovery
  - if recovery remains unresolved, stop before portfolio mutation and escalate manual attention

## Report Schema Checklist

- `schema_version` present and expected
- `instrument_id`, `timeframe`, and `bar_close_time` match the triggering bar
- `feature_snapshot_summary.feature_names` matches the intended feature producer set
- `index_features` and `stablecoin_features` are explicit even when `null`
- `index_suite_context.status` matches the actual lookup outcome
- `index_suite_context.requested_index_version` matches the configured provider version
- `signal_decisions`, `risk_decisions`, and `execution_intents` are all present as arrays
- `runtime_cycle_result` matches the cycle summary returned by the runner

## Quality Gate Checks

- If `missing_data` is present, confirm which upstream input was absent and whether the current mode allows degradation.
- If `stale_data` is present, compare snapshot/bar timestamps against the cycle decision time.
- If `version_mismatch` is present, compare requested Index Suite version against the resolved snapshot version.
- If `time_sync_uncertain` is present, inspect runtime clock status before blaming strategy or risk output.
- In `restricted_live`, any of these states should stop the cycle before intent preparation proceeds.

## Postmortem Note Template

```text
Incident:
Date:
Mode:
Operator:

What Failed First:
- 

Initial Evidence:
- 

Degraded Or Fatal Classification:
- 

Restarted Or Halted:
- 

Root Cause Hypothesis:
- 

Next Preventive Action:
- 
```
