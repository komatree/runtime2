# runtime2 Project State And Next Steps

## 1. Executive Summary

`runtime2` is a new Binance-focused candle runtime with strong architecture boundaries, a real launcher path, fail-closed restricted-live rehearsal, and operator-visible observability. The major Binance private-stream migration has already been completed: private bootstrap now uses Spot WS-API `userDataStream.subscribe.signature` instead of the deprecated REST listenKey bootstrap path. Canonical private payload translation, replay-safe reconciliation persistence, mutation safeguard gating, shared exchange health reporting, and long-running soak tooling are all present.

What is verified:
- launcher/config discipline and preflight gating
- dry-run workflow on the real launcher path
- canonical Binance private bootstrap alignment with current Spot WS-API direction
- fail-closed mutation behavior after private-stream invalidation
- bounded-duration soak stopping
- real testnet idle-session soak evidence for `2h` and `6h`
- paired create/cancel active private-event proof from `a5/r5`
- paired fill-related private-event proof from `a6/r6`
- reconciliation convergence under active `cancelled` and `filled` conditions
- paired direct account/balance-update proof from `a2/r2`

What is not yet verified:
- signed-path correctness as a separately preserved dedicated evidence class remains narrower than ideal
- broader production-grade operational proof for the full signed-path plus active-event operating loop
- production-grade operational proof for reconciliation under broader real disruption

Current readiness verdict:
- `report_only`: ready
- `paper`: ready
- `restricted_live`: rehearsal-capable, fail-closed, not production-ready
- production promotion: blocked

Immediate next priority:
- re-run and preserve the dedicated signed-path harness evidence as a standalone reviewed class, then exercise the broader operator end-to-end flow against the now-cleared narrow active-event evidence baseline.

## 2. System Scope and Architecture

`runtime2` is the authoritative new codebase for the Binance integration effort. It is not a compatibility layer over legacy micro-live. The runtime flow stays explicit:
- closed bar trigger
- normalized candle slice
- feature snapshot build
- strategy evaluation
- risk evaluation
- execution intent
- persistence/reporting
- future exchange execution and reconciliation

Major components:
- contracts and core models in [`app/contracts`](/home/terratunes/code/trading/runtime2/app/contracts)
- launcher/config/rehearsal flow in [`app/config`](/home/terratunes/code/trading/runtime2/app/config) and [`scripts/runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py)
- separate runners in [`app/runtime`](/home/terratunes/code/trading/runtime2/app/runtime)
- Binance adapter logic in [`app/exchanges/binance`](/home/terratunes/code/trading/runtime2/app/exchanges/binance)
- monitoring/reporting in [`app/monitoring`](/home/terratunes/code/trading/runtime2/app/monitoring) and [`app/storage`](/home/terratunes/code/trading/runtime2/app/storage)

Key design principle:
- strategy state is not exchange state
- strategy, risk, and portfolio-facing code consume internal contracts such as `FeatureSnapshot`, `OrderState`, `FillEvent`, `AccountSnapshot`, and `RuntimeCycleResult`
- exchange-native payloads stop at the Binance adapter boundary

runtime2 differs from legacy micro-live in deliberate ways:
- config-driven launcher instead of env-only launch semantics
- mode-separated `report_only`, `paper`, and `restricted_live` runners instead of one live-ish path
- structured JSONL/runtime-health artifacts instead of relying mainly on sqlite-style postmortem summarization
- stronger explicit reconciliation and mutation-safety boundaries

References:
- [`docs/data_contracts.md`](/home/terratunes/code/trading/runtime2/docs/data_contracts.md)
- [`docs/runtime_flow.md`](/home/terratunes/code/trading/runtime2/docs/runtime_flow.md)
- [`docs/micro_live_to_runtime2_inheritance_audit.md`](/home/terratunes/code/trading/runtime2/docs/micro_live_to_runtime2_inheritance_audit.md)

## 3. What Has Been Completed

Completed items with concrete evidence:

| Item | Current state | Evidence |
| --- | --- | --- |
| REST listenKey bootstrap replaced | completed | [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py), [`docs/binance_change_compliance_audit.md`](/home/terratunes/code/trading/runtime2/docs/binance_change_compliance_audit.md) |
| Private WS-API bootstrap aligned to current Spot model | completed | `userDataStream.subscribe.signature` used in [`app/exchanges/binance/private_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_transport.py) |
| Mutation blocked after stream invalidation until later safe confirmation | completed | [`app/exchanges/binance/live_portfolio_gate.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/live_portfolio_gate.py), [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md) |
| Soak duration enforcement bug fixed | completed | bounded read + deadline enforcement in [`app/monitoring/restricted_live_soak.py`](/home/terratunes/code/trading/runtime2/app/monitoring/restricted_live_soak.py) and [`app/exchanges/binance/restricted_live_transport.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/restricted_live_transport.py) |
| Dedicated Spot testnet rehearsal config | completed | [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml) |
| Launcher/config discipline | completed | thin wrappers + authoritative launcher in [`scripts/run_report_only.sh`](/home/terratunes/code/trading/runtime2/scripts/run_report_only.sh), [`scripts/run_paper.sh`](/home/terratunes/code/trading/runtime2/scripts/run_paper.sh), [`scripts/run_restricted_live.sh`](/home/terratunes/code/trading/runtime2/scripts/run_restricted_live.sh), [`scripts/runtime2_rehearsal.py`](/home/terratunes/code/trading/runtime2/scripts/runtime2_rehearsal.py) |
| Canonical private payload translator | completed | [`app/exchanges/binance/private_payload_translator.py`](/home/terratunes/code/trading/runtime2/app/exchanges/binance/private_payload_translator.py) |
| Replay-safe and restart-safe reconciliation persistence | completed | [`app/storage/reconciliation_state.py`](/home/terratunes/code/trading/runtime2/app/storage/reconciliation_state.py) |
| Shared exchange health visibility | completed | [`app/monitoring/exchange_health.py`](/home/terratunes/code/trading/runtime2/app/monitoring/exchange_health.py), persisted through runtime status/health outputs |
| Operator-visible summaries and artifacts | completed | [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md), soak artifacts under [`reports/soak_sessions`](/home/terratunes/code/trading/runtime2/reports/soak_sessions) |
| Staged soak practice inherited | completed | campaign and evidence review flow documented in [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md) |
| Fail-closed posture inherited and extended | completed | [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md), [`docs/micro_live_to_runtime2_inheritance_audit.md`](/home/terratunes/code/trading/runtime2/docs/micro_live_to_runtime2_inheritance_audit.md) |

Important completed nuance:
- `listenKeyExpired` is still handled as an incoming invalidation event where needed
- this is not a sign that runtime2 still bootstraps through deprecated REST listenKey calls

## 4. Evidence Collected So Far

### 1h validation soaks

Available evidence:
- multiple validation directories under [`reports/soak_sessions`](/home/terratunes/code/trading/runtime2/reports/soak_sessions)

What is proven:
- launcher path and artifact writing work on real rehearsal runs
- short bounded-duration restricted-live soak runs complete with the expected artifact shape

What is not proven:
- long-running durability
- active private-event behavior
- reconciliation recovery under real event disruption

### 2h soak evidence

Reviewed evidence:
- [`reports/soak_sessions/binance-testnet-soak-2h-night/soak_summary.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-soak-2h-night/soak_summary.json)

Observed:
- `stop_reason == completed`
- `aborted == false`
- `final_exchange_health_state == healthy`
- `completed_cycles == 188`
- `refresh_attempts == 2`
- `refresh_failures == 0`
- `reconnect_count == 0`
- `heartbeat_overdue_events == 0`
- `reconciliation_recovery_attempts == 0`
- `blocked_mutation_count == 0`

What is proven:
- idle-session durability for 2h on Spot testnet
- artifact completeness
- clean renewal behavior during an idle session

What is not proven:
- broader active private-event coverage beyond the reviewed paired scenarios
- real reconciliation convergence
- mutation gating under real private order/account updates

### 6h soak evidence

Reviewed evidence:
- [`reports/soak_sessions/binance-testnet-soak-6h/soak_summary.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-soak-6h/soak_summary.json)

Observed:
- `stop_reason == completed`
- `aborted == false`
- `final_exchange_health_state == healthy`
- `completed_cycles == 545`
- `refresh_attempts == 6`
- `refresh_failures == 0`
- `reconnect_count == 0`
- `heartbeat_overdue_events == 0`
- `reconciliation_recovery_attempts == 0`
- `blocked_mutation_count == 0`

What is proven:
- stronger idle-session continuity than the 2h run
- bounded-duration soak fix works in practice
- repeated renewal can remain clean over a longer session

What is not proven:
- broader active private-event durability beyond the reviewed paired scenarios
- live private/account/order flow correctness
- real recovery path behavior

### Idle-session durability evidence

What is proven:
- runtime2 can maintain a healthy private-session state during real idle testnet sessions
- health and soak artifacts persist correctly
- renewal path can succeed repeatedly without reconnect churn in the reviewed sessions

What is not proven:
- private truth under active order flow
- recovery from real missing private events
- operator reaction under repeated degradation

Important warning:
- idle soak success is not active-event success

### Launcher / monitoring / reporting evidence

What is proven:
- launcher-backed dry-run and restricted-live rehearsal paths exist and generate auditable artifacts
- runtime health and status reports persist unified exchange health
- soak artifact structure is stable and operator-readable

Key references:
- [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/production_gate_pre_audit.md`](/home/terratunes/code/trading/runtime2/docs/production_gate_pre_audit.md)

What is not proven:
- that operator workflow is complete enough without additional operating-PC clarifications

### Binance compliance audit evidence

What is proven:
- no active `/api/v1` usage
- no active `userDataStream.start/ping/stop` usage
- current private bootstrap path aligns to WS-API subscription

Reference:
- [`docs/binance_change_compliance_audit.md`](/home/terratunes/code/trading/runtime2/docs/binance_change_compliance_audit.md)

What is not proven:
- signed-path correctness on current Spot testnet
- explicit `eR` / expiryReason tolerance under translator tests

### Deprecated API scan evidence

What is proven:
- deprecated bootstrap usage is not active in production or rehearsal code paths
- remaining `listenKey` mentions are historical context, compatibility aliasing, event handling, or artifact naming drift

Reference:
- [`reports/binance_deprecated_usage_scan.md`](/home/terratunes/code/trading/runtime2/reports/binance_deprecated_usage_scan.md)

What is not proven:
- that remaining legacy-loaded artifact naming will not confuse operators

### Signed-path review evidence

What is proven:
- REST signing implementation uses encoded query construction before HMAC
- WS-API subscription signing exists and is adapter-local
- paired `a5/r5` and `a6/r6` evidence imply the signed private path was good enough to support real driver-backed create/cancel and fill handling on Spot testnet

Reference:
- [`docs/binance_signed_path_verification_plan.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_plan.md)

What is not proven:
- separately preserved full signed-path evidence remains narrower than ideal
- special-character safety
- explicit `-1022 INVALID_SIGNATURE` prevention evidence

### Paired create/cancel active-event proof

Reviewed paired evidence:
- action driver:
  - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_events.jsonl)
  - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a5/action_driver/action_driver_summary.md)
- runtime:
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_cycles.jsonl)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/runtime_health.json)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/reconciliation_events.jsonl)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r5/soak_summary.md)

What is proven:
- create and cancel actions definitely happened
- the same exchange order id `17384129` appeared in runtime reconciliation evidence
- runtime automatically converged that order to terminal `cancelled`
- reconciliation under active create/cancel conditions remained clean and operator-safe

What is not yet proven:
- none within the narrow create/cancel evidence class itself; direct account-update proof is reviewed separately below

### Paired fill-related active-event proof

Reviewed paired evidence:
- action driver:
  - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_events.jsonl)
  - [`reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-active-private-driver-20260315-a6/action_driver/action_driver_summary.md)
- runtime:
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_cycles.jsonl)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/runtime_health.json)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/reconciliation_events.jsonl)
  - [`reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-active-private-driver-20260315-r6/soak_summary.md)

What is proven:
- the fill-attempt action definitely happened for exchange order id `17387064`
- runtime reconciliation artifacts referenced the same order id `17387064`
- runtime converged that order to terminal `filled`
- reconciliation remained clean under the richer active scenario

What is not yet proven:
- the failed resting create in `a6` does not add new create/cancel proof
- direct account-update proof is reviewed separately below

### Paired direct account-update proof

Reviewed paired evidence:
- action driver:
  - [`reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_events.jsonl)
  - [`reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_summary.md`](/home/terratunes/code/trading/runtime2/reports/event_exercises/binance-testnet-account-update-a2/action_driver/action_driver_summary.md)
- runtime:
  - [`reports/soak_sessions/binance-testnet-account-update-r2/runtime_cycles.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/runtime_cycles.jsonl)
  - [`reports/soak_sessions/binance-testnet-account-update-r2/runtime_health.json`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/runtime_health.json)
  - [`reports/soak_sessions/binance-testnet-account-update-r2/reconciliation_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/reconciliation_events.jsonl)
  - [`reports/soak_sessions/binance-testnet-account-update-r2/soak_summary.md`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/soak_summary.md)
  - [`reports/soak_sessions/binance-testnet-account-update-r2/account_update_events.jsonl`](/home/terratunes/code/trading/runtime2/reports/soak_sessions/binance-testnet-account-update-r2/account_update_events.jsonl)

What is proven:
- a successful fill attempt definitely happened for exchange order id `17393758`
- runtime reconciliation artifacts referenced the same order id `17393758`
- runtime persisted a direct `outboundAccountPosition` account-update artifact
- the account-update artifact directly captured `BTC` and `USDT` balance state during the paired active window
- account-side proof now goes beyond order-state-only inference and beyond mismatch-alert-only evidence

What is not yet proven:
- broader production-rehearsal readiness outside the now-cleared narrow active-event evidence classes

### Failure injection and reconciliation disruption

What is proven:
- deterministic scenario harnesses and tests exist
- restricted-live and reconciliation paths have strong simulated coverage

What is not currently preserved as reviewed workspace evidence:
- I did not find checked-in artifact directories under `reports/failure_injection/` or `reports/reconciliation_disruption/` in the current workspace snapshot

What is not proven:
- real exchange operational behavior from those scenario classes

## 5. Audit Conclusions

### Operational inheritance

Based on [`docs/micro_live_to_runtime2_inheritance_audit.md`](/home/terratunes/code/trading/runtime2/docs/micro_live_to_runtime2_inheritance_audit.md):

`inherited correctly`
- thin launch/wrapper flow
- preflight safety checks
- operator-visible summaries and staged soak practice
- fail-closed posture
- testnet/mainnet separation, now explicit

`intentionally replaced`
- env-only launch semantics
- one mixed live path
- sqlite-first postmortem surface

`missing / insufficiently inherited`
- signed auth-check as a pre-launch operator step
- explicit operating-PC checklist
- explicit repeated exchange-error halt rule in operator-facing language
- explicit graceful external stop convention for long-running soak sessions

### Binance compliance

Based on [`docs/binance_change_compliance_audit.md`](/home/terratunes/code/trading/runtime2/docs/binance_change_compliance_audit.md):

`handled and verified`
- v1 endpoint retirement
- deprecated `listenKey` / `userDataStream.start-ping-stop` removal
- WS-API `userDataStream` subscription alignment

`handled but not yet verified`
- `executionReport` `eR` / expiryReason tolerance
- percent-encode-before-HMAC signing

`not yet handled`
- `ICEBERG_PARTS = 100` implications

### Deprecated API usage

Based on [`reports/binance_deprecated_usage_scan.md`](/home/terratunes/code/trading/runtime2/reports/binance_deprecated_usage_scan.md):

- no active deprecated Spot private bootstrap remains
- remaining legacy strings are mostly harmless and explainable
- optional cleanup remains around rehearsal artifact naming such as `listen_key_refresh.jsonl`

### Signed-path review

Based on [`docs/binance_signed_path_verification_plan.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_plan.md):

- implementation is present
- evidence is not yet strong enough
- next verification should focus on real Spot testnet proof and explicit encoded-signature test coverage

## 6. Current Open Gaps

Current concrete gaps:
- signed-path current Spot testnet proof is still somewhat weaker as a separately preserved evidence class than the paired run now suggests
- `executionReport` `eR` / expiryReason tolerance is not explicitly tested
- operating-PC workflow gaps remain in runtime2 runbooks
- explicit graceful stop convention for long-running soak sessions is still weak
- explicit exchange-error halt rule in operator language is still weaker than legacy micro-live practice
- `ICEBERG_PARTS` explicit guard/test is not yet handled
- failure-injection and reconciliation-disruption harnesses exist, but reviewed real artifact retention is not part of the current workspace snapshot
- clock sync and status-query health often remain `unknown` during idle-session soaks, which is explainable but still leaves evidence gaps

## 7. Recommended Execution Order

Use this order strictly.

1. Operator/runbook corrections.
Why first:
- they are low-cost
- they reduce avoidable PC/operator mistakes before collecting more evidence

Required:
- add explicit operating-PC checklist
- add explicit repeated exchange-error halt rule
- add explicit graceful stop convention for soak runs

2. Signed-path verification.
Why second:
- if signed REST/WS behavior is wrong, later live/event evidence is ambiguous
- this is the shortest path to removing a current Binance correctness uncertainty

Required:
- execute [`docs/binance_signed_path_verification_plan.md`](/home/terratunes/code/trading/runtime2/docs/binance_signed_path_verification_plan.md)

3. Parser tolerance tests for `eR` / expiryReason.
Why third:
- this is small, local, and removes a specific 2026 Binance compatibility blind spot
- it should be resolved before relying on active private-event evidence

4. Active private-event exercise on Spot testnet.
Why fourth:
- idle-session evidence is already good enough to justify this
- now the main missing proof is active private-event handling, not idle continuity

Required:
- one rehearsal session with actual private order/account events
- preserved artifacts showing translation, gate behavior, and reconciliation visibility

5. Reconciliation fault and recovery evidence under live-like conditions.
Why fifth:
- after active private events are proven, recovery evidence becomes interpretable
- this should confirm convergence behavior beyond simulation

6. Final production-gate review.
Why last:
- only after operator workflow, signed paths, parser tolerance, active-event proof, and recovery evidence are complete does a production review become meaningful

## 8. Production Readiness Criteria

Before runtime2 can be considered ready for production rehearsal, all of these minimum gates must be met:

1. Launcher and operator workflow gates
- authoritative launcher path remains the only supported entrypoint
- explicit operating-PC checklist exists and is followed
- explicit graceful stop convention exists

2. Binance API correctness gates
- no deprecated private bootstrap usage
- signed REST testnet proof exists
- signed WS-API subscription testnet proof exists
- explicit `eR` / expiryReason tolerance tests exist

3. Runtime correctness gates
- canonical translation remains mandatory
- live mutation safeguard remains mandatory
- invalidation-driven REST recovery cannot mutate portfolio state without later explicitly safe confirmation

4. Operational evidence gates
- at least one real active private-event rehearsal artifact set exists and is reviewed
- reconciliation recovery under real or near-real disruption is evidenced, not only simulated
- long-running soak evidence includes more than idle continuity

5. Production posture gates
- unrestricted live submission path remains blocked until explicitly reviewed
- all open blockers in [`docs/production_gate_pre_audit.md`](/home/terratunes/code/trading/runtime2/docs/production_gate_pre_audit.md) are cleared by evidence, not only by scaffolding

If any one of these is missing, production promotion should not be considered.

## 9. Risks and Misinterpretations to Avoid

- idle soak is not active-event proof
- transport stability is not runtime correctness
- Binance compliance review is not live correctness
- signed-path implementation is not the same as signed-path proof
- operator workflow gaps can still create incidents even when architecture is strong
- runtime2 is not re-learning everything from scratch; many key operational patterns were inherited correctly
- newer architecture does not automatically mean higher operational confidence
- clean 2h or 6h idle sessions do not justify production claims

## 10. Immediate Next Actions

### Today

- re-run and preserve the dedicated signed-path verification artifact set
- review the operator runbook/checklist against the now-cleared narrow active-event evidence baseline
- confirm the remaining broader readiness items are explicitly tracked without over-claiming production readiness

### This week

- execute the signed-path verification plan on Spot testnet
- add explicit translator tests for `executionReport` `eR` / expiryReason tolerance
- exercise a broader end-to-end signed-path plus active-event operating flow

### Before production rehearsal

- preserve and review active private-event artifacts
- preserve and review reconciliation recovery evidence from non-idle behavior
- confirm no bypass exists around the mutation safeguard layer
- complete a final evidence review against [`docs/production_gate_pre_audit.md`](/home/terratunes/code/trading/runtime2/docs/production_gate_pre_audit.md)

## Current Verdict

Best current verdict:
- architecture maturity: strong
- operational inheritance: mostly good, with practical operator gaps
- Binance API compliance: mostly aligned, partially verified
- runtime correctness evidence: strong in simulation, idle-session rehearsal, and bounded active private-event proof
- production readiness: blocked
