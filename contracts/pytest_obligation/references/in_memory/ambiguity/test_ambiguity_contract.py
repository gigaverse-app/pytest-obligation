"""Replay Quint histories of model.qnt against profile C's reference machine, InMemoryMachine (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

test_ambiguity = quint_contract("quint-connect.json", driver="ambiguity_driver")
