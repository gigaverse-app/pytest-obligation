"""Replay fresh Quint histories of the session-host contract through real pytest configuration and the host API.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/session-host/manifest.json, replays each one through the driver in
docs/quint/session-host/adapter.py, and requires every declared mutation to be
caught by an observed-state mismatch.
"""

import importlib.util
from pathlib import Path

import pytest
from pytest_quint_connect import HistoryContext, quint_contract

TOPIC = Path(__file__).resolve().parents[2] / "docs" / "quint" / "session-host"

test_session_host = quint_contract(TOPIC / "manifest.json", driver="session_host_driver")


@pytest.fixture
def session_host_driver():
    spec = importlib.util.spec_from_file_location("session_host_quint_driver", TOPIC / "adapter.py")
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    def start(context: HistoryContext):
        return adapter.create(context.contract.root, context.work_dir, context.mutant)

    return start
