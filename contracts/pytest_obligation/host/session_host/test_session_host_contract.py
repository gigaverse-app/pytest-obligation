"""Replay Quint histories of model.qnt against real pytest configuration and the host API (driver: session_host_adapter.py)."""

from pytest_quint_connect import quint_contract

test_session_host = quint_contract("quint-connect.json", driver="adapter_driver")
