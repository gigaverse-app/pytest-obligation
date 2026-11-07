"""Replay fresh Quint histories of the report-merge contract through the real merge_reports API.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/report-merge/manifest.json, replays each one through the driver in
docs/quint/report-merge/adapter.py, and requires every declared mutation to be
caught by an observed-state mismatch.
"""

import importlib.util
from pathlib import Path

import pytest

from pytest_quint_connect import HistoryContext, quint_contract

TOPIC = Path(__file__).resolve().parents[2] / "docs" / "quint" / "report-merge"

test_report_merge = quint_contract(TOPIC / "manifest.json", driver="report_merge_driver")


@pytest.fixture
def report_merge_driver():
    spec = importlib.util.spec_from_file_location("report_merge_quint_driver", TOPIC / "adapter.py")
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    def start(context: HistoryContext):
        return adapter.create(context.contract.root, context.work_dir, context.mutant)

    return start
