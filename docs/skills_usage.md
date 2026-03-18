# Skills Usage

Local repository skills are version-controlled under [`.codex/skills/`](/home/terratunes/code/trading/runtime2/.codex/skills).

## Launch Location

Start Codex from the repository root:

```bash
cd /home/terratunes/code/trading/runtime2
```

Expected local skill root:

```bash
pwd
ls .codex/skills
```

The canonical local skill path is [`.codex/skills/`](/home/terratunes/code/trading/runtime2/.codex/skills). The legacy top-level [`skills/`](/home/terratunes/code/trading/runtime2/skills) directory is now only a deprecated README stub and is not the authoritative path for normal Codex workflow.

## Skills

- `runtime-review`
  - for runtime, contract, feature, strategy, risk, execution, portfolio, and runner reviews
- `exchange-hardening-review`
  - for Binance adapter, reconciliation, private/public stream, clock-sync, and exchange-boundary reviews
- `docs-sync`
  - for documentation drift checks after code changes
- `release-gate-check`
  - for readiness, rehearsal, dry-run promotion, restricted-live, and go/no-go checks

## When To Invoke

- use `runtime-review` after runtime-path changes
- use `exchange-hardening-review` after exchange or recovery-path changes
- use `docs-sync` after code changes affecting docs or operator behavior
- use `release-gate-check` before promotion to rehearsal, dry-run promotion, or restricted-live

## Example Prompts

- `Use runtime-review on these runtime and feature changes.`
- `Run exchange-hardening-review on the Binance reconciliation update.`
- `Use docs-sync after these contract and runbook edits.`
- `Run release-gate-check before giving a restricted-live go/no-go summary.`
- `Use runtime-review and docs-sync after these app/runtime and docs changes.`
- `Use exchange-hardening-review before closing this Binance private-stream task.`
- `Use release-gate-check before this dry-run promotion summary.`

## Fallback If Skills Are Not Auto-Exposed

If a session does not list the repo-local skills automatically, do not switch to a different skill path and do not assume the skills are missing. Treat [`.codex/skills/`](/home/terratunes/code/trading/runtime2/.codex/skills) as authoritative and open the needed `SKILL.md` files directly.

Fallback examples:

```bash
sed -n '1,220p' .codex/skills/runtime-review/SKILL.md
sed -n '1,220p' .codex/skills/exchange-hardening-review/SKILL.md
sed -n '1,220p' .codex/skills/docs-sync/SKILL.md
sed -n '1,220p' .codex/skills/release-gate-check/SKILL.md
```

After opening the file, follow the skill instructions normally and say in the task summary that the skill was used via direct `SKILL.md` fallback because it was not auto-exposed in that session.

## Local Layout

Each skill contains:

- `SKILL.md`
- `checklists/*.md`

No extra speculative skills are part of the local pack.

## Release Gate Helper

Use the helper script for an auditable local pass:

```bash
python scripts/release_gate_check.py
python scripts/release_gate_check.py --run-pytest
```

This helper verifies that the canonical local skills exist under [`.codex/skills/`](/home/terratunes/code/trading/runtime2/.codex/skills) and that required readiness docs are present.
