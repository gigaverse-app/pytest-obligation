"""Replay Quint histories of model.qnt against the shipped reference ResourceProvider (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

test_resource_identity = quint_contract("quint-connect.json", driver="resource_identity_driver")
