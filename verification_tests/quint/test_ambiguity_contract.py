"""Replay fresh Quint histories of the ambiguity contract through profile C's reference machine, InMemoryMachine.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/ambiguity/manifest.json and replays each one through the topic's
adapter.py (loaded by the quint_adapter fixture in conftest.py). Every
declared planted bug must be caught by an observed-state mismatch.
"""

from pathlib import Path

from pytest_quint_connect import quint_contract

test_ambiguity = quint_contract(
    Path(__file__).resolve().parents[2] / "docs" / "quint" / "ambiguity" / "manifest.json", driver="quint_adapter"
)
