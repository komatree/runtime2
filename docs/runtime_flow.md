# Runtime Flow

## Runtime Sequence

0. Config-driven launcher bootstrap
   - owner: `scripts/runtime2_rehearsal.py` and `app/config/rehearsal.py`
   - input: explicit rehearsal config plus data-file paths
   - output: validated mode selection, constructed `RuntimeContext`, and loaded market inputs
   - failure points: config mode mismatch, missing kline files, invalid config schema, fail-closed rehearsal flag violations
1. Closed bar trigger
   - owner: `datafeeds` and `runtime`
   - input: normalized `BarSlice`
   - failure points: last candle is not closed, overlapping windows, stale slice
   - public WS path: Binance public kline messages must be normalized into canonical closed candles before they can trigger this step
2. Normalized candle slice acceptance
   - owner: `runtime.bar_close_validator`
   - input: canonical `BarSlice`
   - failure points: invalid slice metadata or inconsistent close boundary
   - real-data path: Binance kline inputs must be converted into closed execution and context candle slices before this step
   - explicit quality state: `incomplete_bar`
3. Feature snapshot build
   - owner: `features`
   - input: validated `BarSlice`
   - output: canonical `FeatureSnapshot`
   - failure points: incomplete bar history, invalid feature values, stale auxiliary inputs
   - real-data path: 4h execution bars may be enriched with 1d context candle features
   - separation:
     - candle service computes local candle-derived features
     - index suite service reads precomputed snapshots only
     - index suite repository/provider resolves the latest valid snapshot by instrument/date/version
     - missing, stale, or version-mismatched Index Suite snapshots are tolerated and surfaced diagnostically
     - stablecoin service maps report-oriented snapshots only
     - strategies and risk consume the unified snapshot and do not compute these upstream features
   - explicit quality states:
     - `missing_data`
     - `stale_data`
     - `version_mismatch`
     - `time_sync_uncertain`
4. Strategy evaluation
   - owner: `strategies`
   - input: `DecisionContext`
   - output: venue-neutral `SignalDecision` values
   - failure points: missing rationale, incomplete feature snapshot, inconsistent portfolio view
5. Risk evaluation
   - owner: `risk`
   - input: `SignalDecision`, `PortfolioState`, optional `VenueProfile`
   - output: `RiskDecision`
   - failure points: exposure breach, stale portfolio state, venue capability mismatch
6. Execution intent generation
  - owner: `execution` for future full implementation, with report-only placeholder builder active now
  - input: allowed or adjusted `RiskDecision`
  - output: `ExecutionIntent`
  - failure points: unsupported order type, missing size, missing target venue
  - report-only behavior: intents are generated for auditability but never submitted
   - paper behavior: intents are handed to a local simulator, not to an exchange adapter
7. Persistence and reporting
  - owner: `storage` and `monitoring`
  - input: cycle artifacts and summary
  - output: persisted `RuntimeCycleResult` and operator-visible reports
  - failure points: storage write failure, report sink unavailable
  - current implementation: JSONL report record including feature snapshot, decision-context summary, and decision-time Index Suite context
8. Paper order/fill simulation and portfolio transition
   - owner: `execution` and `portfolio`
   - input: `ExecutionIntent`
   - output: simulated `OrderState`, `FillEvent`, and updated `PortfolioState`
   - failure points: inconsistent simulation assumptions, incorrect portfolio accounting
   - multi-cycle behavior: sequential bars must carry forward the prior cycle's ending `PortfolioState` and derived `PositionState`
   - lifecycle model: `new -> acknowledged -> partially_filled|filled|canceled|expired|rejected`
9. Future exchange execution and reconciliation
   - owner: `exchanges` and `portfolio`
   - input: `ExecutionIntent`
   - output: normalized `OrderState`, `FillEvent`, and `AccountSnapshot`
   - failure points: venue rejection, timeout, malformed private payload translation, reconciliation mismatch
   - reconciliation states: `submit_sent -> unknown_execution -> status_query_pending -> recovered_terminal_state | unreconciled_manual_attention`
   - order lifecycle recovery states: `recovering -> filled|canceled|expired|rejected|unreconciled`
   - canonical translation rule: Binance private payloads must pass through the explicit private-payload translator before portfolio mutation or account sync
   - gap automation: private-stream gaps trigger explicit automatic signed status-query recovery when policy allows
   - automatic recovery trigger reasons remain explicit:
     - `private_stream_gap`
     - `restart_resume`
     - `unknown_execution`
     - `missing_private_updates`
   - automatic recovery is restart-safe: persisted unresolved reconciliation state may resume signed status-query recovery after process restart instead of silently resetting the workflow
   - persistence: recovery attempts and outcomes are written to append-only reconciliation logs, and the latest unresolved reconciliation cursor/state snapshot persists:
     - gap detection
     - recovery trigger reason
     - automatic vs resumed recovery state
     - attempt sequence and replay-safe numbering
     - convergence result
     - manual-attention escalation timing

## Mode Behavior

- `report_only`
  - completes validation, features, strategy, risk, execution-intent generation, and persistence
  - creates auditable `ExecutionIntent` records only
  - does not create exchange-bound order side effects
  - may consume normalized public WS candle-close events as the real-time trigger source
  - feature policy: first complete path for candle features plus optional read-only index/stablecoin snapshots
  - Index Suite policy: only valid snapshots enrich features; missing/stale/version-mismatched snapshots are persisted as diagnostics
  - quality policy: may continue with explicit degraded states except for `incomplete_bar`
  - persists: `FeatureSnapshot`, `DecisionContext` summary, `SignalDecision`, `RiskDecision`, `ExecutionIntent`, `RuntimeCycleResult`
- `paper`
  - completes validation through execution intent generation and local fill simulation
  - creates simulated `ExecutionIntent`, `OrderState`, `FillEvent`, and updated `PortfolioState`
  - reuses the same feature producers as report-only
  - may consume the same normalized public WS candle-close events as report-only
  - quality policy: may continue with explicit degraded states except for `incomplete_bar`
  - persists: everything from report-only plus explicit paper state transitions and paper session summaries
- `restricted_live`
  - prepares live-facing `ExecutionIntent` values with venue configuration
  - does not submit to exchanges yet
  - reuses the same feature producers as report-only
  - persists: everything from paper mode plus live-preparation alerts for deferred execution
  - when configured with reconciliation state storage, persists unresolved order ids, latest cursor, gap flag, and replay-safe recovery attempt numbering
  - live portfolio/account sync must consume canonical `OrderState`, `FillEvent`, and `AccountSnapshot` only
  - any live portfolio mutation must pass through the mandatory safeguard gate after canonical Binance translation
  - ambiguous, unreconciled, malformed, or snapshot-mismatched live state must block mutation explicitly
  - quality policy: fails closed on `missing_data`, `stale_data`, `version_mismatch`, `incomplete_bar`, and `time_sync_uncertain`

## Current Skeleton Ownership

- `scripts/runtime2_rehearsal.py`
  - authoritative Python launcher for report-only, paper, and restricted-live rehearsal
  - shell wrappers delegate to this entrypoint only
- `app/runtime/report_only_runner.py`
  - first complete working reference implementation
  - contains the first real-data reference path using Binance kline schema inputs
- `app/runtime/feature_builder.py`
  - shared candle/index/stablecoin feature composition
- `app/runtime/paper_runner.py`
  - simulated order acceptance, fill path, and portfolio continuity
- `app/runtime/restricted_live_runner.py`
  - live-preparation stage without submission
- `app/runtime/state_machine.py`
  - explicit stage tracking for cycle execution
- `app/runtime/bar_close_validator.py`
  - closed-bar gatekeeper

## Core Invariants

- Closed bars are the only valid trigger for strategy evaluation.
- Strategies consume canonical candles and features, never raw exchange payloads.
- Feature producers own candle/index/stablecoin computation or adaptation before strategy evaluation.
- Risk checks complete before any future exchange side effect.
- Report-only is the reference path for end-to-end debugging and contract validation.
- Paper mode remains exchange-free even though it simulates order lifecycle and portfolio changes.
- Order lifecycle is shared across paper, reconciliation, and future live-facing execution paths.
- Paper session continuity is part of the reference path and must stay traceable across repeated bars.
- Mode separation is explicit in runner classes and `RunnerMode`.
- Every cycle produces auditable persistence artifacts even when it fails early.
- Reconciliation uncertainty is treated as a first-class workflow with explicit state visibility.
- Automatic recovery remains inspectable: gap-triggered or restart-resumed status queries must stay visible in logs and cursor snapshots rather than hidden behind silent retries.
- Private-stream-gap recovery is policy-driven automation, not optimistic inference. If recovery does not converge, the workflow must stay pending or escalate to manual attention explicitly.
- Data quality and freshness are treated as first-class runtime inputs and remain separate from strategy logic.
- Public market-data transport concerns remain isolated inside exchange adapters and must emit canonical bars rather than raw WS payloads.
