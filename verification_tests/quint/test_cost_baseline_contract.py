"""Replay fresh Quint histories of the cost-baseline contract through the real CostCompleteness hooks.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/cost-baseline/manifest.json, replays each one through the driver in
docs/quint/cost-baseline/adapter.py, and requires every declared mutation to be
caught by an observed-state mismatch.
"""

import importlib.util
from pathlib import Path

import pytest
from pytest_quint_connect import HistoryContext, quint_contract

TOPIC = Path(__file__).resolve().parents[2] / "docs" / "quint" / "cost-baseline"

test_cost_baseline = quint_contract(TOPIC / "manifest.json", driver="cost_baseline_driver")


@pytest.fixture
def cost_baseline_driver():
    spec = importlib.util.spec_from_file_location("cost_baseline_quint_driver", TOPIC / "adapter.py")
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    def start(context: HistoryContext):
        return adapter.create(context.contract.root, context.work_dir, context.mutant)

    return start
