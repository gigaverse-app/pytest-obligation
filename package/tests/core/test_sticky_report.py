"""Exercise report conclusions through real generated tests, then the public renderer."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
from pytest_obligation.profiles.failures import failure_evidence
from pytest_obligation.profiles.reporting import merge_reports
from pytest_obligation.recovery import RecoveryCandidateEvidence, RecoveryDiagnostics
from pytest_obligation.reporting.markdown import MAX_BODY, counts, render
from tests.core.test_profile_summary import contract_project  # noqa: F401 - explicit shared pytester fixture


@pytest.mark.parametrize("mode", ["complete", "filtered", "binding", "failed", "teardown"])
@pytest.mark.parametrize("workers", [0, 2])
def test_real_pytest_evidence_reaches_the_sticky(
    contract_project: pytest.Pytester,  # noqa: F811 - explicitly imported shared fixture
    mode: str,
    workers: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(contract_project.path))
    if mode == "failed":
        source = next(contract_project.path.glob("test_*.py"))
        source.write_text(
            source.read_text()
            .replace("from pytest_obligation import Claim,", "from pytest_obligation import ExtraProof, Claim,")
            .replace(
                "from pytest_obligation.references.in_memory import reference_derivation_binding",
                "from pytest_obligation.references.in_memory import reference_derivation_binding, assert_the_reference_capability_exists",
            )
            .replace(
                "derivation=reference_derivation_binding,",
                "derivation=reference_derivation_binding, extras=(ExtraProof(name='missing-capability', run=assert_the_reference_capability_exists),),",
            )
        )
    if mode in ("binding", "teardown"):
        fault = {
            "binding": """
from pytest_obligation.binding import assert_test_binding_delegates_to_production
assert_test_binding_delegates_to_production(adopter='orders', field='select',
    binding=lambda: None, production_shape='orders.select')
""",
            "teardown": "raise RuntimeError('database cleanup failed')",
        }[mode]
        # Fixture failures travel through the actual pytest hooks; no fabricated report JSON.
        contract_project.makeconftest(
            "import pytest\n@pytest.fixture(autouse=True)\ndef fail_one_case(request):\n"
            "    if request.node.callspec.params['case'].id.startswith('F-'):\n"
            + ("        yield\n" if mode == "teardown" else "")
            + "\n".join("        " + line for line in fault.strip().splitlines())
            + ("\n    else:\n        yield\n" if mode == "teardown" else "\n")
        )
    path = contract_project.path / "profiles.json"
    args = ["-q", "-n", str(workers), f"--due-work-profile-report={path}"]
    if mode == "filtered":
        args += ["-k", "assert_derivation_is_idempotent"]
    result = contract_project.runpytest_subprocess(*args)
    reports = TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes())
    body = render(reports)
    suite = next(iter(reports.values()))
    assert suite.source is not None and suite.source.kind == "contract setup"
    assert suite.source.path.endswith(".py")
    assert suite.session_seconds is not None and suite.session_seconds > 0
    assert suite.exploration == {}
    executed = [c for group in suite.case_groups() for c in group.values() if c.outcomes]
    assert executed and all(c.durations for c in executed)
    assert "summed check time" in body
    if mode == "complete":
        assert result.ret == pytest.ExitCode.OK
        assert suite.verified
        assert counts(suite)["passed"] > 0
        assert not any(counts(suite)[k] for k in ("failed", "rejected", "blocked", "gaps"))
    else:
        assert "✅ All claims" not in body
        assert not next(iter(reports.values())).verified
        if mode == "filtered":
            assert result.ret == pytest.ExitCode.OK
            assert "Test filtered out" in body
            assert "Run the missing" in body
        elif mode == "binding":
            assert "Test binding rejected" in body
            assert "references no production" in body
            assert "Connect the binding to production code" in body
        else:
            assert result.ret == pytest.ExitCode.TESTS_FAILED
            assert ("**Check failed**" if mode == "failed" else "Test setup/cleanup failed") in body


def test_known_gap_probe_is_explicit_but_never_a_failed_behavior_claim(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
from pytest_obligation import Adoption, KnownGap, NotApplicable, ObligationContract, Profile, due_work_contract_suite
from pytest_obligation.references.in_memory import assert_the_reference_capability_exists
contract = ObligationContract(name='orders', adoption=Adoption.LEGACY,
    profiles={**{p: NotApplicable('Outside this application contract.') for p in Profile},
              Profile.A: KnownGap('Recovery worker has not been implemented.', detect=assert_the_reference_capability_exists)})
@due_work_contract_suite(contract)
class TestOrders: pass
""")
    path = pytester.path / "profiles.json"
    result = pytester.runpytest_subprocess("-q", f"--due-work-profile-report={path}")
    assert result.ret == pytest.ExitCode.OK
    body = render(TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes()))
    assert "Known gap declared" in body
    assert "Application reason: Recovery worker" in body
    assert "✅ All claims" not in body
    assert "🔴 1 checks failed" not in body


def test_failure_state_roundtrips_and_survives_worker_merge() -> None:
    diagnostics = RecoveryDiagnostics(
        name="orders",
        stage="resumed",
        ticks=7,
        candidates=[
            RecoveryCandidateEvidence(
                identity="order-17",
                role="poisoned",
                owed=True,
                progressed=False,
                fault_count=1,
                details={"status": "pending"},
            )
        ],
    )
    error = AssertionError("deferred work was abandoned")
    error.add_note("Recovery diagnostics:\n" + diagnostics.model_dump_json())
    case = CaseEvidence(
        family="recovery",
        collected=True,
        selected=True,
        outcomes={"setup": ["passed"], "call": ["failed"], "teardown": ["passed"]},
        failures=[failure_evidence(error, "call")],
    )
    suite = SuiteCoverage(name="receipts", profiles={}, additional_cases={"extra-recovery": case})
    adapter = TypeAdapter(dict[str, SuiteCoverage])
    restored = adapter.validate_json(adapter.dump_json({"tests.Orders": suite}))
    merged = {
        "tests.Orders": SuiteCoverage(
            name="receipts", profiles={}, additional_cases={"extra-recovery": CaseEvidence(family="recovery")}
        )
    }
    merge_reports(merged, restored)
    body = render(merged)
    assert "1 failures" in body
    assert "resumed" in body and "**7**" in body and "order-17" in body and "status=pending" in body
    assert not merged["tests.Orders"].verified


def test_stored_verdicts_and_application_text_cannot_forge_a_green_report() -> None:
    suite = SuiteCoverage(
        name="orders</summary><img src=x>@everyone|[click](bad)",
        profiles={
            "F": ProfileCoverage(
                title="ignored application title",
                assessment=Assessment(state="claimed"),
                cases={"missing": CaseEvidence(family="derive")},
            )
        },
    )
    data = suite.model_dump()
    data["verified"] = True
    data["profiles"]["F"]["verified"] = True
    restored = SuiteCoverage.model_validate(data)
    body = render({"test_app.Orders": restored})
    assert "✅ All claims" not in body
    assert "<img src=x>" not in body and "@everyone" not in body and "[click](bad)" not in body
    assert "Owed work is discovered from stored facts" in body


@pytest.mark.parametrize("content", [None, "{broken", '{"unknown": {}}'])
def test_cli_preserves_reviewable_unavailable_evidence(tmp_path: Path, content: str | None) -> None:
    source, output, summary = (tmp_path / name for name in ("report.json", "report.md", "summary.md"))
    if content is not None:
        source.write_text(content)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "pytest_obligation.reporting", "--input", str(source), "--output", str(output)],
        env={**os.environ, "GITHUB_STEP_SUMMARY": str(summary)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Evidence unavailable" in output.read_text(encoding="utf-8")
    assert summary.read_text(encoding="utf-8").strip() == output.read_text(encoding="utf-8").strip()


def test_comment_limit_preserves_verdict_and_explicit_omission() -> None:
    reports = {
        f"suite{i}": SuiteCoverage(
            name="orders" * 300,
            profiles={
                "A": ProfileCoverage(
                    title="recovery", assessment=Assessment(state="known gap", because="long reason " * 300)
                )
            },
        )
        for i in range(100)
    }
    body = render(reports)
    assert len(body) <= MAX_BODY
    assert "Coverage gaps" in body
    assert "omitted" in body and body.count("<details>") == body.count("</details>")


def test_report_accepts_prior_version_without_optional_failure_metadata() -> None:
    data = {
        "tests.Orders": {
            "name": "orders",
            "profiles": {},
            "additional_cases": {
                "replay": {"family": "replay", "collected": True, "selected": True, "outcomes": {"call": ["failed"]}}
            },
        }
    }
    body = render(TypeAdapter(dict[str, SuiteCoverage]).validate_json(json.dumps(data)))
    assert "1 failures" in body


def test_failed_test_step_remains_red_when_no_contract_failure_was_recorded() -> None:
    body = render({}, test_outcome="failure")
    assert "🔴 Test step failed" in body
    assert "0 failed contract checks recorded" in body


def test_broken_optional_diagnostics_preserve_the_original_failure_category() -> None:
    class BrokenMessage(AssertionError):
        def __str__(self) -> str:
            raise RuntimeError("message formatter failed")

    error = BrokenMessage()
    error.add_note("Recovery diagnostics:\n{invalid")
    evidence = failure_evidence(error, "call")
    assert evidence.kind == "check"
    assert evidence.message == "BrokenMessage: Exception message unavailable"
    assert evidence.recovery == []


def test_sources_outside_the_checkout_never_get_a_github_link(
    contract_project: pytest.Pytester,  # noqa: F811 - explicitly imported shared fixture
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "other-checkout"))
    path = contract_project.path / "profiles.json"
    result = contract_project.runpytest_subprocess("-q", f"--due-work-profile-report={path}")
    assert result.ret == pytest.ExitCode.OK
    reports = TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes())
    assert next(iter(reports.values())).source is None
    assert "[View contract" not in render(reports, repository_url="https://github.com/example/app", revision="a" * 40)
