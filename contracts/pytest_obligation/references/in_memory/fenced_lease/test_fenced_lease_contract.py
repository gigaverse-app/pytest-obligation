"""Replay Quint histories of model.qnt against the real InMemoryOwner (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

test_fenced_lease = quint_contract("quint-connect.json", driver="fenced_lease_driver")
