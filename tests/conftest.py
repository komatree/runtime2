"""Shared pytest marker baseline for runtime2 regression gates."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Assign stable marker groups from test paths and filenames."""

    for item in items:
        path = Path(str(item.fspath))
        parts = set(path.parts)
        item.add_marker(pytest.mark.regression)

        if "contracts" in parts:
            item.add_marker(pytest.mark.contracts)
        if "features" in parts:
            item.add_marker(pytest.mark.features)
        if "strategies" in parts:
            item.add_marker(pytest.mark.strategies)
        if "exchanges" in parts:
            item.add_marker(pytest.mark.exchanges)
        if "runtime" in parts:
            item.add_marker(pytest.mark.runtime_mode)

        name = path.name
        if "report_only" in name:
            item.add_marker(pytest.mark.report_only_integration)
        if "paper_runner" in name:
            item.add_marker(pytest.mark.paper_integration)
        if "reconciliation" in name:
            item.add_marker(pytest.mark.reconciliation)
        if "observability" in name or "report_persistence" in name:
            item.add_marker(pytest.mark.observability)
        if "scenario" in name:
            item.add_marker(pytest.mark.scenario_regression)
