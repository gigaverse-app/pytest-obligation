"""Count real generated tests without executing fixture setup or test bodies."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pytest_obligation.reporting.collected import skipped_tests
from pytest_obligation.reporting.inventory import ApplicationInventory
from tests.core.test_profile_summary import contract_project  # noqa: F401


@pytest.mark.parametrize("options_source", ["ini", "environment"])
def test_collect_missing_once_then_reuse_inventory(
    contract_project: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, options_source: str  # noqa: F811
) -> None:
    contract_project.makepyfile(
        counting_bootstrap="from pathlib import Path\n"
        "def pytest_configure(config):\n    Path('bootstrap-loaded').touch()\n"
    )
    options = "-p counting_bootstrap -n 2 --dist=loadgroup"
    if options_source == "ini":
        contract_project.makeini(f"[pytest]\naddopts = {options}\n")
    else:
        monkeypatch.setenv("PYTEST_ADDOPTS", options)
    contract_project.makepyfile(test_unrelated="raise RuntimeError('Do not collect unrelated tests for counts')")
    contract_project.makeconftest(
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.fixture(autouse=True)\ndef never_execute():\n"
        "    Path('tests-executed').touch()\n    raise AssertionError('counting must not run tests')\n"
    )
    output = contract_project.path / "inventory.json"
    command = [
        sys.executable,
        "-I",
        "-m",
        "pytest_obligation.reporting.collect",
        "--application-path",
        ".",
        "--output",
        str(output),
        "--revision",
        "revision-one",
    ]
    result = subprocess.run(
        command + ["--pytest-command", f"{sys.executable} -m pytest"],
        cwd=contract_project.path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads(output.read_text())
    count = sum(len(app["nodeids"]) for app in inventory["applications"].values())
    assert count > 0
    assert (contract_project.path / "bootstrap-loaded").exists()
    assert not (contract_project.path / "tests-executed").exists()
    reused = subprocess.run(
        command + ["--pytest-command", "must-not-be-launched"],
        cwd=contract_project.path,
        capture_output=True,
        text=True,
    )
    assert reused.returncode == 0, reused.stderr
    rendered = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            "absent-*.json",
            "--expected-reports",
            "0",
            "--test-outcome",
            "skipped",
            "--inventory",
            str(output),
            "--collection-revision",
            "revision-one",
            "--junit-input",
            "absent-*.xml",
            "--graphics",
            "--output",
            "report.md",
        ],
        cwd=contract_project.path,
        capture_output=True,
        text=True,
    )
    assert rendered.returncode == 0, rendered.stderr
    assert f'alt="{count} skipped tests"' in (contract_project.path / "report.md").read_text()
    stale = subprocess.run(
        ["wrong-revision" if value == "revision-one" else value for value in rendered.args],
        cwd=contract_project.path,
        capture_output=True,
        text=True,
    )
    assert stale.returncode == 0, stale.stderr
    assert 'alt="skipped tests: unknown"' in (contract_project.path / "report.md").read_text()


def test_existing_selector_nodeids_avoid_collection(tmp_path: Path) -> None:
    (tmp_path / "test_orders.py").write_text(
        "raise RuntimeError('must not import')\n"
        "from pytest_obligation import due_work_contract_suite\n"
        "@due_work_contract_suite(contract)\nclass TestOrders: pass\n"
    )
    (tmp_path / "selected.json").write_text(json.dumps({"test_orders.py::TestOrders::test_contract[a]": {}}))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting.collect",
            "--application-path",
            ".",
            "--input",
            "selected.json",
            "--output",
            "inventory.json",
            "--revision",
            "head-one",
            "--pytest-command",
            "must-not-be-launched",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "inventory.json").read_text())["applications"]["test_orders.TestOrders"][
        "nodeids"
    ] == ["test_orders.py::TestOrders::test_contract[a]"]


@pytest.mark.parametrize("damage", ["none", "stale", "broken", "xdist"])
def test_collection_then_partial_execution_counts_remaining_tests(
    contract_project: pytest.Pytester,  # noqa: F811
    damage: str,
) -> None:
    inventory_file = contract_project.path / "inventory.json"
    command = [
        sys.executable,
        "-I",
        "-m",
        "pytest_obligation.reporting.collect",
        "--application-path",
        ".",
        "--output",
        str(inventory_file),
        "--revision",
        "current",
        "--pytest-command",
        f"{sys.executable} -m pytest",
    ]
    first = subprocess.run(command, cwd=contract_project.path, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    if damage in ("stale", "broken"):
        inventory_file.write_text(
            "{" if damage == "broken" else inventory_file.read_text().replace('"current"', '"old"')
        )
        repaired = subprocess.run(command, cwd=contract_project.path, capture_output=True, text=True)
        assert repaired.returncode == 0, repaired.stderr
    inventory = ApplicationInventory.model_validate_json(inventory_file.read_bytes())
    junit = contract_project.path / "junit.xml"
    extra = []
    if damage == "xdist":
        contract_project.makeconftest(
            "import pytest\ndef pytest_collection_modifyitems(items):\n"
            "    for item in items: item.add_marker(pytest.mark.xdist_group('contract-group'))\n"
        )
        extra = ["-n", "2", "--dist=loadgroup"]
    result = contract_project.runpytest_subprocess(
        "-q", "-k", "assert_derivation_is_idempotent", f"--junitxml={junit}", *extra
    )
    assert result.ret == pytest.ExitCode.OK
    total = sum(len(app.nodeids or []) for app in inventory.applications.values())
    assert skipped_tests(inventory, [junit]) == total - result.parseoutcomes()["passed"]
    assert skipped_tests(inventory, [junit, junit]) == skipped_tests(inventory, [junit])
