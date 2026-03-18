# Production Gate Pre-Audit

## Purpose

This document defines the exact minimum conditions still required before production promotion can even be considered for `runtime2`.

It is intentionally conservative.

- It is not a production-readiness declaration.
- It does not replace [`docs/binance_cutover_readiness.md`](/home/terratunes/code/trading/runtime2/docs/binance_cutover_readiness.md) or [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md).
- It focuses on the shortest blocking path from current rehearsal capability to a production-candidate review.

## Current Status

### Launcher

- status: strong
- config-driven launcher is authoritative
- shell scripts are thin wrappers only
- mode routing reaches the real runners

### Dry-Run Workflow

- status: strong
- dry-run uses the real launcher path
- run-specific directories and summaries are persisted
- operator-readable markdown and machine-readable JSON outputs exist

### Restricted-Live Rehearsal

- status: strong for rehearsal, not for production
- fail-closed behavior is explicit
- blocked mutation is treated as a valid safety outcome
- restart/crash-recovery rehearsal scenarios exist
- deterministic failure-injection and reconciliation-disruption scenarios now exist
- expiry-driven recovery now remains blocked until later canonical private confirmation

### Private Transport Durability

- status: partially ready
- real Binance private transport exists inside the adapter boundary
- lifecycle, reconnect, refresh, expiry, and heartbeat visibility exist
- deterministic soak and restricted-live soak workflows exist
- soak campaign tooling exists for `6h`, `12h`, and `24h` sessions
- as of the latest evidence review, no checked-in `reports/soak_sessions/<session_id>/` artifacts were present for completed real `6h`, `12h`, or `24h` sessions
- long-running real-world durability is still not proven enough for production consideration

### Reconciliation Automation

- status: partially ready
- gap detection, automatic signed status-query recovery, replay-safe persistence, and restart-safe continuation exist
- convergence is explicit and operator-visible
- deterministic reconciliation-disruption scenarios now cover:
  - private event loss
  - delayed status query
  - duplicated execution reports
  - partial fill reorder
- long-running automatic convergence across real private-stream disruption is still not proven enough

### Clock Sync Hardening

- status: partially ready
- offset sampling, recalibration, and uncertain-state exposure exist
- operator visibility exists
- simulated drift coverage now includes:
  - `+500ms` drift
  - `-500ms` drift
  - sudden exchange time jump
  - local NTP skew
- restricted-live fail-closed behavior is covered when clock uncertainty persists
- production-grade continuous wiring and operational tolerance enforcement remain incomplete

### Live Portfolio Mutation Safeguards

- status: partially ready
- canonical Binance translation exists
- mandatory safeguard gate exists
- ambiguous, unreconciled, malformed, or snapshot-mismatched state blocks mutation
- unrestricted live execution and mutation are still not production-ready

### Exchange Health Visibility

- status: strong for operator visibility
- unified exchange health is now persisted in the main observability path for Binance-facing runs
- private stream, reconciliation, clock sync, and signed status-query state are visible in `runtime_health.json` and `runtime_status.md`
- visibility is strong, but it does not remove underlying transport/runtime blockers

## What Is Already Strong

- launcher and shell-wrapper discipline
- dry-run and rehearsal operator workflow
- report-only and paper vertical slices
- restricted-live fail-closed posture
- canonical Binance private payload translation boundary
- mandatory live portfolio safeguard gate
- replay-safe reconciliation persistence and restart visibility
- shared exchange health reporting
- operator-facing artifacts, summaries, and debugging guidance
- deterministic disruption evidence for reconciliation and clock drift behavior

## Exact Remaining Blockers

1. Long-running real Binance private transport durability is not yet proven.
   - Real authenticated transport exists.
   - The current workspace evidence set does not include reviewed `6h`, `12h`, or `24h` restricted-live soak outputs.
   - Production consideration still needs sustained evidence for reconnect churn, listen-key refresh/expiry behavior, heartbeat watchdog behavior, and session continuity under real exchange conditions.

2. Real-world reconciliation convergence is not yet proven enough.
   - Automatic gap-to-REST recovery exists.
   - Production consideration still needs evidence that repeated recovery, restart continuation, and manual-attention escalation behave correctly under real private-stream gaps and delayed status truth.

3. Clock sync is not yet production-grade operationally.
   - Hardening exists.
   - Production consideration still needs continuous exchange-health wiring, clear operational thresholds, and proven behavior under drift and recalibration failure.

4. Unrestricted live execution is still blocked.
   - The system can prepare and gate live-facing mutation safely.
   - Production consideration still requires a production-safe end-to-end live submission, translation, reconciliation, and mutation path with no bypass around the safeguard layer.

5. Production gate criteria are not yet satisfied by evidence, only by scaffolding.
   - Rehearsal artifacts are strong.
   - The soak campaign and thresholds are documented, but the reviewed workspace does not yet contain the resulting long-running session artifacts.
   - Production consideration still requires real long-running soak evidence and clear pass/fail thresholds, not just contract completeness.

## Minimum Conditions Before Production Consideration

The following are the minimum remaining conditions. If any one of them is missing, production promotion should not be considered.

1. Real restricted-live soak evidence under Binance must complete successfully.
   - extended-session private transport stays explainable
   - reconnect and listen-key refresh behavior stays within defined thresholds
   - heartbeat overdue events do not accumulate into unexplained degradation
   - operator-facing soak artifacts remain complete
   - all `6h`, `12h`, and `24h` sessions meet the documented pass criteria

2. Automatic reconciliation convergence must prove stable under real disruption.
   - private-stream gaps trigger automatic recovery explicitly
   - signed status-query recovery converges or escalates explicitly
   - restart continuation preserves unresolved state safely
   - no silent recovery or silent acceptance occurs

3. Clock sync must become an enforced operational gate, not only a component contract.
   - current status is continuously visible
   - recalibration failure is surfaced immediately
   - signed request safety is blocked on uncertain time state
   - thresholds are documented and operator-usable

4. Live mutation safety must remain impossible to bypass in the real restricted-live path.
   - canonical translation remains mandatory
   - safeguard gate remains mandatory
   - ambiguous and unreconciled states remain blocked
   - operator-visible blocked-mutation reasons remain persisted
   - listen-key expiry or equivalent private-stream invalidation must not allow premature mutation

5. Production consideration must be backed by one explicit evidence review.
   - latest restricted-live soak artifacts reviewed
   - latest exchange-health artifacts reviewed
   - latest reconciliation state and recovery artifacts reviewed
   - latest blocked-mutation and restart-recovery scenarios reviewed
   - no open contradiction between docs, artifacts, and observed runtime behavior

## Recommendation

Recommendation: `continue rehearsal`

Current evidence verdict: `hold for production reconsideration until real soak artifacts exist and are reviewed`

Meaning:

- continue `report_only`
- continue `paper`
- continue restricted-live rehearsal only under current fail-closed gates
- do not open a production promotion decision yet

## Why This Is Not A Hold

- the runtime is materially useful for continued gated rehearsal
- operator visibility is strong enough to support more evidence gathering
- fail-closed safety posture is improving rather than regressing

## Why This Is Not A Promote Candidate

- transport durability is not yet proven enough
- reconciliation convergence is not yet proven enough under real disruption
- clock-sync enforcement is not yet strong enough operationally
- unrestricted live execution remains blocked

## Exact Next Actions

1. Run and review the real `6h` soak session and confirm it passes the documented hard thresholds.
2. Run and review the real `12h` soak session and confirm it passes the documented hard thresholds.
3. Run and review the real `24h` soak session and confirm it passes the documented hard thresholds.
4. Review automatic reconciliation convergence behavior from those soak artifacts, including restart continuation.
5. Confirm expiry-driven invalidation remains blocked until later canonical private confirmation in reviewed restricted-live evidence.
6. Tighten clock-sync operational thresholds and verify they surface through the shared exchange-health path during rehearsal.
7. Keep production promotion blocked until the live safeguard path remains mandatory and explainable under real transport conditions.

## Latest Soak Evidence Review

- review date: `2026-03-14`
- reviewed path: `reports/soak_sessions/`
- reviewed session directories found:
  - `reports/soak_sessions/binance-testnet-soak-2h-night/`
  - several shorter validation/debug runs
- operator notes: none found alongside the reviewed soak artifacts

Implication:

- the soak execution package is now producing real reviewable artifacts
- a reviewed `2h` Spot testnet soak met structural pass thresholds:
  - `stop_reason == completed`
  - `aborted == false`
  - `final_exchange_health_state == healthy`
  - `refresh_failures == 0`
  - artifact set complete
- that `2h` run remained largely idle from a private-truth perspective:
  - no reconnects
  - no heartbeat overdue events
  - no reconciliation recovery attempts
  - no blocked mutations
  - repeated `no private payloads available for restricted-live mutation gate` alerts
- production promotion remains blocked because the reviewed `2h` evidence strengthens rehearsal confidence only for idle-session durability, not for active private-event durability or longer-run proof
- a reviewed `6h` Spot testnet soak also met structural pass thresholds:
  - `stop_reason == completed`
  - `aborted == false`
  - `final_exchange_health_state == healthy`
  - `completed_cycles == 545`
  - `refresh_attempts == 6`
  - `refresh_failures == 0`
  - `reconnect_count == 0`
  - `heartbeat_overdue_events == 0`
- that `6h` run remained idle-stream evidence only:
  - no private payload-driven mutation attempts
  - no reconciliation recovery attempts
  - repeated `no private payloads available for restricted-live mutation gate` alerts across all cycles
- the `6h` review strengthens confidence in bounded-duration idle-session continuity and subscription renewal, but it still does not materially improve production confidence for active-event durability

## Latest 6h Soak Review

- review date: `2026-03-14`
- reviewed path: `reports/soak_sessions/binance-testnet-soak-6h/`
- artifact presence:
  - `soak_summary.json`: present
  - `soak_summary.md`: present
  - `health_transitions.jsonl`: present
  - `reconnect_events.jsonl`: present
  - `listen_key_refresh.jsonl`: present
  - `reconciliation_events.jsonl`: present
- operator notes reviewed: none found

Assessment:

- the reviewed `6h` run passes the documented structural thresholds
- the current verdict for this `6h` session is `PASS WITH GAPS`
- the main gap is evidence shape, not an observed failure:
  - the run was idle-stream only
  - it did not exercise active private-event handling
  - it did not exercise reconciliation recovery
- progression to the next longer soak step is reasonable for further rehearsal evidence accumulation, but not as a production signal

## Latest 12h Soak Review

- review date: `2026-03-14`
- requested evidence: first real `12h` restricted-live soak session
- expected artifact root: `reports/soak_sessions/<12h_session_id>/`
- actual result: no `12h` session directory or soak evidence files were present in the workspace
- reviewed file search result:
  - no `soak_summary.json`
  - no `soak_summary.md`
  - no `health_transitions.jsonl`
  - no `reconnect_events.jsonl`
  - no `listen_key_refresh.jsonl`
  - no `reconciliation_events.jsonl`
- operator notes reviewed: none found

Assessment:

- the `12h` run cannot be rated as passed because the required evidence is absent
- comparison against the prior `6h` session is not possible because no reviewed `6h` artifacts are present either
- the current verdict for the first `12h` session is `FAIL` for evidence review purposes
- progression to `24h` should remain blocked until both `6h` and `12h` artifacts exist and pass the documented hard thresholds

## Latest 24h Soak Review

- review date: `2026-03-14`
- requested evidence: first real `24h` restricted-live soak session
- expected artifact root: `reports/soak_sessions/<24h_session_id>/`
- actual result: no `24h` session directory or soak evidence files were present in the workspace
- reviewed file search result:
  - no `soak_summary.json`
  - no `soak_summary.md`
  - no `health_transitions.jsonl`
  - no `reconnect_events.jsonl`
  - no `listen_key_refresh.jsonl`
  - no `reconciliation_events.jsonl`
- operator notes reviewed: none found

Assessment:

- the `24h` run cannot be rated as passed because the required evidence is absent
- no trend comparison across `6h`, `12h`, and `24h` is possible because none of the reviewed soak artifact sets are present
- the current verdict for the first `24h` session is `FAIL` for evidence review purposes
- production confidence should not improve from the current soak evidence state

Operational conclusion:

- continue rehearsal
- do not treat the soak workflow as operational proof until the real `6h`, `12h`, and `24h` artifact sets exist and are reviewed successfully
