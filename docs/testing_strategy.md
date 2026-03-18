# Testing Strategy

## Test Layers

- Contract tests
  - scope: canonical model construction, invariants, and normalization boundaries
  - examples: `Candle`, `DecisionContext`, `ExecutionIntent`, `OrderState`
- Pure logic tests
  - scope: strategy and future risk logic with no side effects
  - examples: breakout trigger placeholders, regime classification placeholders, router composition
- Feature layer tests
  - scope: feature service output shape, partial-input tolerance, unified `FeatureSnapshot` composition
  - examples: candle-derived features, read-only index snapshot adaptation, stablecoin snapshot adaptation
- Runner mode tests
  - scope: runner initialization, mode separation, bar-close gating, cycle-result generation
  - examples: report-only path, paper no-action/action cycles, portfolio continuity, restricted-live construction guards
- Exchange adapter stub tests
  - scope: adapter interface existence, clock safety stubs, reconciliation summary shape, client construction
  - examples: Binance adapter skeleton tests
- Report-only integration tests
  - scope: closed-bar trigger through feature/strategy/risk/persistence without exchange submission
  - examples: `ReportOnlyRunner` end-to-end slice with real report-only feature/risk/execution/persistence components
- Paper-mode integration tests
  - scope: report-only shared path plus simulated order/fill and portfolio state transitions
  - examples: no-action cycle, action-producing cycle, portfolio state update, multiple-cycle continuity, enter/hold/exit session continuity, repeated feature updates
- Restricted-live readiness tests
  - scope: conservative rollout gates around adapter visibility, reconciliation shape, and clock safety
  - examples: exchange adapter stub tests, future reconciliation tests, any later restricted-live gate tests
- Report schema tests
  - scope: append-only persistence shape, serializer tolerance for optional sections, schema stability
  - examples: round-trip JSONL repository reads, missing optional feature sections, fixed top-level field shape
- Future reconciliation tests
  - scope: unknown execution handling, private-stream gap detection, reconciliation fallbacks
  - examples: currently placeholder tests documenting expected future coverage
- Backtest-runtime parity tests
  - scope: replay harness determinism, report-only/paper decision parity, explicit mismatch reporting
  - examples: no-action parity, action parity, mismatch artifact persistence
- Scenario regression tests
  - scope: operator-readable end-to-end scenarios covering portfolio continuity, risk posture, degraded inputs, and reconciliation recovery
  - examples: clean no-action market, breakout entry, hold, exit, degraded feature inputs, reconciliation-driven recovery
- Restricted-live rehearsal scenario tests
  - scope: end-to-end rehearsal verification for canonical Binance translation, reconciliation outcome, safeguard gating, restart safety, and operator-facing scenario artifacts
  - examples: safe mutation path, ambiguous mutation blocked path, unreconciled mutation blocked path, restart with unresolved reconciliation state, restart with degraded private-stream state, restart with blocked portfolio mutation state
- Restricted-live failure-injection campaign tests
  - scope: simulated exchange failure conditions across the real restricted-live runner and Binance safeguard gate
  - examples: private stream disconnect, listen-key expiration, reconnect storms, delayed private events, missing order events, duplicated fill events
- Reconciliation disruption scenario tests
  - scope: deterministic reconciliation convergence and escalation under disrupted private-stream conditions
  - examples: private event loss, delayed status query, duplicated execution reports, partial fill reorder

## Phase 1 Priorities

- Contract invariants stay strict and venue-neutral
- Candle normalization and close-window correctness stay deterministic
- Feature services remain producer-owned rather than strategy-owned
- Report-only mode is the first complete vertical slice and must stay green
- Paper mode must remain deterministic and explicitly exchange-free
- Paper sessions must be reproducible across sequential bars with append-only transition logs and session summaries
- Restricted-live eligibility depends on documented gates, not optimism about unfinished exchange code
- Blocked mutation is a valid rehearsal success path when the scenario expects a fail-closed outcome
- Restart-safe blocked mutation is a valid rehearsal success path when unresolved or degraded state is restored correctly
- Failure-injection scenarios should prove operator visibility, not just liveness, under exchange stress
- Report-only persistence schema must stay explicit and stable for debugging
- Adapter tests lock shape and safety hooks before live trading code exists
- Parity drift is a blocking diagnostic until explained, not an optional analytics signal
- Scenario regressions should stay small in number and high in diagnostic value

## Tooling Direction

- `pytest` for primary test execution
- Fixtures for canonical candles, feature snapshots, portfolio state, and runtime dependencies
- Serializer and repository tests should verify append-only behavior before any SQLite migration
- Replay datasets stored under `data/` or synthesized in test fixtures
- No dependency on legacy runtime behavior as a correctness oracle
- Prefer pure, deterministic tests first; add side-effecting integration tests only after contracts stabilize

## Marker Baseline

The regression baseline uses stable pytest markers so restricted-live review can point to auditable test groups instead of one opaque command.

- `contracts`
  - canonical contract and invariant tests
- `features`
  - feature service and composition tests
- `strategies`
  - pure strategy logic tests
- `runtime_mode`
  - runner construction, mode separation, and cycle behavior tests
- `exchanges`
  - Binance adapter scaffold and boundary tests
- `report_only_integration`
  - report-only vertical-slice integration tests
- `paper_integration`
  - paper continuity and portfolio simulation tests
- `reconciliation`
  - unknown execution and recovery workflow tests
- `observability`
  - status, health summary, and persistence observability tests
- `scenario_regression`
  - scenario-based runtime and portfolio regression coverage
- `regression`
  - umbrella marker applied to the full baseline suite

Recommended gate commands:

```bash
pytest -m "contracts or features or strategies or runtime_mode or exchanges" tests -q
pytest -m "report_only_integration or paper_integration or reconciliation or observability" tests -q
pytest -m scenario_regression tests -q
pytest -m regression tests -q
```

Marker groups are conservative release gates. If a test belongs to a required gate, it should not rely on network access or non-deterministic timing.
