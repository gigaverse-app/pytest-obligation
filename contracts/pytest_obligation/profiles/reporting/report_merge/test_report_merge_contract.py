"""Replay Quint histories of model.qnt against the real merge_reports API (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

test_report_merge = quint_contract("quint-connect.json", driver="report_merge_driver")
