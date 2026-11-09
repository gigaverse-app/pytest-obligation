"""Replay Quint histories of model.qnt against the real CostCompleteness hooks (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

test_cost_baseline = quint_contract("quint-connect.json", driver="cost_baseline_driver")
