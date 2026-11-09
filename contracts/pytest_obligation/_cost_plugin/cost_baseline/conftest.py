"""The cost-baseline driver fixture: each history gets a fresh adapter over the real CostCompleteness hooks.

cost_baseline_adapter.py is a hand-written driver (step and observe). It predates codegen; converting it
to a generated, typed base like fenced_lease's is follow-up work.
"""

import pytest
from cost_baseline_adapter import create
from pytest_quint_connect import HistoryContext


@pytest.fixture
def cost_baseline_driver():
    def start(context: HistoryContext):
        return create(context.contract.root, context.work_dir, context.mutant)

    return start
