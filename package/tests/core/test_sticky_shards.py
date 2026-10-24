"""Sharded reporting preserves real evidence and exposes incomplete inputs."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.core.test_profile_summary import contract_project  # noqa: F401


def test_selective_execution_keeps_an_unimported_application_visible(contract_project: pytest.Pytester) -> None:  # noqa: F811
    executed = next(contract_project.path.glob("test_*.py"))
    contract_project.makepyfile(
        test_unselected="""
raise RuntimeError('Unselected application must not be imported for the report')
from pytest_obligation import due_work_contract_suite, ObligationContract
@due_work_contract_suite(ObligationContract(name='Unselected billing'))
class TestBilling: pass
"""
    )
    report = contract_project.path / "shard-1.json"
    result = contract_project.runpytest_subprocess(str(executed), "-q", f"--due-work-profile-report={report}")
    assert result.ret == pytest.ExitCode.OK
    output = contract_project.path / "report.md"
    rendered = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            str(report),
            "--expected-reports",
            "1",
            "--output",
            str(output),
            "--application-path",
            ".",
            "--test-outcome",
            "success",
        ],
        cwd=contract_project.path,
        capture_output=True,
        text=True,
    )
    assert rendered.returncode == 0, rendered.stderr
    body = output.read_text()
    assert "catalog derivation" in body and "**1** applications with results" in body
    assert "2 applications" in body
    assert "Unselected billing" in body and "Not run" in body
    assert "0 blocked checks" in body
    assert "Evidence unavailable" not in body


@pytest.mark.parametrize("damage", ["none", "missing", "invalid", "disagreement"])
def test_shards_reach_one_report(contract_project: pytest.Pytester, damage: str) -> None:  # noqa: F811
    first = contract_project.path / "shard-1.json"
    second = contract_project.path / "shard-2.json"
    for path, expression in (
        (first, "assert_derivation_is_idempotent"),
        (second, "not assert_derivation_is_idempotent"),
    ):
        result = contract_project.runpytest_subprocess("-q", "-k", expression, f"--due-work-profile-report={path}")
        assert result.ret == pytest.ExitCode.OK
    if damage == "missing":
        second.unlink()
    elif damage == "invalid":
        second.write_text("{broken")
    elif damage == "disagreement":
        second.write_text(second.read_text().replace('"name":', '"name": "foreign", "ignored":', 1))
    output = contract_project.path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            str(contract_project.path / "shard-*.json"),
            "--expected-reports",
            "2",
            "--output",
            str(output),
            "--test-outcome",
            "success",
        ],
        env={**os.environ, "GITHUB_STEP_SUMMARY": str(contract_project.path / "summary.md")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    body = output.read_text()
    assert "Owed work is discovered from stored facts" in body
    if damage == "none":
        assert "Evidence unavailable" not in body
        assert "0 blocked checks" in body and "0 failures" in body and "0 rejected bindings" in body
        assert "1 supported guarantees" in body
    else:
        assert "Evidence unavailable" in body
        assert "✅ All claims" not in body


def test_empty_glob_is_reviewable(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            str(tmp_path / "shard-*.json"),
            "--expected-reports",
            "2",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Evidence unavailable" in output.read_text()
