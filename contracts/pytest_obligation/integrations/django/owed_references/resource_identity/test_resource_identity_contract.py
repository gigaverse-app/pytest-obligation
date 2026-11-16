"""Replay Quint histories of model.qnt against the shipped reference ResourceProvider (driver: resource_identity_adapter.py)."""

from pytest_quint_connect import quint_contract

test_resource_identity = quint_contract("quint-connect.json", driver="adapter_driver")
