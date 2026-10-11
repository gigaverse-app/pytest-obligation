"""Run real child sessions: baseline policy holds before filters and across xdist."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from pytest_obligation.debt import BASELINE

SOURCE = """
from pytest_obligation.contract import (
    NotAssessed, Profile, SafetyContract, safety_contract_suite,
)
@safety_contract_suite(SafetyContract(name="control", profiles={
    p: NotAssessed(because="The production seam has not been bound yet.") for p in (Profile.H, Profile.J)
}))
class TestDebt:
    pass
"""


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "test_debt.py").write_text(SOURCE)
    (tmp_path / "pytest.ini").write_text("[pytest]\ndue_work_debt_baseline = " + BASELINE.as_posix())
    return tmp_path


@pytest.mark.parametrize("selection", [[], ["-k", "REPLAY_SAFE_EXECUTION"], ["--deselect", "test_debt.py::TestDebt"]])
def test_new_debt_fails_before_filtering(project: Path, selection: list[str]) -> None:
    result = run(project, "--collect-only", "test_debt.py", *selection)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "New expected failures (2)" in result.stdout


def test_node_narrowing_does_not_compare_an_incomplete_suite(project: Path) -> None:
    result = run(project, "--collect-only", "test_debt.py::TestDebt::test_safety_contract")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("workers", [[], ["-n", "2"]])
def test_matching_baseline_and_removed_debt(project: Path, workers: list[str]) -> None:
    entries = [
        dict(case=f"{p}-not_assessed", kind="binding-debt", reason="unbound")
        for p in ("REPLAY_SAFE_EXECUTION", "BOUNDED_RETRY")
    ]
    path = project / BASELINE
    path.write_text(yaml.safe_dump({"suites": [{"suite": "test_debt.TestDebt", "debt": entries}]}))
    result = run(project, "test_debt.py", *workers)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 xfailed" in result.stdout
    entries.append(dict(case="removed", kind="binding-debt", reason="stale"))
    path.write_text(yaml.safe_dump({"suites": [{"suite": "test_debt.TestDebt", "debt": entries}]}))
    result = run(project, "test_debt.py", *workers)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "Stale entries (1)" in result.stdout


def test_policy_is_opt_in(project: Path) -> None:
    (project / "pytest.ini").write_text("[pytest]\n")
    result = run(project, "test_debt.py")
    assert result.returncode == 0, result.stdout + result.stderr
