# Release Gate Check Checklist

Use this document when running the local release-gate helper or preparing a Codex readiness review.

## Purpose

This checklist standardizes the minimum local checks before writing a restricted-live go/no-go summary.

It does not replace:

- [`docs/restricted_live_readiness.md`](/home/terratunes/code/trading/runtime2/docs/restricted_live_readiness.md)
- [`docs/release_readiness_checklist.md`](/home/terratunes/code/trading/runtime2/docs/release_readiness_checklist.md)

Those remain the policy and operator review sources of truth.

## Local Command

```bash
python scripts/release_gate_check.py
python scripts/release_gate_check.py --run-pytest
```

## Required Local Checks

- required local skills present under [`.codex/skills/`](/home/terratunes/code/trading/runtime2/.codex/skills)
- required readiness docs present and non-empty
- pytest gate commands remain runnable and auditable

## Expected Output Categories

- skill presence
- documentation presence
- pytest gate status when `--run-pytest` is used
- final pass/fail line suitable for operator review notes

## Manual Follow-Through

After the local helper passes, still confirm:

- runtime observability artifacts are present
- degraded states are visible and explainable
- Binance blockers are still disclosed explicitly
- rollback criteria are still understood
- open gaps are included in the final review output
