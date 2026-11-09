"""The ambiguity driver fixture: each history gets a fresh adapter over profile C's reference machine, InMemoryMachine.

ambiguity_adapter.py is a hand-written driver (step and observe). It predates codegen; converting it
to a generated, typed base like fenced_lease's is follow-up work.
"""

import pytest
from ambiguity_adapter import create
from pytest_quint_connect import HistoryContext


@pytest.fixture
def ambiguity_driver():
    def start(context: HistoryContext):
        return create(context.contract.root, context.work_dir, context.mutant)

    return start
