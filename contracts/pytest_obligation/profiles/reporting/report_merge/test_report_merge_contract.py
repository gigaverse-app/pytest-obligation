"""Replay Quint histories of model.qnt against the real merge_reports API (driver in conftest.py)."""

from pytest_quint_connect import quint_contract

# The adapter loads the source mutants by file path, not by import:
# gv:test-dependency: scripts/source_contracts/mutations.py

test_report_merge = quint_contract("quint-connect.json", driver="report_merge_driver")
