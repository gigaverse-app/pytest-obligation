"""The report-merge driver fixture: each history gets a fresh adapter over the real merge_reports API.

report_merge_adapter.py is a hand-written driver (step and observe). It predates codegen; converting it
to a generated, typed base like fenced_lease's is follow-up work.
"""

import pytest
from pytest_quint_connect import HistoryContext
from report_merge_adapter import create


@pytest.fixture
def report_merge_driver():
    def start(context: HistoryContext):
        return create(context.contract.root, context.work_dir, context.mutant)

    return start
