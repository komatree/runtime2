# Phase 1 Scope

## Objective

Deliver a production-candidate baseline for candle-driven strategy execution on a constrained venue set with clear contracts and operational safety.

## In Scope

- Canonical candle data contract
- Deterministic candle ingestion and feature computation pipeline
- Initial feature families:
  - candle features
  - index suite features
  - stablecoin market health features
- Initial strategy families:
  - breakout first
  - pullback later within the new contracts, not as a legacy lift-and-shift
  - regime classification / gating as context
  - router for strategy activation and conflict resolution
- Risk checks for notional limits, symbol limits, exposure caps, and stale data rejection
- Execution planning for marketable and passive order intents
- Exchange adapters for Binance and Upbit behind common interfaces
- Basic portfolio state tracking
- Storage for runtime snapshots, fills, and audit events
- Monitoring for health, metrics, and actionable alerts

## Out of Scope

- Options, futures, or leveraged derivatives
- Cross-runtime backward compatibility shims
- All-in migration of legacy strategy code into `runtime2`
- GUI dashboards beyond essential operator artifacts
- Multi-region deployment automation
- High-frequency tick-level strategy logic

## Phase 1 Exit Criteria

- Replay mode can process candle streams end-to-end
- Strategies emit intents using only canonical contracts
- Risk layer can allow, modify, or reject intents deterministically
- Execution layer can route approved intents to exchange adapters
- Storage captures enough state for restart and auditability
- Runbooks and operator documentation cover the common failure paths
