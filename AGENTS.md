# runtime2 AGENTS

## Project Identity

- `runtime2` is a brand-new production-candidate candle-based trading runtime.
- It is not an extension of the legacy micro-live or grid runtime.
- Treat `runtime2/` as the authoritative codebase.

## Hard Rules

- Do not modify legacy repositories or legacy runtime directories unless explicitly asked.
- Do not add backward-compatibility hacks, bridge layers, or legacy-coupled shortcuts.
- Keep exchange-specific logic isolated under `app/exchanges/*`.
- Keep strategies unaware of exchange payloads, client objects, and venue JSON details.
- Keep feature producers separate from feature consumers. Strategies and risk consume `FeatureSnapshot`; they do not compute Index Suite or stablecoin features themselves.

## Phase-1 Scope

- Binance only.
- BTC / ETH / SOL only.
- `report_only` runner first and kept working as the first complete vertical slice.
- `paper` runner next.
- `restricted_live` remains skeleton-only until blockers are cleared.
- Index Suite is a shared read-only feature source.
- Stablecoin data is a report-only snapshot source in phase 1.
- Upbit is phase 2, not phase 1.

## Architecture Rules

- Start with contracts first. Preserve typed, explicit boundaries in `app/contracts`.
- Keep runtime flow explicit:
  - closed bar trigger
  - normalized candle slice
  - feature snapshot build
  - strategy evaluation
  - risk evaluation
  - execution intent
  - persistence/reporting
  - future exchange execution and reconciliation
- Keep runner modes separate. Do not collapse `report_only`, `paper`, and `restricted_live` into one behavior path with mode flags spread through the code.
- Keep open gaps explicit in code comments, docs, and final summaries. Do not imply live-readiness where it does not exist.

## Exchange Rules

- Binance pre-live blockers must stay visible in code and docs:
  - private stream ingestion
  - order status reconciliation
  - clock sync safety
- Do not hide unknown execution handling behind optimistic assumptions.
- Do not implement exchange behavior in strategies, features, risk, or runtime contracts.

## Quality Rules

- Use typed Python.
- Add tests for every new contract and every critical workflow change.
- Keep pure logic separate from IO. Strategies, feature transforms, and decision policies should stay pure where practical.
- Prefer small coherent vertical slices over broad incomplete scaffolding.

## Documentation Rules

- Update docs with code changes in the same task.
- Keep `docs/data_contracts.md` and `docs/runtime_flow.md` current whenever contracts or runtime flow change.
- Keep Binance blockers and phase boundaries current in exchange docs.

## Local Skills

- Local repository skills live under `.codex/skills/`.
- `.codex/skills/` is the canonical local skill path for this repo. Do not rely on the legacy top-level `skills/` directory.
- Use `runtime-review` after runtime, contract, feature, strategy, risk, execution, portfolio, or runner changes.
- Use `exchange-hardening-review` after exchange, reconciliation, private-stream, public-stream, or clock-sync changes.
- Use `docs-sync` after code changes that affect docs, operator procedures, runtime flow, contracts, or release/cutover status.
- Use `release-gate-check` before promotion to rehearsal or restricted-live, and before any go/no-go summary.
- If repo-local skills are not auto-exposed in a session, open `.codex/skills/<skill>/SKILL.md` directly and follow it anyway.

## Skill Invocation Policy

- After changes to `app/runtime`, `app/contracts`, `app/features`, or runner behavior, use `runtime-review` before declaring the task done.
- After changes to `app/exchanges`, reconciliation, private/public stream handling, clock sync, or order lifecycle, use `exchange-hardening-review` before declaring the task done.
- After any code change that affects docs or contracts, use `docs-sync`.
- Before any rehearsal, dry-run promotion, or restricted-live readiness claim, use `release-gate-check`.
- In completion summaries, mention whether the relevant skill was used and what it found.

## Review Output Requirements

- List changed files.
- Summarize design decisions.
- Summarize tests added and tests run.
- List open gaps and blockers.
