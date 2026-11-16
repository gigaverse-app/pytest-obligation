"""Replay Quint histories of model.qnt against profile C's reference machine, InMemoryMachine (driver: ambiguity_adapter.py)."""

from pytest_quint_connect import quint_contract

test_ambiguity = quint_contract("quint-connect.json", driver="adapter_driver")
