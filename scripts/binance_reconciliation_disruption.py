#!/usr/bin/env python3
"""Deterministic Binance reconciliation disruption campaign."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.monitoring.reconciliation_disruption import build_default_reconciliation_disruption_scenarios
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionArtifactWriter
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionReportingService
from app.monitoring.reconciliation_disruption import ReconciliationDisruptionRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="reconciliation disruption campaign")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "reconciliation_disruption",
        help="artifact root directory",
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
    scenarios = build_default_reconciliation_disruption_scenarios()
    if args.scenario_id:
        requested = set(args.scenario_id)
        scenarios = tuple(s for s in scenarios if s.scenario_id in requested)
        if not scenarios:
            raise SystemExit("no matching reconciliation disruption scenarios requested")

    runner = ReconciliationDisruptionRunner(output_root=args.output_dir)
    reporting = ReconciliationDisruptionReportingService()
    exit_code = 0
    for scenario in scenarios:
        run = runner.run_scenario(scenario=scenario)
        paths = ReconciliationDisruptionArtifactWriter(
            output_dir=args.output_dir / scenario.scenario_id,
        ).persist(
            run=run,
            markdown=reporting.render_markdown(run=run),
        )
        print(f"scenario_id: {scenario.scenario_id}")
        print(f"summary_json: {paths.summary_json_path}")
        print(f"summary_markdown: {paths.summary_markdown_path}")
        print(f"workflow_records_jsonl: {paths.workflow_records_path}")
        print(f"workflow_log_jsonl: {paths.workflow_log_path}")
        print(f"reconciliation_state_json: {paths.reconciliation_state_path}")
        print(f"scenario_passed: {str(run.summary.scenario_passed).lower()}")
        if not run.summary.scenario_passed:
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
