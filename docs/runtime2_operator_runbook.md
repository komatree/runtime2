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

Current bounded-stage summary:

- `binance-bounded-preflight-r1-30m`: `PASS WITH CAUTION`
- `binance-bounded-r1-4h`: `PASS WITH CAUTION`
- `binance-bounded-r2-4h`: `PASS WITH CAUTION`
- `binance-bounded-r3-4h`: `PASS WITH CAUTION`
- `binance-bounded-r4-8h`: `PASS WITH CAUTION`
- `binance-bounded-r5-8h`: `FAIL`
- `binance-envcheck-r0-1h`: `ENV-CHECK PASS WITH CAUTION`

Known caution classes carried into the current stage:

- `PERCENT_PRICE_BY_SIDE` causing `PARTIAL_SUCCESS_NONBLOCKING`
- reconnect / heartbeat churn

Known bounded-stage incident:

- `binance-bounded-r5-8h` recorded `window_aborted_late` for `a2`
- `a3` did not run
- final runtime artifact set was missing
- current retained evidence is most consistent with an interruption class affecting the environment or session continuity

## Binance Live Checklist v1

Use this checklist before the next bounded operator / bounded micro-live run.

- confirm the run is still Spot testnet and still `restricted_live_rehearsal`
- confirm `runtime_session.json`, `scheduler_manifest.json`, and per-window `action_driver_result.json` are expected review artifacts
- confirm no operator is relying on deprecated REST `listenKey` bootstrap assumptions
- confirm the intended private bootstrap path is still the subscribe-based Spot WebSocket API UDS path
- confirm `executionReport` optional metadata such as `expiryReason` / `eR` remains treated as tolerated input, not as a new live decision input
- confirm newer exchange metadata such as `executionRules`, `referencePrice`, `permissionSets`, `amendAllowed`, `quoteOrderQtyMarketAllowed`, STP-related fields, `MAX_ASSET`, and `myFilters` are being treated as watchpoints or future hardening items, not as reasons to improvise logic changes immediately before the run
- confirm unknown execution recovery remains inspectable and fail-closed
- confirm reconnect / heartbeat churn remains an explicit watchpoint
- confirm request-weight, order-count, and timeout uncertainty remain explicit watchpoints during the run
- confirm Demo Mode is not being conflated with the current bounded run; it is a later test-ladder stage, not a prerequisite for this run

## 1. Before Any Binance Rehearsal

Complete these checks in order.

1. Complete the operating-PC checklist in [`docs/runtime2_operating_pc_checklist.md`](/home/terratunes/code/trading/runtime2/docs/runtime2_operating_pc_checklist.md).
2. Confirm the intended config file matches the intended environment.
3. Confirm testnet credentials are loaded for testnet rehearsal.
4. Confirm local runtime data files under `data/binance/` are present and readable.
5. Confirm the approved config-referenced files exist on this host.
   - current concrete examples:
     - `data/binance/btcusdt_4h.json`
     - `data/binance/btcusdt_1d.json`
6. Confirm `reports/` and `logs/` are writable.
7. Confirm the target run is still rehearsal-only and not unrestricted live trading.

Quick data checks:

```bash
ls -l data/binance
test -f data/binance/btcusdt_4h.json
test -f data/binance/btcusdt_1d.json
```

## Credential Handling Standard

Use this standard for all future bounded operator runs.

- start from a fresh shell
- prefer the hidden-prompt WSL preflight path:
  - [`scripts/preflight_broader_rehearsal_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_broader_rehearsal_wsl.sh)
  - [`scripts/preflight_wsl.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_wsl.sh)
- if both `BINANCE_API_KEY` and `BINANCE_API_SECRET` are already present in the current shell, the preflight scripts should skip prompting and continue
- enter both `BINANCE_API_KEY` and `BINANCE_API_SECRET` through hidden prompts only
- do not run inline credential-bearing commands such as:
  - `BINANCE_API_KEY=... BINANCE_API_SECRET=... bash ...`
  - `env BINANCE_API_KEY=... BINANCE_API_SECRET=... python ...`
- do not share terminal output, pane capture, or screen recording while entering credentials
- unset credentials after the run completes:
  - `unset BINANCE_API_KEY BINANCE_API_SECRET`

Operator meaning:

- current-shell export behavior remains the supported compatibility path for the existing wrappers
- the safety change is only in how credentials are entered, not in how runtime or scheduler commands consume them

## Runtime Data Bundle Requirement

`runtime2` bounded execution requires local runtime data files under `data/binance/`.

- code arrives by Git
- credentials are injected locally
- runtime data bundle must be transferred separately to the Operations PC

Current concrete file examples:

- `data/binance/btcusdt_4h.json`
- `data/binance/btcusdt_1d.json`

Warning:

- missing runtime data files can cause early runtime failure before the normal bounded artifact set appears
- this may look like a silent or near-silent launch failure if the operator only checks later for `runtime_session.json`

Confirmed failure shape:

- `FileNotFoundError: data/binance/btcusdt_4h.json`

Remediation:

1. Re-transfer the approved runtime data bundle.
2. Re-check required files:

```bash
ls -l data/binance
test -f data/binance/btcusdt_4h.json
test -f data/binance/btcusdt_1d.json
```

3. Run a direct runtime smoke with a fresh `run_id`.
4. Only after that succeeds, launch the bounded wrapper run.

## Host Power And Sleep Discipline

For bounded runs longer than `4h`:

- use stable AC power
- disable sleep
- disable hibernate
- disable lid-close sleep behavior if applicable
- avoid leaving the run on a host that may suspend WSL, tmux, or the terminal session

Operator meaning:

- interruption-class failures invalidate bounded-run evidence
- host/session continuity is part of the operator responsibility for long runs

## Fail-Closed Interruption Policy

Treat the following as fail-closed conditions:

- `window_aborted_late`
- missing final runtime artifact set
- missing planned action-window artifacts for a normal bounded run
- interrupted scheduler lineage
- incomplete final runtime summary

Operator rules:

- do not resume interrupted runs
- do not manually run later windows under the same interrupted run id
- do not reconstruct missing artifacts by hand
- retain the incomplete artifact set for review

## Fresh Run-Id Requirement After Interruption

After any interrupted or incomplete run:

- use a fresh run id
- do not reuse the interrupted run id

Examples:

- invalid:
  - reuse `binance-bounded-r5-8h`
- valid:
  - `binance-bounded-r6-8h`
  - `binance-envcheck-r1-1h`

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

Binance-specific watchpoints for the bounded run:

- any unexpected `executionRules` or `referencePrice` payload change showing up in artifacts
- any operator-visible `expiryReason` / `eR` drift from the already tolerated shape
- any sign of deprecated REST `listenKey` assumptions reappearing instead of the subscribed UDS path
- any unexpected field-family expansion around `permissionSets`, `amendAllowed`, `quoteOrderQtyMarketAllowed`, or STP-related metadata
- any unexplained `MAX_ASSET` or `myFilters` constraint surfacing in operator-visible errors
- any unknown execution alert that does not converge cleanly
- any reconnect or heartbeat degradation that becomes unexplained
- any request-weight, order-count, or timeout pattern that becomes session-shaping instead of incidental

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
- reconnect / heartbeat churn becomes unexplained
- request-weight, order-count, or timeout errors repeat without a documented explanation

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
