"""Replay fresh Quint histories of the session-host contract through real pytest configuration and the host API.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/session-host/manifest.json and replays each one through the topic's
adapter.py (loaded by the quint_adapter fixture in conftest.py). Every
declared planted bug must be caught by an observed-state mismatch.
"""

from pathlib import Path

from pytest_quint_connect import quint_contract

test_session_host = quint_contract(
    Path(__file__).resolve().parents[2] / "docs" / "quint" / "session-host" / "manifest.json", driver="quint_adapter"
)
