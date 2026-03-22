# Binance Cutover Readiness

This document is the operator-facing Binance cutover package for `runtime2`.

It is intentionally conservative. It does not declare Binance production-ready trading.

## Purpose

Use this document before any promotion decision beyond `report_only`, `paper`, or restricted-live rehearsal.

Read together with:

- [`docs/exchange_integration_notes.md`](/home/terratunes/code/trading/runtime2/docs/exchange_integration_notes.md)
- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/binance_known_gaps.md`](/home/terratunes/code/trading/runtime2/docs/binance_known_gaps.md)
- [`docs/cutover_checklist.md`](/home/terratunes/code/trading/runtime2/docs/cutover_checklist.md)

## Current Readiness Summary

## Binance Live Checklist v1

This checklist is for the next bounded operator / bounded micro-live run only.

- start from a fresh shell and load credentials through hidden prompt entry
- keep current-shell export behavior for the existing wrappers, but do not use inline credential-bearing commands
- avoid shared terminal capture during credential entry and unset credentials after the run
- keep the current broader `r5` baseline as the authoritative proof set
- keep the same runtime/session lineage model used in `r5`
- keep stale-output fail-if-exists behavior unchanged
- keep restricted-live mutation safeguards unchanged
- treat `executionRules` and `referencePrice` additions as watchpoints, not last-minute integration work
- treat `expiryReason` / `eR` as tolerated optional metadata unless reviewed evidence proves a new operational need
- keep the subscribe-based Spot WebSocket API UDS bootstrap path as the only accepted private bootstrap assumption
- treat `permissionSets`, `amendAllowed`, `quoteOrderQtyMarketAllowed`, STP-related parsing expansion, `MAX_ASSET`, and `myFilters` as gap-awareness items, not bounded-run redesign work
- keep unknown execution handling fail-closed and operator-visible
- watch reconnect / heartbeat churn, request-weight behavior, order-count pressure, and timeout uncertainty explicitly during the run
- keep Demo Mode out of this stage; it is a later test-ladder step

## Known Gaps / Not In Scope For Bounded Run

The following are intentionally not in scope for the next bounded run:

- broader Binance live-hardening refactors
- parser/model expansion for `executionRules` or `referencePrice`
- surfacing `expiryReason` / `eR` as a new operator-facing lifecycle dimension
- new handling for `permissionSets`, `amendAllowed`, `quoteOrderQtyMarketAllowed`, STP-specific metadata, `MAX_ASSET`, or `myFilters`
- redesign of unknown execution handling
- reconnect or heartbeat subsystem redesign
- new rate-limit / order-count policy automation
- Demo Mode execution

These remain future-hardening items unless the bounded run shows a concrete regression that forces narrower remediation.

### Market Data

- Public market-data normalization exists.
- Closed-bar detection exists and is the correctness focus.
- Public websocket degradation states are explicit.
- Real network transport loop and automatic failover transport are still incomplete.

### Private Stream

- Private-stream lifecycle contracts exist:
  - auth/init
  - subscribe
  - reconnect
  - session rollover
  - graceful shutdown
- Normalized event family boundaries exist:
  - order/execution updates
  - account updates
  - stream status events
- Real authenticated WebSocket API user-data subscription transport exists inside the adapter boundary.
- Canonical private-payload translation into `OrderState`, `FillEvent`, and `AccountSnapshot` exists.
- Restricted-live rehearsal scenarios now exercise this path end-to-end.
- A deterministic soak and failure-injection rehearsal path now persists reconnect, refresh, heartbeat, and authoritative/degraded state transitions.
- Failure-injection coverage now includes:
  - private stream disconnect
  - listen-key expiration
  - websocket reconnect storms
  - delayed private events
  - missing order events
  - duplicated fill events
- Endpoint-profile validation now fails closed when REST and websocket hosts do not match the configured Binance environment.
- Watchdog-based heartbeat overdue and subscription-expiry degradation is now explicit and operator-visible.
- Expiry-driven REST recovery alone is no longer sufficient for portfolio mutation after stream invalidation.
- `listen_key_expiration` now remains blocked until later canonical private confirmation arrives.
- The old private bootstrap failure was caused by REST `listenKey` acquisition against a deprecated Spot user-data bootstrap path that now returns HTTP `410 Gone`.
- The adapter now bootstraps private truth with `userDataStream.subscribe.signature` on the Spot WebSocket API, so restricted-live rehearsal no longer depends on the deprecated listenKey acquisition flow.
- Production-proven reconnect scheduling, heartbeat hardening, and long-running runtime operation remain incomplete.

### Reconciliation

- Unknown execution and recovery workflow states are explicit.
- Recovery logging is append-only and inspectable.
- Lookup and recovery architecture exists by `client_order_id` and `exchange_order_id`.
- Signed REST order-status lookup transport exists inside the adapter boundary.
- Signed lookup now has request-weight-aware throttling and more defensive schema/error parsing.
- Transport-backed reconciliation orchestration exists for rehearsal-stage recovery flow.
- Restricted-live rehearsal scenarios now cover both recovered and blocked-mutation outcomes.
- Deterministic disruption scenarios now cover:
  - private event loss
  - delayed status query
  - duplicated execution reports
  - partial fill reorder
- Replay-safe persistent reconciliation exists, but full real-world automatic convergence remains incomplete.

### Clock Sync

- Server-time sampling and offset evaluation contracts exist.
- Time-sync uncertainty is a first-class quality state.
- Tests now cover:
  - `+500ms` drift
  - `-500ms` drift
  - sudden exchange time jump
  - local NTP skew
- Restricted-live fail-closed behavior is covered when uncertainty persists.
- Live clock-source integration and hard operational tolerance enforcement remain incomplete.

### Order Lifecycle

- Shared order lifecycle states are explicit:
  - `NEW`
  - `ACKNOWLEDGED`
  - `PARTIALLY_FILLED`
  - `FILLED`
  - `CANCELED`
  - `EXPIRED`
  - `REJECTED`
  - `RECOVERING`
  - `UNRECONCILED`
- Paper and reconciliation share the lifecycle model.
- Canonical Binance private payload translation now maps into internal lifecycle-bearing models.
- Restricted-live now uses the mandatory live safeguard gate before any portfolio mutation attempt.
- Production-safe unrestricted live convergence remains incomplete.

### Launcher And Runtime Path

- The config-driven launcher path is in place and authoritative.
- Shell scripts remain thin wrappers over `scripts/runtime2_rehearsal.py`.
- Mode routing reaches the actual report-only, paper, and restricted-live rehearsal runners.
- Runtime observability now persists one unified exchange health surface automatically for Binance-facing runtime paths.
- That surface summarizes private stream, reconciliation, clock sync, and signed status-query state in both `runtime_health.json` and `runtime_status.md`.
- If no exchange-health provider is configured, Binance-facing paths should still persist explicit `unknown` component states rather than omitting the exchange-health section.
- This is launcher readiness for rehearsal operation, not proof of production-safe Binance trading.

### Restricted-Live Soak Workflow

- A long-running restricted-live soak workflow now exists on top of the restricted-live runner path.
- It persists exchange-health transitions, reconnect counts, subscription-renewal results, heartbeat-overdue events, reconciliation recovery attempts, and blocked mutation events.
- It now also persists dedicated evidence files for reconnects, private-stream renewal activity, and reconciliation recovery records.
- The current validation workflow should use the dedicated Spot testnet rehearsal config at [`configs/runtime2_restricted_live_testnet.toml`](/home/terratunes/code/trading/runtime2/configs/runtime2_restricted_live_testnet.toml) with Spot testnet credentials, not the mainnet-oriented restricted-live config.
- A default campaign layer now exists for `6h`, `12h`, and `24h` soak sessions under `reports/soak_sessions/<session_id>/`.
- For single-session real evidence runs, operators should also set `--output-subdir soak_sessions` so artifacts land under the same `reports/soak_sessions/<session_id>/` review path.
- It has explicit abort criteria for fatal exchange health, manual-attention reconciliation, and repeated blocked mutation.
- The campaign tooling exists, but production promotion still requires reviewed real-session evidence from those runs.
- As of the latest workspace evidence review, no completed `reports/soak_sessions/<session_id>/` directories were present for real `6h`, `12h`, or `24h` sessions.
- It is durability evidence for rehearsal only, not production promotion proof.

Minimum operator success thresholds for each real soak session:

- exit code `0`
- `soak_summary.json.stop_reason == "completed"`
- `soak_summary.json.aborted == false`
- all expected artifact files present:
  - `health_transitions.jsonl`
  - `reconnect_events.jsonl`
  - `listen_key_refresh.jsonl`
  - `reconciliation_events.jsonl`
  - `soak_summary.json`
  - `soak_summary.md`
- no refresh failure
- no manual-attention escalation
- no fatal exchange-health stop
- if recovery attempts occurred, `reconciliation_recovery_success_rate == 1.0`

Automatic failure conditions for cutover evidence:

- any non-zero soak exit code
- `stop_reason` of `fatal_exchange_health`
- `stop_reason` of `manual_attention`
- `stop_reason` of `max_blocked_mutations`
- missing artifact files
- unexplained blocked mutation
- expiry-driven mutation observed without later canonical private confirmation

### Dry-Run Workflow

- A run-specific dry-run workflow exists on top of the launcher path.
- Dry-run outputs include preflight summary, launch summary, runtime artifacts, and final run summary.
- Report-only and paper dry-runs are operator-usable now.
- Restricted-live dry-run remains gated and should be treated as rehearsal only.

## Blocker Table

| Area | Status | Operator Meaning |
| --- | --- | --- |
| Public market-data normalization | ready | Closed-bar parsing and runtime-facing normalization exist. |
| Public websocket transport lifecycle | partially ready | Health states exist, but real transport loop and failover transport remain incomplete. |
| Private stream contract model | partially ready | Lifecycle, real transport boundary, canonical translation, and rehearsal verification exist, but production-proven runtime operation remains incomplete. |
| Reconciliation workflow model | partially ready | Recovery states, signed lookup transport, replay-safe persistence, disruption rehearsal, and transport-backed orchestration exist, but real-world automatic convergence remains incomplete. |
| Clock-sync contract | partially ready | Offset evaluation and drift rehearsal exist, but live operational hardening is incomplete. |
| Shared order lifecycle model | ready | Canonical lifecycle model exists and is reusable across paper and reconciliation. |
| Binance lifecycle translation | partially ready | Canonical private-payload translation exists with more defensive parsing, but long-running production operation remains incomplete. |
| Launcher/runtime path | ready | Config-driven launcher and runner routing are operational for rehearsal use. |
| Shared exchange health surface | partially ready | Operator-readable rollup is persisted automatically for Binance-facing runtime paths, but the provider-backed content is still only as strong as the underlying rehearsal-grade transport hardening. |
| Dry-run workflow | ready | Operator dry-run path exists and writes auditable run-specific artifacts. |
| Restricted-live soak workflow | partially ready | Long-running rehearsal workflow and artifacts exist, but real-world Binance durability is still not production-proven. |
| Signed order submission | blocked | No unrestricted production order submission path should be enabled. |
| Portfolio-safe live fill translation | partially ready | Canonical translation, safeguard layers, and restricted-live mutation gating exist, but unrestricted live trading remains incomplete. |
| Production cutover decision | blocked | Open Binance transport and recovery gaps remain. |

## Operator Verification Steps

### Credentials

1. Confirm Binance credentials are present only for restricted-live rehearsal workflows.
2. Confirm rehearsal scripts still keep order submission disabled.
3. Confirm credential use is limited to gated preflight and not treated as proof of live readiness.

### Launcher Invocation

1. Confirm operators use `scripts/runtime2_rehearsal.py` directly or the thin shell wrappers only.
2. Confirm the selected mode matches the config file mode.
3. Confirm `--confirm-rehearsal-only` is present for any launcher-backed run.
4. Confirm restricted-live rehearsal also includes `--allow-restricted-live-rehearsal` and `--confirm-no-order-submission`.

### Dry-Run Output Review

1. Confirm the dry-run wrote a dedicated `reports/dry_runs/<run_id>/` directory.
2. Confirm `latest_launch_summary.json` exists and names the expected runner.
3. Confirm `run_summary.json` and `run_summary.md` exist and agree on status.
4. Confirm `runtime_cycles.jsonl`, `runtime_cycle_summaries.jsonl`, `runtime_health.json`, and `runtime_status.md` exist.
5. Confirm `runtime_health.json.exchange_health` is present when exchange-facing rehearsal wiring is expected.
5. Confirm paper dry-runs also wrote `paper_state_transitions.jsonl`.

### Private Stream Health

1. Confirm lifecycle state visibility exists for init, subscribe, reconnect, rollover, and terminate paths.
2. Confirm stream termination or invalidation would surface as an operator-visible alert.
3. Confirm canonical private-payload translation results are visible and not malformed.
4. Confirm soak rehearsal artifacts exist when transport durability is under review:
   - `health_transitions.jsonl`
   - `reconnect_events.jsonl`
   - `listen_key_refresh.jsonl`
   - `reconciliation_events.jsonl`
   - `soak_summary.json`
   - `soak_summary.md`
5. Confirm heartbeat-overdue or subscription-expiry degradation is visible before any restart decision.
6. Confirm public market-data continuity is not being mistaken for private order/account truth.
7. When running the restricted-live soak, confirm `health_transitions.jsonl` shows explainable reconnect, refresh, and authoritative/degraded changes.

### Reconciliation Visibility

1. Confirm unknown execution states are inspectable.
2. Confirm recovery attempts and outcomes are persisted append-only.
3. Confirm the latest signed status-query lookup succeeded or failed explicitly.
4. Confirm request-weight blocking appears explicitly rather than degrading into opaque lookup failures.
5. Confirm endpoint-profile isolation prevents accidental cross-environment control-plane requests.
6. Confirm unresolved recovery escalates to manual attention rather than silent acceptance.
7. Confirm restricted-live rehearsal scenario output distinguishes safe mutation from intentionally blocked mutation.
8. Confirm the unified exchange health rollup reports reconciliation as `healthy`, `degraded`, or `fatal` in line with the latest cursor snapshot and workflow state.
9. When running the restricted-live soak, confirm `soak_summary.json` includes recovery attempts, recovery success rate, and blocked mutation counts.
10. If the provider is absent for a Binance-facing run, confirm the persisted rollup still shows explicit `unknown` component states instead of a missing exchange-health section.

### Degraded Mode Behavior

1. Confirm `missing_data`, `stale_data`, `version_mismatch`, `incomplete_bar`, and `time_sync_uncertain` stay explicit.
2. Confirm degraded-but-allowed behavior remains visible in `report_only` and `paper`.
3. Confirm restricted-live still fails closed on its defined blockers.

## Cutover Decision Guidance

- `ready` in this document means the contract or observability boundary is usable.
- `partially ready` means the architecture exists but the transport or hardening is incomplete.
- `blocked` means no promotion decision should claim Binance production readiness.

Current recommendation:

- allow `report_only`
- allow `paper`
- allow restricted-live rehearsal only under existing gates
- block any production promotion decision

Updated recommendation:

- restricted-live rehearsal confidence is stronger than before
- production promotion remains blocked
- next review should not reopen promotion unless:
  - real long-running soak evidence is collected and reviewed
  - expiry-driven restricted-live mutation remains blocked until later canonical private confirmation across reviewed evidence
  - all 6h / 12h / 24h soak sessions meet the documented minimum success thresholds

For the next bounded operator / bounded micro-live run, add these operator watchpoints:

- monitor for any new Spot/Testnet payload fields that appear in persisted artifacts but are not yet consumed
- monitor for any reconnect / heartbeat churn that stops being explainable
- monitor for repeated request-weight, order-count, or timeout signals
- monitor for any unknown execution state that does not converge automatically

## Latest Soak Evidence Review

- review date: `2026-03-14`
- reviewed artifact root: `reports/soak_sessions/`
- reviewed result:
  - one real `2h` Spot testnet soak session present at `reports/soak_sessions/binance-testnet-soak-2h-night/`
  - no reviewed `6h`, `12h`, or `24h` soak session directories present yet
- operator notes reviewed: none found

Operational interpretation:

- the soak workflow is not just ready to run; it is producing reviewable artifacts under the intended path
- the reviewed `2h` Spot testnet soak passed structural thresholds:
  - `stop_reason == completed`
  - `aborted == false`
  - `final_exchange_health_state == healthy`
  - `refresh_attempts == 2`
  - `refresh_failures == 0`
  - `reconnect_count == 0`
  - `heartbeat_overdue_events == 0`
- the same `2h` soak was largely idle and did not exercise active private-event handling:
  - no private payload-driven mutation attempts
  - no reconciliation recovery attempts
  - repeated `no private payloads available for restricted-live mutation gate` alerts across all cycles
- this improves rehearsal confidence for idle-session continuity and subscription renewal, but it does not materially improve production confidence for active-event durability
- a reviewed `6h` Spot testnet soak also passed structural thresholds:
  - `stop_reason == completed`
  - `aborted == false`
  - `final_exchange_health_state == healthy`
  - `completed_cycles == 545`
  - `refresh_attempts == 6`
  - `refresh_failures == 0`
  - `reconnect_count == 0`
  - `heartbeat_overdue_events == 0`
- the same `6h` soak remained idle-stream evidence only:
  - no private payload-driven mutation attempts
  - no reconciliation recovery attempts
  - repeated `no private payloads available for restricted-live mutation gate` alerts across all cycles
- this strengthens rehearsal confidence for longer idle-session continuity and renewal behavior, but still does not prove active private-event durability
- Binance should remain in restricted-live rehearsal only, and the next longer soak step is reasonable only as further rehearsal evidence accumulation, not as a promotion signal

## Latest 6h Session Review

- review date: `2026-03-14`
- expected session evidence: `reports/soak_sessions/<6h_session_id>/`
- actual reviewed result: no `6h` session artifacts present in the workspace
- missing required files:
  - `soak_summary.json`
  - `soak_summary.md`
  - `health_transitions.jsonl`
  - `reconnect_events.jsonl`
  - `listen_key_refresh.jsonl`
  - `reconciliation_events.jsonl`
- operator notes reviewed: none found

Cutover interpretation:

- the first real `6h` soak cannot be treated as passed
- the absence of artifacts is itself a hard evidence failure against the documented soak thresholds
- do not proceed to `12h` until the `6h` run is re-executed and its artifacts are reviewed successfully

## Latest 12h Session Review

- review date: `2026-03-14`
- expected session evidence: `reports/soak_sessions/<12h_session_id>/`
- actual reviewed result: no `12h` session artifacts present in the workspace
- missing required files:
  - `soak_summary.json`
  - `soak_summary.md`
  - `health_transitions.jsonl`
  - `reconnect_events.jsonl`
  - `listen_key_refresh.jsonl`
  - `reconciliation_events.jsonl`
- operator notes reviewed: none found

Cutover interpretation:

- the first real `12h` soak cannot be treated as passed
- comparison to the prior `6h` session is not possible because no reviewed `6h` session artifacts are present either
- the absence of `12h` artifacts is itself a hard evidence failure against the documented soak thresholds
- do not proceed to `24h` until the `6h` and `12h` runs are re-executed and their artifacts are reviewed successfully

## Latest 24h Session Review

- review date: `2026-03-14`
- expected session evidence: `reports/soak_sessions/<24h_session_id>/`
- actual reviewed result: no `24h` session artifacts present in the workspace
- missing required files:
  - `soak_summary.json`
  - `soak_summary.md`
  - `health_transitions.jsonl`
  - `reconnect_events.jsonl`
  - `listen_key_refresh.jsonl`
  - `reconciliation_events.jsonl`
- operator notes reviewed: none found

Cutover interpretation:

- the first real `24h` soak cannot be treated as passed
- no `6h` / `12h` / `24h` durability trend can be established because none of the reviewed soak artifact sets are present
- the absence of `24h` artifacts is itself a hard evidence failure against the documented soak thresholds
- production confidence should not increase from the current soak evidence state
