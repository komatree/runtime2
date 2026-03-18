# Restricted Live Readiness

## Purpose

This document defines the minimum conditions required before `runtime2` may move from `report_only` and `paper` into `restricted_live` testing.

`restricted_live` is not full live trading. It is a tightly controlled pre-live test mode with explicit operational gates.

## Readiness Criteria

All items below must be true before restricted-live testing is allowed.

1. Runtime path readiness
   - `report_only` remains the reference implementation and is stable.
   - `paper` mode has passed continuity checks across repeated cycles.
   - `restricted_live` still performs no uncontrolled exchange side effects.
   - restricted-live quality gates fail closed before strategy/risk outputs are trusted.
2. Contract readiness
   - `docs/data_contracts.md` and `docs/runtime_flow.md` match the current code.
   - strategy-facing contracts remain venue-neutral.
   - exchange-specific behavior stays inside Binance adapter boundaries.
3. Binance gate readiness
   - private stream contract and lifecycle states are implemented and operator-visible
   - reconciliation contract is implemented and operator-visible
   - clock sync contract is implemented and operator-visible
   - unknown execution recovery flow is documented and testable
   - canonical Binance private payload translation is implemented and operator-visible
   - restricted-live portfolio mutation is blocked unless the live safeguard gate passes
4. Operational readiness
   - alertable runtime artifacts are being persisted
   - operator rollback criteria are defined and understood
   - open gaps are disclosed explicitly before each rollout decision
   - degraded states are visible in `DecisionContext` and `RuntimeCycleResult`
   - restricted-live rehearsal scenarios cover both allowed mutation and intentionally blocked mutation paths
5. Regression readiness
   - required regression groups are identified and auditable
   - marker-based test commands produce a reproducible gate report
   - no required gate group is skipped silently

## Required Passing Tests

The following test groups must be green before restricted-live testing:

- contract tests
- feature layer tests
- pure logic strategy tests
- runtime mode tests
- report-only integration tests
- paper-mode integration tests
- runtime observability tests
- report schema tests
- exchange adapter stub tests
- future reconciliation tests relevant to unknown execution handling
- scenario regression tests
- restricted-live rehearsal verification scenarios

Minimum full command:

```bash
pytest tests -q
```

Recommended auditable gate commands:

```bash
pytest -m "contracts or features or strategies or runtime_mode or exchanges" tests -q
pytest -m "report_only_integration or paper_integration or reconciliation or observability" tests -q
pytest -m scenario_regression tests -q
pytest -m regression tests -q
```

If any restricted-live-specific scaffolding tests are later added, they become mandatory gates as well.
Current restricted-live rehearsal scenarios must show:

- safe mutation after canonical translation and safeguard checks
- mutation blocked on malformed or ambiguous canonical state
- mutation blocked on unreconciled recovery state
- restart with unresolved reconciliation state restores that state clearly
- restart with degraded private-stream state keeps mutation blocked clearly
- restart with blocked portfolio-mutation state remains a valid safety success path
- machine-readable and markdown scenario summaries for operator review

## Required Documentation State

The following docs must be current before rollout review:

- [`docs/data_contracts.md`](/home/terratunes/code/trading/runtime2/docs/data_contracts.md)
- [`docs/runtime_flow.md`](/home/terratunes/code/trading/runtime2/docs/runtime_flow.md)
- [`docs/exchange_integration_notes.md`](/home/terratunes/code/trading/runtime2/docs/exchange_integration_notes.md)
- [`docs/operator_runbook.md`](/home/terratunes/code/trading/runtime2/docs/operator_runbook.md)
- [`docs/debugging_playbook.md`](/home/terratunes/code/trading/runtime2/docs/debugging_playbook.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/release_readiness_checklist.md`](/home/terratunes/code/trading/runtime2/docs/release_readiness_checklist.md)

If code changes the runtime flow, exchange blockers, persistence shape, or recovery path, rollout is blocked until docs are updated.

Documentation review must confirm:

- required docs exist and are not placeholder-empty
- runtime flow, data contracts, and Binance blockers reflect current code
- operator runbook matches current observability artifacts and rollback steps
- open gaps are disclosed in operator-facing language

## Rehearsal Entry Package

Restricted-live review is blocked unless the rehearsal entry package is present and usable:

- [`scripts/preflight_runtime2.sh`](/home/terratunes/code/trading/runtime2/scripts/preflight_runtime2.sh)
- [`scripts/run_report_only.sh`](/home/terratunes/code/trading/runtime2/scripts/run_report_only.sh)
- [`scripts/run_paper.sh`](/home/terratunes/code/trading/runtime2/scripts/run_paper.sh)
- [`scripts/run_restricted_live.sh`](/home/terratunes/code/trading/runtime2/scripts/run_restricted_live.sh)

The rehearsal package must fail closed on:

- missing config file
- missing required data paths
- non-writable report or log paths
- invalid exchange mode for the selected runner
- missing `--confirm-rehearsal-only` on run commands
- missing restricted-live safety confirmations
- any attempt to enable order submission

Restricted-live rehearsal additionally requires Binance credentials to be present even though unrestricted live trading is still disabled.
The rehearsal package must emit operator-facing summaries in append-only JSONL and latest-summary markdown form.
The authoritative launcher is `scripts/runtime2_rehearsal.py`; shell scripts remain thin wrappers only.

## Exchange Blocker Checklist

Restricted-live testing is blocked if any of these remain unclear or invisible:

- Binance private stream
  - auth/init lifecycle exists
  - subscribe lifecycle exists
  - reconnect lifecycle exists
  - session rollover handling exists
  - termination/invalidation handling exists
  - normalized ingestion contract exists
  - normalized event families for order/account/stream status exist
  - gap conditions produce explicit alerts
  - future transport responsibilities are documented
- Binance reconciliation
  - missing order updates are surfaced explicitly
  - unknown execution ids produce recovery actions
  - unresolved reconciliation state can be reloaded safely after restart
  - replay-safe recovery attempt numbering is visible and inspectable
  - private-stream gaps trigger explicit automatic signed status-query recovery or explicit manual-attention escalation
  - recovery trigger reason, gap state, resumed-from-snapshot state, and convergence result are operator-visible
  - portfolio mutation is held when reconciliation confidence is insufficient
- Live mutation safeguard gate
  - canonical private payload translation must occur before portfolio mutation
  - malformed payloads must block mutation
  - `recovering` or `unreconciled` order state must block mutation
  - account snapshot mismatch must block mutation
  - blocked-mutation reasons must be visible in cycle alerts and operator reports
- Binance clock sync
  - offset measurement exists
  - tolerance check exists
  - drift failures are surfaced before signed request logic is trusted
- Data quality blockers
  - `missing_data` must block restricted-live
  - `stale_data` must block restricted-live
  - `version_mismatch` must block restricted-live
  - `incomplete_bar` must block restricted-live
  - `time_sync_uncertain` must block restricted-live
- Order recovery architecture
  - lookup by `client_order_id` contract exists
  - lookup by `exchange_order_id` contract exists
  - unknown execution recovery plan exists

## Observability Checklist

Before restricted-live testing:

- report-only JSONL records are being written consistently
- paper-mode state transition records are being written consistently
- runtime cycle summary records are being written consistently
- latest runtime health/status snapshot is being updated consistently
- operator-facing markdown status report is being refreshed consistently
- cycle-level alerts are visible to operators
- feature presence and optional-source absence are visible in persisted records
- generated intents are visible before any future exchange submission path
- Binance reconciliation outputs and recovery actions are inspectable
- latest reconciliation state snapshot is inspectable when restart-safe persistence is configured
- reconciliation snapshots include last trigger reason, automatic/manual state, convergence state, and manual-attention timing
- Binance clock status is inspectable
- restricted-live mutation-blocked reasons are inspectable in persisted cycle results
- degraded-but-non-fatal states are explicit rather than implied
- restricted-live fail-closed behavior for quality blockers is verified in tests
- restricted-live rehearsal scenario artifacts are available for operator review when generated
- restart/crash-recovery scenario artifacts are available for operator review when generated
- reconciliation state snapshots are inspectable before restart and after resumed rehearsal

## Rollback Criteria

Restricted-live testing must be halted immediately if any of the following occur:

- private-stream gaps appear without a defined operator response
- unknown execution ids appear and recovery confidence is not restored
- clock skew exceeds configured tolerance repeatedly
- persisted cycle artifacts are missing or incomplete
- portfolio state cannot be explained from persisted decisions and simulated/live-facing state transitions
- documentation and running behavior diverge materially

Rollback action:

1. Stop restricted-live testing.
2. Return to `paper` or `report_only`.
3. Preserve artifacts for diagnosis.
4. Document the blocking issue before any retry.
5. Preserve the reconciliation state snapshot used for restart recovery review.

## Restart And Crash-Recovery Rehearsal

Restricted-live is not considered explainable enough unless restart and interruption behavior has been rehearsed.

Required restart/crash-recovery scenarios:

- mid-run interruption with persisted unresolved reconciliation state
- restart with unresolved reconciliation state restored from persistence
- restart with degraded private-stream state still visible to operators
- restart with blocked portfolio-mutation state that remains blocked safely
- restart with persisted private-stream gap state that resumes or re-escalates recovery explicitly

Operator review for these rehearsals must inspect:

- `restricted_live_scenarios/<scenario_name>/scenario_summary.json`
- `restricted_live_scenarios/<scenario_name>/scenario_summary.md`
- `restricted_live_scenarios/<scenario_name>/reconciliation_state.json` when present

Failure-injection review should additionally inspect:

- `reports/failure_injection/<scenario_id>/scenario_summary.json`
- `reports/failure_injection/<scenario_id>/scenario_summary.md`
- `reports/failure_injection/<scenario_id>/scenario_cycles.jsonl`

Required failure-injection scenarios:

- private stream disconnect
- listen-key expiration
- websocket reconnect storms
- delayed private events
- missing order events
- duplicated fill events

Required interpretation:

- expiry-driven recovery is not enough to authorize portfolio mutation by itself
- after `listen_key_expiration` or equivalent stream invalidation, mutation must remain blocked until later canonical private confirmation or another explicitly documented safe confirmation condition exists

Blocked mutation after restart is a valid rehearsal success path when the scenario expected fail-closed behavior.

## Release Gate Table

- `contracts`
  - required: yes
  - purpose: venue-neutral invariants and schema stability
- `features`
  - required: yes
  - purpose: shared feature producer correctness and partial tolerance
- `strategies`
  - required: yes
  - purpose: pure logic output shape and venue neutrality
- `runtime_mode`
  - required: yes
  - purpose: report-only, paper, and restricted-live separation
- `report_only_integration`
  - required: yes
  - purpose: first working vertical slice remains green
- `paper_integration`
  - required: yes
  - purpose: continuity and portfolio integrity across repeated cycles
- `observability`
  - required: yes
  - purpose: operator visibility and degraded-mode reporting
- `scenario_regression`
  - required: yes
  - purpose: operator-readable portfolio/risk/degradation/recovery behavior protection
- `exchanges`
  - required: yes
  - purpose: Binance scaffolding and boundary contracts remain explicit
- `reconciliation`
  - required: yes
  - purpose: unknown execution and recovery visibility remain intact

## Open-Gap Disclosure Template

Use this template before any restricted-live rollout decision:

```text
Restricted-Live Review
Date:
Operator:
Commit/Workspace State:

Ready Areas:
- 

Known Gaps:
- 

Binance Private Stream Status:
- 

Reconciliation Status:
- 

Clock Sync Status:
- 

Unknown Execution Recovery Status:
- 

Persisted Artifacts Verified:
- 

Rollback Trigger Review:
- 

Decision:
- allow restricted-live test
- block restricted-live test
```
