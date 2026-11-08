"""Replay fresh Quint histories of the cost-baseline contract through the real CostCompleteness hooks.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/cost-baseline/manifest.json and replays each one through the topic's
adapter.py (loaded by the quint_adapter fixture in conftest.py). Every
declared planted bug must be caught by an observed-state mismatch.
"""

from pathlib import Path

from pytest_quint_connect import quint_contract

test_cost_baseline = quint_contract(
    Path(__file__).resolve().parents[2] / "docs" / "quint" / "cost-baseline" / "manifest.json", driver="quint_adapter"
)
