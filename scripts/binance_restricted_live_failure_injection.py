#!/usr/bin/env python3
"""Deterministic restricted-live failure-injection campaign."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.monitoring.restricted_live_failure_injection import build_default_failure_injection_scenarios
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionArtifactWriter
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionReportingService
from app.monitoring.restricted_live_failure_injection import RestrictedLiveFailureInjectionRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="restricted-live failure-injection campaign")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "failure_injection",
        help="scenario artifact root directory",
    )
    parser.add_argument(
        "--scenario-id",
        action="append",
        default=[],
        help="limit execution to one or more scenario ids",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios = build_default_failure_injection_scenarios()
    if args.scenario_id:
        requested = set(args.scenario_id)
        scenarios = tuple(scenario for scenario in scenarios if scenario.scenario_id in requested)
        if not scenarios:
            raise SystemExit("no matching failure-injection scenarios requested")

    runner = RestrictedLiveFailureInjectionRunner(output_root=args.output_dir)
    reporting = RestrictedLiveFailureInjectionReportingService()
    exit_code = 0
    for scenario in scenarios:
        run = runner.run_scenario(scenario=scenario)
        paths = RestrictedLiveFailureInjectionArtifactWriter(
            output_dir=args.output_dir / scenario.scenario_id,
        ).persist(
            run=run,
            markdown=reporting.render_markdown(run=run),
        )
        print(f"scenario_id: {scenario.scenario_id}")
        print(f"summary_json: {paths.summary_json_path}")
        print(f"summary_markdown: {paths.summary_markdown_path}")
        print(f"cycle_records_jsonl: {paths.cycle_records_path}")
        print(f"scenario_passed: {str(run.summary.scenario_passed).lower()}")
        if not run.summary.scenario_passed:
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
