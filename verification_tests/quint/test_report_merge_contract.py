"""Replay fresh Quint histories of the report-merge contract through the real merge_reports API.

pytest-quint-connect generates the witnesses and samples declared in
docs/quint/report-merge/manifest.json and replays each one through the topic's
adapter.py (loaded by the quint_adapter fixture in conftest.py). Every
declared planted bug must be caught by an observed-state mismatch.
"""

from pathlib import Path

from pytest_quint_connect import quint_contract

test_report_merge = quint_contract(
    Path(__file__).resolve().parents[2] / "docs" / "quint" / "report-merge" / "manifest.json", driver="quint_adapter"
)
