"""Replay Quint histories of model.qnt against the real CostCompleteness hooks (driver: cost_baseline_adapter.py)."""

from pytest_quint_connect import quint_contract

test_cost_baseline = quint_contract("quint-connect.json", driver="adapter_driver")
