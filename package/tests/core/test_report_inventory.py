"""A selective report accounts for declared suites without importing the application."""

import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest


@pytest.mark.parametrize("evidence", ["empty", "skipped", "missing"])
def test_unexecuted_applications_are_named_without_fabricating_results(tmp_path: Path, evidence: str) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/contracts.py").write_text(
        "raise RuntimeError('inventory must not import the application')\n"
        "from pytest_obligation import ObligationContract\n"
        "ORDERS = ObligationContract(name='Order delivery')\n"
    )
    (tmp_path / "tests/test_orders.py").write_text(
        "from pytest_obligation.contract import due_work_contract_suite as suite\n"
        "from tests.contracts import ORDERS\n"
        "@suite(ORDERS)\nclass TestOrders: pass\n"
    )
    if evidence == "empty":
        (tmp_path / "shard-1.json").write_text("{}")
    output = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            "shard-*.json",
            "--expected-reports",
            "0" if evidence == "skipped" else "1",
            "--output",
            str(output),
            "--test-outcome",
            "skipped" if evidence == "skipped" else "success",
            "--application-path",
            "tests",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    body = unescape(output.read_text())
    assert "Order delivery" in body
    assert "tests.test_orders.TestOrders" in body
    assert "0 checks passed" not in body
    if evidence == "missing":
        assert "Evidence unavailable" in body
        assert "Unknown: reports incomplete" in body
    else:
        assert "Evidence unavailable" not in body
        assert "Not run" in body
        assert "No application contract checks ran" in body


def test_empty_valid_reports_without_inventory_explain_their_scope(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text("{}")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            "report.json",
            "--output",
            "report.md",
            "--test-outcome",
            "success",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    body = (tmp_path / "report.md").read_text()
    assert "No application contract checks ran" in body
    assert "inventory was not supplied" in body
    assert "Evidence unavailable" not in body
