# Operator Runbook

## Startup Checklist

1. Validate configuration values and secrets availability.
2. Confirm exchange connectivity and system clock health.
3. Verify datafeed freshness and candle close alignment.
4. Confirm portfolio snapshot load succeeded.
5. Start runtime in `report_only` mode first and inspect persisted reports before enabling `paper`.
6. Use `paper` mode before any future live-enablement workflow.
7. Do not begin `restricted_live` testing until [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md) has been reviewed against current code and test status.

## Quick Triage

- inspect first
  - latest `runtime_status.md`
  - latest `runtime_health.json`
  - latest unified exchange health section inside `runtime_health.json`
  - latest cycle JSONL record
  - latest dry-run or rehearsal summary when applicable
- artifact locations
  - configured report JSONL output path
  - `reports/rehearsal_run_summaries.jsonl`
  - `reports/dry_runs/<run_id>/`
  - paper state transition JSONL when in paper mode
- restart when
  - the issue is transient and state is still explainable from persisted artifacts
  - private/public stream interruption recovered cleanly and health artifacts are current again
  - degraded optional inputs are understood and allowed for the current mode
- halt when
  - restricted-live quality gates fail closed
  - reconciliation remains unresolved
  - private stream truth is unavailable in any live-facing rehearsal
  - persisted artifacts are missing or contradictory

## Rehearsal Entrypoints

Use the rehearsal package rather than ad hoc commands:

```bash
bash scripts/preflight_runtime2.sh --mode report_only --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode read_only
bash scripts/run_report_only.sh --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode read_only --confirm-rehearsal-only
bash scripts/run_paper.sh --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode paper --confirm-rehearsal-only
bash scripts/run_restricted_live.sh --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode restricted_live_rehearsal --confirm-rehearsal-only --allow-restricted-live-rehearsal --confirm-no-order-submission
```

The rehearsal scripts are thin wrappers over the single Python launcher. They now:

1. run preflight validation
2. load explicit rehearsal config
3. construct the runtime context for the selected mode
4. invoke the selected runner
5. write operator-facing summaries

They still do not enable unrestricted exchange order submission.

Script role split:

- [`scripts/run_paper.sh`](/home/terratunes/code/trading/runtime2/scripts/run_paper.sh) is a launcher wrapper only. It starts the `paper` rehearsal path by delegating to [`scripts/runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py).
- [`scripts/check_soak_result.sh`](/home/terratunes/code/trading/runtime2/scripts/check_soak_result.sh) is a post-run review helper only. It does not launch runtime2; it inspects a completed soak session under `reports/soak_sessions/<run_id>/`.

Example post-run review:

```bash
bash scripts/check_soak_result.sh binance-testnet-soak-validation-1h
```

## Automated Dry-Run Session

Use the automated dry-run workflow when you want one operator-readable rehearsal session with run-specific artifacts:

```bash
python scripts/dry_run_runtime2.py --mode report_only --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode read_only --confirm-rehearsal-only
python scripts/dry_run_runtime2.py --mode paper --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode paper --confirm-rehearsal-only
python scripts/dry_run_runtime2.py --mode restricted_live --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode restricted_live_rehearsal --confirm-rehearsal-only --allow-restricted-live-rehearsal --confirm-no-order-submission
```

The dry-run workflow performs:

1. preflight validation
2. run-specific directory creation
3. authoritative launcher invocation
4. cycle-level persistence from the selected runner
5. final markdown and JSON summary generation

The dry-run workflow does not build its own runtime path. It validates settings, then calls the same config-driven launcher path used by the rehearsal scripts.

Each run writes a dedicated directory under `reports/dry_runs/<run_id>/`, with a matching logs directory under `logs/dry_runs/<run_id>/`.

## Binance Private Transport Soak Rehearsal

Use the deterministic soak runner when you need long-running reconnect, refresh, expiry, and heartbeat failure evidence without enabling unrestricted trading:

```bash
python scripts/binance_private_transport_soak.py --plan path/to/binance_private_transport_soak_plan.json --output-dir reports/binance_private_transport_soak/latest
```

The soak runner is rehearsal-grade. It replays an explicit plan through the private-stream lifecycle and writes:

- `health_transitions.jsonl`
- `soak_summary.json`
- `soak_summary.md`

Inspect for:

- reconnect count
- refresh attempts and refresh failures
- authoritative to degraded transitions
- termination count
- explicit heartbeat-overdue and listen-key-expiry alerts

## Restricted-Live Binance Soak Rehearsal

Use the restricted-live soak when you need rehearsal-grade durability evidence on top of the actual restricted-live runner path and real Binance transport:

```bash
python scripts/binance_restricted_live_soak.py --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode restricted_live_rehearsal --run-id soak-001 --cycles 20 --confirm-rehearsal-only --allow-restricted-live-rehearsal --confirm-no-order-submission
```

This path is still rehearsal-only. It reuses the restricted-live runner path and writes a run-specific directory under `reports/restricted_live_soaks/<run_id>/`.

For the current Binance Spot testnet validation workflow, use the dedicated testnet config rather than the mainnet-oriented rehearsal config:

```bash
python scripts/binance_restricted_live_soak.py \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --run-id binance-testnet-soak-validation-1h \
  --duration-hours 1 \
  --cycles 20 \
  --poll-interval-seconds 30 \
  --output-subdir soak_sessions \
  --max-blocked-mutations 3 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

That command expects Binance Spot testnet credentials in `BINANCE_API_KEY` and `BINANCE_API_SECRET`.

Current stage note:

- the broader `restricted_live_rehearsal` stage is now closed on the authoritative `r5` evidence set
- `r5` is the baseline for multi-window restricted-live session lineage and continuity
- the next live-facing step is not another broader-stage proof; it is a bounded operator / bounded micro-live stage using the same fresh run-id and scheduler-lineage rules
- do not bypass `runtime_session.json`, `scheduler_manifest.json`, or stale-output fail-if-exists protections in that next stage

Inspect:

- `health_transitions.jsonl`
- `soak_summary.json`
- `soak_summary.md`
- `runtime_cycles.jsonl`
- `runtime_cycle_summaries.jsonl`
- `runtime_health.json`
- `runtime_status.md`
- `reconciliation_state.json` when present

Track:

- exchange-health transitions
- reconnect count
- listen-key refresh attempts and failures
- heartbeat-overdue events
- reconciliation recovery attempts
- blocked mutation events

Duration enforcement notes:

- `--duration-hours` is enforced against bounded soak cycles, not only at process start.
- private-stream reads now time out into a no-payload cycle instead of blocking the soak indefinitely waiting for the next private event.
- if a cycle overruns the remaining duration, the soak should stop after that cycle and should not start another one.

Stop or abort the soak when:

- exchange health becomes `fatal`
- reconciliation requires manual attention
- blocked mutation events reach the configured threshold
- listen-key expiry or reconnect churn becomes unexplained

## Restricted-Live Soak Campaign

Use the soak campaign when you need staged evidence collection across the default long-running durations:

```bash
python scripts/binance_restricted_live_soak_campaign.py --config ... --execution-data ... --context-data ... --reports-dir ... --logs-dir ... --exchange-mode restricted_live_rehearsal --campaign-id campaign-001 --confirm-rehearsal-only --allow-restricted-live-rehearsal --confirm-no-order-submission
```

Exact examples:

```bash
python scripts/binance_restricted_live_soak_campaign.py \
  --config configs/runtime2_restricted_live.toml \
  --execution-data data/binance/btcusdt_4h.json \
  --context-data data/binance/btcusdt_1d.json \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --campaign-id binance-soak-20260314 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

If you need to run one duration only, use the single-session runner:

```bash
python scripts/binance_restricted_live_soak.py \
  --config configs/runtime2_restricted_live.toml \
  --execution-data data/binance/btcusdt_4h.json \
  --context-data data/binance/btcusdt_1d.json \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --run-id binance-soak-20260314-6h \
  --duration-hours 6 \
  --cycles 1000000 \
  --poll-interval-seconds 30 \
  --output-subdir soak_sessions \
  --max-blocked-mutations 3 \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

For the first real `6h` evidence run, always set `--output-subdir soak_sessions` on the single-session runner. The default single-session output path is `reports/restricted_live_soaks/<run_id>/`, but the long-running evidence review path expects `reports/soak_sessions/<session_id>/`.

The campaign runs the default session set:

- `6h`
- `12h`
- `24h`

Campaign artifacts are written under:

- `reports/soak_sessions/<session_id>/`
- `logs/soak_sessions/<session_id>/`

Each session now persists:

- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `listen_key_refresh.jsonl`
- `reconciliation_events.jsonl`
- `soak_summary.json`
- `soak_summary.md`
- `rehearsal_run_summaries.jsonl`
- `latest_rehearsal_summary.md`

Use the campaign when the goal is durability evidence collection rather than a short rehearsal check.

Minimum execution checks before starting:

1. Confirm `BINANCE_API_KEY` and `BINANCE_API_SECRET` are set in the current shell.
2. Confirm the selected config is `restricted_live` and still has order submission disabled.
3. Confirm `reports/` and `logs/` are writable.
4. Confirm the input execution/context files are the intended rehearsal inputs.
5. Confirm the operator understands that any non-zero exit code is a failed rehearsal session.

Minimum success thresholds for each session:

- hard pass requirements
  - process exit code is `0`
  - `soak_summary.json.stop_reason == "completed"`
  - `soak_summary.json.aborted == false`
  - all expected artifact files exist
  - no manual-attention escalation occurred
  - no fatal exchange-health stop occurred
  - `listen_key_refresh.jsonl` shows no refresh failure result
  - if `reconciliation_recovery_attempts > 0`, then `reconciliation_recovery_success_rate == 1.0`
- review-required, not automatic fail by itself
  - reconnects occurred
  - heartbeat overdue events occurred
  - exchange health became degraded and later recovered
  - blocked mutation count is non-zero but each case is explainable and remains fail-closed

Automatic failure thresholds for each session:

- non-zero process exit code
- `stop_reason` is `fatal_exchange_health`
- `stop_reason` is `manual_attention`
- `stop_reason` is `max_blocked_mutations`
- missing any expected artifact file
- any unexplained blocked mutation
- any refresh failure
- any reconciliation recovery attempt that does not converge or explicitly fail closed

Execution checklist:

### 6h Run

1. Run the single-session soak with `--duration-hours 6 --output-subdir soak_sessions` or review `reports/soak_sessions/<campaign_id>-6h/`.
2. Confirm all artifact files exist.
3. Confirm `stop_reason == "completed"`.
4. Confirm reconnect, heartbeat, and blocked-mutation counts are explainable.
5. Confirm any reconciliation recovery attempts converged with persisted evidence.

### 12h Run

1. Run the single-session soak with `--duration-hours 12` or review `reports/soak_sessions/<campaign_id>-12h/`.
2. Re-check all 6h success thresholds.
3. Confirm no refresh failures accumulated over the longer window.
4. Confirm exchange-health transitions remain explainable across the whole session.
5. Confirm no unresolved reconciliation state remained in `reconciliation_events.jsonl`.

### 24h Run

1. Run the single-session soak with `--duration-hours 24` or review `reports/soak_sessions/<campaign_id>-24h/`.
2. Re-check all 12h success thresholds.
3. Confirm there was no fatal/manual-attention abort and no unexplained degraded plateau.
4. Confirm blocked mutation remained fail-closed and operator-visible when it occurred.
5. Preserve the full artifact directory for cutover review before any next-stage discussion.

## Live Monitoring

- Watch for stale candle alerts, exchange throttling, and order reconciliation lag.
- Track position exposure, rejected intents, and repeated risk adjustments.
- Review fill latency and venue error-rate metrics.
- For public Binance market data, watch websocket degradation separately from private stream health:
  - reconnect count
  - heartbeat overdue alerts
  - session rollover alerts
  - explicit failover-to-REST state
- For Binance private stream health, watch:
  - auth/init completion
  - subscribe completion
  - reconnect count
  - refresh attempt count and refresh failure count
  - session rollover alerts
  - termination / invalidation alerts
  - authoritative vs degraded state transitions
  - account update arrival vs reconciliation order updates
  - malformed private-payload translation alerts
  - latest signed status-query success/failure during reconciliation recovery
- For restricted-live soak review, watch:
  - `exchange_health.overall_state`
  - blocked mutation count
  - reconciliation recovery attempt count
  - reconciliation recovery success rate
  - whether the soak stopped because of `fatal_exchange_health`, `manual_attention`, or `max_blocked_mutations`
- Treat the shared exchange health surface as the operator-facing rollup for:
  - private stream connectivity and authority
  - reconciliation convergence state
  - clock-sync status
  - signed status-query health
- Read it from the persisted `runtime_health.json` and `runtime_status.md` artifacts rather than reconstructing it from raw adapter details by hand.
- Expect the main runtime path to persist this surface automatically for Binance-facing runs. If a live-facing or Binance rehearsal run has no exchange-health section, treat that as an observability defect.
- If an exchange-health provider is absent, the persisted surface should still show explicit `unknown` component states rather than omitting the section.

## Report-Only Monitoring

- Inspect the most recent JSONL report record for:
  - feature names present
  - optional index/stablecoin source presence
  - real-data context features such as 1d context fields when enabled
  - strategy outputs
  - risk outcomes
  - generated but non-submitted execution intents
- Treat missing reports as a runtime/storage failure even when no trading occurs.
- Treat insufficient closed-candle context as a market-data/runtime failure, not as a strategy issue.
- If Binance public WS is active, confirm the last trigger came from a closed-bar event rather than an open/incomplete kline update.
- Inspect runtime observability artifacts on every operator pass:
  - append-only cycle summaries
  - latest health/status snapshot
  - operator markdown status report
- Treat degraded-but-non-fatal flags as action items:
  - `index_suite_missing`
  - `stablecoin_missing`
  - `exchange_data_degraded`
- Inspect stablecoin observability outputs separately when configured:
  - JSONL snapshot export
  - CSV snapshot export
  - markdown summary
  - `source_type` and `source_fresh_until`
  - descriptive metrics only; do not treat them as direct trade signals

## Paper Monitoring

- Inspect simulated `ExecutionIntent`, `OrderState`, and `FillEvent` records together.
- Confirm paper portfolio transitions match expectations after each cycle.
- Treat continuity drift between `starting_portfolio_state` and the prior `ending_portfolio_state` as an operator error or test setup error.
- Do not interpret paper fills as exchange-reconciled truth.
- For multi-cycle sessions, inspect the paper session summary after the last bar:
  - `total_cycles`
  - `action_cycle_count`
  - final `PortfolioState`
  - final per-instrument `PositionState`
- If repeated bars produce non-reproducible paper outputs with identical inputs, treat that as a runtime defect rather than market variance.

## Restricted-Live Gate

- Restricted-live is blocked unless all required tests pass.
- Restricted-live is blocked unless Binance private stream, reconciliation, and clock sync gates are explicitly reviewed.
- Restricted-live is blocked if open gaps are not disclosed in operator-facing form.
- Restricted-live is blocked unless the rehearsal preflight passes with:
  - Binance credentials present
  - `exchange_mode=restricted_live_rehearsal`
  - writable report and log paths
  - explicit `--confirm-rehearsal-only`
  - explicit `--allow-restricted-live-rehearsal`
  - explicit `--confirm-no-order-submission`
- Restricted-live must roll back to `paper` or `report_only` on any unexplained order-status or observability failure.
- Restricted-live review should be recorded against [`docs/release_readiness_checklist.md`](/home/terratunes/code/trading/runtime2/docs/release_readiness_checklist.md), not handled informally.

## Rehearsal Summary Artifacts

Each rehearsal entrypoint appends a structured record to:

- `reports/rehearsal_run_summaries.jsonl`

Inspect these records for:

- selected mode
- exchange mode
- config and data path targets
- preflight checks completed
- warnings
- blocking errors
- confirmation that order submission remained disabled

Also inspect:

- `reports/latest_rehearsal_summary.md`
- `reports/latest_launch_summary.json`
- `reports/latest_launch_summary.md`
- latest unified exchange health fields in `runtime_health.json`
- the `Exchange Health` section in `runtime_status.md`, which should always show:
  - private stream
  - reconciliation
  - clock sync
  - signed status query

The automated dry-run workflow additionally writes per-run artifacts:

- `rehearsal_run_summaries.jsonl`
- `latest_rehearsal_summary.md`
- `latest_launch_summary.json`
- `latest_launch_summary.md`
- `runtime_cycles.jsonl`
- `runtime_cycle_summaries.jsonl`
- `runtime_health.json`
- `runtime_status.md`
- `input_manifest.json`
- `run_summary.json`
- `run_summary.md`
- `paper_state_transitions.jsonl` for paper mode

Treat missing `latest_launch_summary.json` or `runtime_cycles.jsonl` inside the run directory as a launcher failure rather than a reporting-only issue.
Treat missing `exchange_health` inside `runtime_health.json` as an observability gap when exchange-facing rehearsal is expected.

## Pre-Restricted-Live Review

Before any restricted-live review:

1. Run the required marker-based regression groups and record results.
2. Verify documentation completeness against the release checklist.
3. Verify runtime observability artifacts exist and are current.
4. Verify Binance private stream, reconciliation, and clock sync gates are still unresolved only where explicitly disclosed.
5. Record allow/block decision with operator name and date.

## Common Failure Modes

- Datafeed stale or missing
  - pause new execution plans
  - keep collecting diagnostics
  - resume only after freshness checks pass
- Public websocket degraded
  - inspect reconnect count and heartbeat status
  - confirm whether failover-to-REST is active
  - do not assume candle-close continuity until closed-bar detection is confirmed again
- Exchange rejects order
  - record full rejection context
  - reconcile order state
  - re-evaluate strategy intent on next cycle rather than blindly retrying
- Reconciliation uncertainty
  - inspect append-only reconciliation logs before assuming the order failed
  - confirm whether the workflow is in `status_query_pending` or `unreconciled_manual_attention`
  - inspect the latest signed status-query health and lookup source before retrying
  - do not mutate portfolio state from ambiguous exchange status
  - escalate operator review when recovery remains unresolved
- Private stream terminated or invalidated
  - treat as a hard exchange-health issue for any live-facing mode
  - reinitialize authenticated session before trusting further order/account state
  - do not treat public market-data continuity as a substitute for private order/account truth
  - if translated private payloads become malformed, stop before portfolio/account mutation and preserve the payloads for adapter diagnosis
  - if durability is unclear, run the private transport soak rehearsal and inspect `health_transitions.jsonl` before resuming restricted-live rehearsal
- Portfolio mismatch
  - trigger reconciliation workflow
  - compare exchange balances with latest snapshot and fills
  - halt live execution if mismatch exceeds threshold
- Restart recovery
  - reload latest snapshots
  - reconcile open orders and positions before strategy evaluation resumes

## Incident Procedures

### Stale Data

- state
  - degraded in `report_only`
  - degraded in `paper`
  - fatal in `restricted_live`
- inspect first
  - latest `RuntimeCycleResult.quality_states`
  - latest `runtime_health.json`
  - last accepted bar close time
- recover
  - confirm upstream market-data freshness recovered
  - rerun preflight or dry-run if operator confidence is low
  - restart runner only after freshness is visible in persisted artifacts
- halt if
  - stale state repeats after restart
  - bar close continuity cannot be explained

### Missing Index Suite Snapshot

- state
  - degraded but non-fatal in `report_only`
  - degraded but non-fatal in `paper`
  - blocker only if restricted-live policy later promotes it to required
- inspect first
  - `index_suite_context`
  - `decision_context_summary`
  - degradation flags in `runtime_status.md`
- recover
  - confirm snapshot repository freshness and requested version
  - rerun after repository input is restored
- halt if
  - missing snapshot coincides with unexplained strategy/risk drift

### Missing Stablecoin Snapshot

- state
  - degraded but non-fatal in `report_only`
  - degraded but non-fatal in `paper`
  - not a direct trade blocker in phase 1
- inspect first
  - stablecoin JSONL/CSV/markdown outputs
  - `stablecoin_snapshot_status`
  - degradation flags in runtime status
- recover
  - confirm collector freshness and source type
  - resume after descriptive snapshot flow is restored
- halt if
  - missing stablecoin data is being mistaken for a strategy defect

### Binance Private Stream Interruption

- state
  - non-fatal for pure `report_only`
  - non-fatal for pure `paper`
  - fatal for any restricted-live rehearsal relying on exchange truth
- inspect first
  - private-stream lifecycle state
  - termination/invalidation alerts
  - reconnect count and session rollover status
- recover
  - reinitialize the authenticated session
  - confirm health artifacts update after reconnect
  - keep portfolio mutation blocked until stream truth is restored
- halt if
  - interruption persists
  - sequence/gap visibility is missing
  - reconciliation confidence cannot be restored

### Reconciliation Unresolved State

- state
  - operator attention required in all modes
  - fatal for restricted-live continuation
- inspect first
  - append-only reconciliation logs
  - `unknown_execution_ids`
  - recovery actions and lookup attempts
- recover
  - confirm whether a terminal state was recovered
  - if not, hold further live-facing action and preserve artifacts
- halt if
  - the workflow remains `unreconciled_manual_attention`
  - portfolio state would need guessing

### Clock Sync Uncertainty

- state
  - degraded in `report_only`
  - degraded in `paper`
  - fatal in `restricted_live`
- inspect first
  - `offset_ms`
  - `round_trip_ms`
  - `time_sync_uncertain` quality state
- recover
  - resample server time
  - confirm offset is back within tolerated range before restart
- halt if
  - uncertainty repeats or cannot be measured reliably

## Mode Recovery Differences

- `report_only`
  - may continue on missing Index Suite or stablecoin inputs with explicit degraded flags
  - restart threshold is lower because no exchange side effects exist
- `paper`
  - may continue on the same degraded optional inputs
  - verify continuity between prior ending portfolio and next starting portfolio before restart
- `restricted_live`
  - fail closed on defined blockers
  - do not restart until exchange-health, reconciliation, and clock conditions are explicitly green again

## Incident Note Template

```text
Incident:
Date:
Mode:
Operator:

Symptom:
- 

First Artifacts Checked:
- 

Degraded Or Fatal:
- 

Immediate Action:
- 

Restart Or Halt Decision:
- 

Follow-Up Required:
- 
```

## Phase-1 Operator Rule

- `report_only` is the first reference implementation.
- Do not treat generated execution intents as submitted orders.
- Do not attempt manual exchange intervention based solely on report-only intents.
- Do not treat paper fills as market-confirmed executions.
- Do not treat `restricted_live` as live-ready. It is a gated testing step only.

## Operational Guardrails

- Prefer fail-closed behavior when market data freshness is uncertain.
- Separate paper-mode validation from live-mode enablement.
- Keep audit artifacts in storage before and after order submission decisions.
- Keep recovery attempts and reconciliation outcomes append-only and operator-visible.
- Keep runtime cycle summaries and latest health/status artifacts current before any restricted-live review.
