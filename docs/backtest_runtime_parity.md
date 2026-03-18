# Backtest Runtime Parity

## Purpose

This document defines the replay and parity harness used to compare `runtime2` decision outputs against a reference backtest-style evaluation path.

The goal is not speed. The goal is reproducibility, explainability, and auditable drift detection.

## Inputs

The replay harness processes one closed bar at a time and supports:

- 4h execution candles
- 1d context candles
- optional Index Suite snapshots
- optional stablecoin snapshots

Each replay cycle is explicit and deterministic.

## Compared Outputs

For each replayed cycle and runtime mode, the harness persists parity records covering:

- signal side and actionability
- key context fields
- risk posture
- execution intent shape

Current runtime modes compared:

- `report_only`
- `paper`

Reference path:

- backtest-style evaluation using the same canonical contracts and shared runtime components, without runner orchestration side effects

## Persisted Artifacts

Parity artifacts are append-only JSONL records.

Each record contains:

- runtime mode
- cycle id
- instrument and timeframe
- bar close time
- match / mismatch status
- mismatch categories
- key context summary
- runtime output summary
- reference output summary

## Mismatch Policy

Parity drift is a first-class diagnostic artifact.

When a mismatch appears:

1. Do not treat it as noise.
2. Inspect the persisted parity record first.
3. Determine whether the drift came from:
   - feature composition
   - optional snapshot presence
   - strategy output
   - risk posture
   - execution intent shape
4. Confirm whether the drift is expected due to an intentional code change.
5. If it is not intentional, block restricted-live progression until explained.

## Relationship To Scenario Regressions

Parity coverage and scenario regressions serve different purposes:

- parity tests compare runtime outputs to a reference evaluation path on the same inputs
- scenario regressions protect meaningful operator-facing behaviors such as:
  - no-action stability
  - breakout entry behavior
  - hold continuity
  - exit continuity
  - degraded-input handling
  - reconciliation-driven recovery visibility

Both should remain green before restricted-live review.

## Current Non-Goals

- performance optimization
- large historical dataset management
- exchange transport replay
- live execution parity

This harness is a decision-path parity tool, not a full execution simulator.
