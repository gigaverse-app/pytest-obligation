"""Replay fresh Quint histories of the resource-identity contract through the shipped reference ResourceProvider.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/resource-identity/manifest.json, replays each one through the driver in
docs/quint/resource-identity/adapter.py, and requires every declared mutation to be
caught by an observed-state mismatch.
"""

import importlib.util
from pathlib import Path

import pytest
from pytest_quint_connect import HistoryContext, quint_contract

TOPIC = Path(__file__).resolve().parents[2] / "docs" / "quint" / "resource-identity"

test_resource_identity = quint_contract(TOPIC / "manifest.json", driver="resource_identity_driver")


@pytest.fixture
def resource_identity_driver():
    spec = importlib.util.spec_from_file_location("resource_identity_quint_driver", TOPIC / "adapter.py")
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    def start(context: HistoryContext):
        return adapter.create(context.contract.root, context.work_dir, context.mutant)

    return start
