"""Replay fresh Quint histories of the resource-identity contract through the shipped reference ResourceProvider.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/resource-identity/manifest.json and replays each one through the topic's
adapter.py (loaded by the quint_adapter fixture in conftest.py). Every
declared planted bug must be caught by an observed-state mismatch.
"""

from pathlib import Path

from pytest_quint_connect import quint_contract

test_resource_identity = quint_contract(
    Path(__file__).resolve().parents[2] / "docs" / "quint" / "resource-identity" / "manifest.json",
    driver="quint_adapter",
)
