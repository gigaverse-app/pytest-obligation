"""A selective report accounts for declared suites without importing the application."""

import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

from pytest_obligation.reporting.inventory import discover
from pytest_obligation.reporting.markdown import render


def test_unreadable_contract_name_preserves_known_suite(tmp_path: Path) -> None:
    (tmp_path / "contracts.py").write_text("not valid Python !")
    (tmp_path / "test_orders.py").write_text(
        "from pytest_obligation.contract import due_work_contract_suite\n"
        "from contracts import ORDERS\n"
        "@due_work_contract_suite(ORDERS)\nclass TestOrders: pass\n"
    )
    inventory = discover(tmp_path, ["test_orders.py"])
    assert inventory.applications["test_orders.TestOrders"].name == "TestOrders"
    assert any("name unresolved" in limitation for limitation in inventory.limitations)


def test_uncollected_applications_keep_numeric_design_without_inventing_test_counts(tmp_path: Path) -> None:
    (tmp_path / "test_orders.py").write_text(
        "from pytest_obligation import due_work_contract_suite, ObligationContract\n"
        "@due_work_contract_suite(ObligationContract(name='Orders'))\nclass TestOrders: pass\n"
    )
    body = render({}, inventory=discover(tmp_path, ["test_orders.py"]), graphics=True)
    assert 'alt="1 applications"' in body
    assert 'alt="0 checks passed"' in body
    assert 'alt="skipped tests: unknown"' in body
    assert "**1** applications not run" in body
    assert "Checks skipped: **unknown**" in body
    assert "| Application / suite |" not in body
    assert "good-0" not in body
    assert body.index("<details>") < body.index("Orders")
    assert "applications not run" not in body.split("<details>")[0]


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
    assert "1 applications" in body
    assert "0 checks passed" in body
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


@pytest.mark.parametrize(
    "module,decorator,configured",
    [
        ("due.django.conformance.suite", "effect_contract_suite", ()),
        ("project.testing", "application_suite", ("project.testing.application_suite",)),
    ],
)
def test_inventory_finds_due_and_explicit_application_wrappers_without_imports(
    tmp_path: Path, module: str, decorator: str, configured: tuple[str, ...]
) -> None:
    (tmp_path / "test_orders.py").write_text(
        "raise RuntimeError('inventory must never import application code')\n"
        f"from {module} import {decorator} as suite\n"
        "@suite(operation, examples=examples)\nclass TestOrders: pass\n"
    )
    inventory = discover(tmp_path, ["."], suite_decorators=configured)
    assert list(inventory.applications) == ["test_orders.TestOrders"]
    assert inventory.applications["test_orders.TestOrders"].nodeids is None
    assert inventory.applications["test_orders.TestOrders"].source.path == "test_orders.py"
    if configured:
        assert not discover(tmp_path, ["."]).applications, "unconfigured wrappers must remain untrusted"


def test_report_cli_inventories_a_configured_wrapper(tmp_path: Path) -> None:
    (tmp_path / "test_orders.py").write_text(
        "from project.testing import suite\n@suite(contract)\nclass TestOrders: pass\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            "absent-*.json",
            "--output",
            "report.md",
            "--test-outcome",
            "skipped",
            "--application-path",
            ".",
            "--suite-decorator",
            "project.testing.suite",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "TestOrders" in (tmp_path / "report.md").read_text()
    assert "**1** applications not run" in (tmp_path / "report.md").read_text()
