# runtime2 Operator Runbook

## Purpose

This runbook defines the concrete operator procedure for `runtime2` Binance rehearsal work.

Use this document for:
- pre-launch checks
- signed auth/bootstrap validation
- long-running soak operation
- exchange-health response
- controlled stop / halt decisions

This is operator-facing.
It is not a production approval document.

Read together with:
- [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md)
- [`docs/production_gate_pre_audit.md`](/home/terratunes/code/trading/runtime2/docs/production_gate_pre_audit.md)
- [`docs/runtime2_project_state_and_next_steps.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_project_state_and_next_steps.md)

## Current Stage Position

The broader `restricted_live_rehearsal` stage is now closed.

Authoritative broader baseline:

- runtime:
  - [`reports/soak_sessions/binance-testnet-broader-rehearsal-r5/`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-broader-rehearsal-r5)
- scheduler:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-scheduler)
- action windows:
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a1/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a2/action_driver)
  - [`reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver/`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-broader-rehearsal-r5-a3/action_driver)

Recorded result:

- broader-stage classification: `PASS WITH CAUTION`
- broader-stage readiness verdict: sufficient to exit the broader `restricted_live_rehearsal` stage

Operator meaning:

- do not reopen broader-stage questions unless later evidence shows regression
- use the same lineage/session model for the next bounded operator / bounded micro-live stage
- keep fail-closed safeguards, stale-output protection, and scheduler late-start abort behavior unchanged

## 1. Before Any Binance Rehearsal

Complete these checks in order.

1. Complete the operating-PC checklist in [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md).
2. Confirm the intended config file matches the intended environment.
3. Confirm testnet credentials are loaded for testnet rehearsal.
4. Confirm `reports/` and `logs/` are writable.
5. Confirm the target run is still rehearsal-only and not unrestricted live trading.

## 2. Canonical Entrypoints

Use only the existing launcher and wrapper surface.

Preflight:

```bash
bash scripts/preflight_runtime2.sh \
  --mode restricted_live \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

Restricted-live rehearsal launcher:

```bash
bash scripts/run_restricted_live.sh \
  --config configs/runtime2_restricted_live_testnet.toml \
  --execution-data data/binance \
  --context-data data/binance \
  --reports-dir reports \
  --logs-dir logs \
  --exchange-mode restricted_live_rehearsal \
  --confirm-rehearsal-only \
  --allow-restricted-live-rehearsal \
  --confirm-no-order-submission
```

Short signed/bootstrap validation run:

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

Post-run review helper:

```bash
bash scripts/check_soak_result.sh binance-testnet-soak-validation-1h
```

For the next bounded operator / bounded micro-live stage, continue to require:

- fresh runtime run ids for every session
- `runtime_session.json` as the source of truth for scheduler timing/binding
- `scheduler_manifest.json` and `scheduler_events.jsonl` for scheduler lineage review
- `action_driver_result.json` for each planned action window
- no manual timestamp copying between terminals

## 3. Pre-Launch Signed Auth-Check Procedure

There is not yet a dedicated one-shot live auth-check helper script in `runtime2`.

There is now a read-only local credential sanity helper:

```bash
python scripts/check_binance_testnet_credentials.py \
  --config configs/runtime2_restricted_live_testnet.toml
```

Use it before any live signed-path or private-bootstrap attempt.
It does not contact Binance.
It only checks:
- testnet config/profile alignment
- obvious placeholder values
- leading/trailing whitespace
- newline contamination
- whether the current `apiKey` matches the WS-API legal character shape

Current required operator procedure:

1. Run the read-only credential sanity helper first.
2. Run launcher preflight.
3. Run a short signed/bootstrap validation soak on Spot testnet.
4. Confirm the run creates the full soak artifact set.
5. Confirm the session reached authenticated private bootstrap successfully.
6. Confirm no deprecated listenKey bootstrap failure occurred.
7. Confirm no signature-related or credential-shape-related failure appears in the artifact set or operator output.

Minimum checks after the signed/bootstrap validation run:

- `reports/soak_sessions/<run_id>/soak_summary.json` exists
- `reports/soak_sessions/<run_id>/health_transitions.jsonl` exists
- `reports/soak_sessions/<run_id>/listen_key_refresh.jsonl` exists
- `reports/soak_sessions/<run_id>/runtime_health.json` exists
- `reports/soak_sessions/<run_id>/runtime_status.md` exists
- bootstrap did not fail with HTTP `410 Gone`
- bootstrap did not fail with a signature-related error
- bootstrap did not fail with Binance `-1100` on `apiKey` shape
- REST signed-path check did not return `401 Unauthorized`

Do not treat mere credential presence as an auth check.
The auth check is only complete when an actual signed/private bootstrap path succeeds on the intended environment.

If the current failure looks like an auth/credential issue, classify it before blaming runtime2:

- `apiKey` rejected for illegal characters:
  - most likely placeholder value, truncation, quoting damage, or wrong env loading path
- REST returns `401 Unauthorized`:
  - most likely invalid credentials or mainnet/testnet mismatch
- both WS and REST fail at the same time with auth-style errors:
  - treat as credential/env-path problem first

## 4. Repeated Exchange-Error Halt Policy

Stop the run immediately and hold further progression when any of these occur:

- fatal exchange health
- manual-attention reconciliation
- blocked mutation threshold reached
- private stream repeatedly invalidates without clear recovery
- signed status-query repeatedly fails for the same reason
- clock sync remains uncertain after recalibration attempts
- repeated reconnect churn becomes unexplained
- repeated subscription refresh failure occurs

Use this concrete halt rule:

1. First occurrence:
   - inspect artifacts
   - do not assume runtime2 is broken immediately
2. Second occurrence of the same exchange-health or transport failure class in the same session:
   - halt the session
   - do not proceed to a longer soak step
3. Repeated occurrence across sessions without a documented explanation:
   - hold progression
   - open an investigation before continuing

Examples of “same failure class”:

- repeated bootstrap signature failures
- repeated private-stream invalidation without later clean recovery
- repeated renewal failures
- repeated clock uncertainty
- repeated status-query failure with the same alert family

For the next bounded operator / bounded micro-live stage, also stop immediately when:

- runtime/session lineage artifacts are missing
- scheduler fails before intended bounded windows complete
- stale-output fail-if-exists protection triggers on a supposedly fresh run
- blocked mutation becomes non-zero

## 5. Graceful External Stop Convention

Use a controlled stop. Do not use `kill -9` unless the process is irrecoverably hung and you have already accepted artifact loss risk.

Preferred stop order:

1. `Ctrl-C` once in the terminal running the soak
2. wait long enough for:
   - current bounded cycle to finish
   - current websocket read timeout to expire
   - summary/artifact flush to complete
3. if the process still does not stop cleanly, send `SIGTERM`
4. only use forced kill as a last resort

After any externally stopped run:

1. mark the session as interrupted in operator notes
2. inspect:
   - `latest_rehearsal_summary.md`
   - `runtime_health.json`
   - `runtime_status.md`
   - `health_transitions.jsonl`
3. do not classify the session as a clean pass
4. do not promote to the next soak step without reviewing the interruption cause

## 6. Operator Response Guide For Unhealthy Exchange State

### If exchange health is `degraded`

Check first:

- private stream component state
- reconciliation component state
- clock sync component state
- signed status-query component state

Continue only when:

- degradation is understood
- current mode allows continued operation
- there is no unresolved reconciliation
- there is no ambiguous mutation path

Hold the session when:

- degradation repeats without explanation
- degradation escalates toward stream invalidation
- clock uncertainty remains unresolved

### If exchange health is `fatal`

Immediate action:

1. halt the session
2. preserve artifacts
3. do not restart immediately unless the failure cause is understood

Mandatory review artifacts:

- `runtime_health.json`
- `runtime_status.md`
- `health_transitions.jsonl`
- `reconnect_events.jsonl`
- `listen_key_refresh.jsonl`
- `reconciliation_events.jsonl`
- `soak_summary.json`

## 7. What To Check Before Concluding runtime2 Is At Fault

Check these in order.

### Environment and operator checks

- correct config file used
- correct endpoint profile used
- correct testnet credentials loaded
- `reports/` and `logs/` writable
- operating PC checklist actually satisfied

### Exchange/environment checks

- testnet service instability or maintenance
- local network interruption
- workstation sleep / hibernate / restart event
- clock drift or NTP issue
- disk-full or log-write issue

### Artifact checks

- does `runtime_health.json` show `unknown`, `degraded`, or `fatal`, and why
- does `runtime_status.md` agree
- do `health_transitions.jsonl` and `reconnect_events.jsonl` show a transport problem
- does `listen_key_refresh.jsonl` show renewal trouble
- does `reconciliation_events.jsonl` show explicit recovery or escalation

Only after those checks should the operator conclude:
- likely runtime2 defect
- likely Binance/environment issue
- likely operator/PC workflow issue

## 8. Long-Running Soak Session Procedure

Use this sequence for `6h`, `12h`, and `24h` rehearsal evidence runs.

1. Complete the operating-PC checklist.
2. Run preflight.
3. Run the short signed/bootstrap validation procedure if not already done for the current environment and credentials.
4. Launch the intended soak session.
5. Monitor:
   - `runtime_health.json`
   - `runtime_status.md`
   - exchange health transitions
6. On completion, run:

```bash
bash scripts/check_soak_result.sh <run_id>
```

7. Review the session against the documented hard thresholds before proceeding to a longer run.

## 9. Minimal Session Classification Rules

Classify a soak session as clean only when all are true:

- `stop_reason == completed`
- `aborted == false`
- expected artifacts are present
- no unexplained blocked mutation
- no fatal exchange health
- no manual-attention reconciliation
- no refresh failure

If the run is idle-stream only:
- classify it as durability evidence only
- do not treat it as active private-event proof

## 10. Recommended Helper Scripts Still Missing

These are still missing from the current operator surface:

1. dedicated read-only signed auth-check helper
2. explicit graceful external stop helper or STOP-file convention
3. operator-facing repeated exchange-error summarizer across sessions
