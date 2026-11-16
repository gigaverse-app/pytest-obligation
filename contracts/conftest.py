"""The driver fixture for contracts whose driver is a hand-written adapter.

A contract in contracts/<module path>/<name>/ with a <name>_adapter.py beside its manifest
declares quint_contract("quint-connect.json", driver="adapter_driver"). The adapter exposes
create(root, work, mutant) and returns an object with step() and observe(). Contracts with a
generated, typed driver (see fenced_lease) keep their own fixture in their conftest.py.
"""

import importlib

import pytest
from pytest_quint_connect import HistoryContext


@pytest.fixture
def adapter_driver():
    def start(context: HistoryContext):
        # pytest's default import mode puts each contract's directory on sys.path, so the adapter
        # beside the manifest imports by name; names are unique because directory names are.
        adapter = importlib.import_module(f"{context.contract.manifest.parent.name}_adapter")
        return adapter.create(context.contract.root, context.work_dir, context.mutant)

    return start
