"""The session-host driver fixture: each history gets a fresh adapter over real pytest configuration and the host API.

session_host_adapter.py is a hand-written driver (step and observe). It predates codegen; converting it
to a generated, typed base like fenced_lease's is follow-up work.
"""

import pytest
from pytest_quint_connect import HistoryContext
from session_host_adapter import create


@pytest.fixture
def session_host_driver():
    def start(context: HistoryContext):
        return create(context.contract.root, context.work_dir, context.mutant)

    return start
