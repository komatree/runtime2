#!/usr/bin/env python3
"""Conservative release gate helper for runtime2.

This script verifies that required local skill folders and readiness documents
exist, and can optionally run the marker-based pytest gate commands used before
restricted-live review.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SKILLS = (
    "runtime-review",
    "exchange-hardening-review",
    "docs-sync",
    "release-gate-check",
)

REQUIRED_DOCS = (
    "docs/restricted_live_readiness.md",
    "docs/release_readiness_checklist.md",
    "docs/release_gate_checklist.md",
    "docs/testing_strategy.md",
    "docs/operator_runbook.md",
    "docs/debugging_playbook.md",
    "docs/cutover_checklist.md",
    "docs/binance_cutover_readiness.md",
    "docs/binance_known_gaps.md",
)

PYTEST_GATE_COMMANDS = (
    ("contracts/features/strategies/runtime/exchanges", [
        "pytest",
        "-m",
        "contracts or features or strategies or runtime_mode or exchanges",
        "tests",
        "-q",
    ]),
    ("report_only/paper/reconciliation/observability", [
        "pytest",
        "-m",
        "report_only_integration or paper_integration or reconciliation or observability",
        "tests",
        "-q",
    ]),
    ("scenario_regression", ["pytest", "-m", "scenario_regression", "tests", "-q"]),
    ("regression", ["pytest", "-m", "regression", "tests", "-q"]),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def check_skills() -> list[CheckResult]:
    results: list[CheckResult] = []
    for skill_name in REQUIRED_SKILLS:
        skill_root = ROOT / ".codex" / "skills" / skill_name
        skill_file = skill_root / "SKILL.md"
        ok = skill_root.is_dir() and _nonempty_file(skill_file)
        detail = "present" if ok else f"missing {skill_file.relative_to(ROOT)}"
        results.append(CheckResult(name=f"skill:{skill_name}", ok=ok, detail=detail))
    return results


def check_docs() -> list[CheckResult]:
    results: list[CheckResult] = []
    for doc in REQUIRED_DOCS:
        doc_path = ROOT / doc
        ok = _nonempty_file(doc_path)
        detail = "present" if ok else f"missing or empty {doc}"
        results.append(CheckResult(name=f"doc:{doc}", ok=ok, detail=detail))
    return results


def run_pytest_commands() -> list[CheckResult]:
    results: list[CheckResult] = []
    for label, command in PYTEST_GATE_COMMANDS:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        ok = completed.returncode == 0
        detail = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if not ok:
            stderr = completed.stderr.strip().splitlines()
            tail = stderr[-1] if stderr else "pytest command failed"
            detail = tail or detail or "pytest command failed"
        results.append(CheckResult(name=f"pytest:{label}", ok=ok, detail=detail))
    return results


def print_results(results: list[CheckResult]) -> None:
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="runtime2 release gate helper")
    parser.add_argument(
        "--run-pytest",
        action="store_true",
        help="Run marker-based pytest gate commands after file checks.",
    )
    args = parser.parse_args()

    all_results: list[CheckResult] = []
    all_results.extend(check_skills())
    all_results.extend(check_docs())
    if args.run_pytest:
        all_results.extend(run_pytest_commands())

    print_results(all_results)
    failures = [result for result in all_results if not result.ok]
    if failures:
        print("\nrelease gate check failed")
        return 1

    print("\nrelease gate check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
