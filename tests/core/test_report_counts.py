"""Display classifications preserve distinct evidence units and actionable priority."""

import re

import pytest

from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SourceLocation, SuiteCoverage
from pytest_obligation.profiles.failures import FailureEvidence
from pytest_obligation.reporting.markdown import counts, render


def test_counts_partition_checks_without_counting_shared_profile_cases_twice() -> None:
    passed = CaseEvidence(
        family="example",
        collected=True,
        selected=True,
        outcomes={phase: ["passed"] for phase in ("setup", "call", "teardown")},
    )
    rejected = CaseEvidence(
        family="binding",
        collected=True,
        selected=True,
        outcomes={"setup": ["failed"]},
        failures=[FailureEvidence(phase="setup", kind="binding", message="bad binding")],
    )
    failed = CaseEvidence(family="behavior", collected=True, selected=True, outcomes={"call": ["failed"]})
    profile = ProfileCoverage(title="claim", assessment=Assessment(state="claimed"), cases={"shared": passed})
    suite = SuiteCoverage(
        name="orders",
        profiles={
            "A": profile,
            "B": profile,
            "C": ProfileCoverage(title="gap", assessment=Assessment(state="declined", because="No remote receipts")),
            "D": ProfileCoverage(title="excluded", assessment=Assessment(state="not applicable", because="No pruning")),
        },
        additional_cases={"rejected": rejected, "failed": failed, "missing": CaseEvidence(family="example")},
    )
    assert counts(suite) == {"passed": 1, "failed": 1, "blocked": 1, "gaps": 0, "rejected": 1}


def test_all_passed_cases_cannot_hide_unassessed_scenario_family() -> None:
    case = CaseEvidence(
        family="example",
        collected=True,
        selected=True,
        outcomes={phase: ["passed"] for phase in ("setup", "call", "teardown")},
    )
    suite = SuiteCoverage(
        name="orders",
        profiles={
            "E": ProfileCoverage(
                title="convergence",
                assessment=Assessment(state="claimed"),
                cases={"case": case},
                families={"one": Assessment(state="not assessed"), "two": Assessment(state="known gap")},
            )
        },
    )
    assert counts(suite)["gaps"] == 1
    assert "Coverage gaps" in render({"orders": suite})


@pytest.mark.parametrize("number", [1, 3, 4])
def test_application_rows_keep_counts_visible_and_flatten_small_reports(number: int) -> None:
    suites = {f"app{i}": SuiteCoverage(name=f"application {i}", profiles={}) for i in range(number)}
    body = render(suites, graphics=True)
    assert ("most actionable first" in body) == (number > 3)
    summaries = re.findall(r'<summary><strong>.*?<div align="right">.*?</summary>', body)
    assert len(summaries) == (number if number <= 3 else 0)
    if number > 3:
        assert all(f"| application {i} |" in body for i in range(number))
    for summary in summaries:
        assert summary.count("<img ") > 1
        assert "applications" not in summary
        assert "good-0-dark.svg" in summary
        assert 'alt="0 passed"' in summary and 'alt="0 rejected"' in summary


def test_actionability_order_and_failure_classification() -> None:
    reports = {}
    for key, case in {
        "blocked": CaseEvidence(family="f"),
        "failed": CaseEvidence(family="f", outcomes={"call": ["failed"]}),
        "rejected": CaseEvidence(
            family="f",
            outcomes={"setup": ["failed"]},
            failures=[FailureEvidence(kind="binding", phase="setup", message="bad")],
        ),
    }.items():
        reports[key] = SuiteCoverage(name=key, profiles={}, additional_cases={key: case})
    body = render(reports)
    assert body.index("<code>failed") < body.index("<code>rejected") < body.index("<code>blocked")


@pytest.mark.parametrize(
    "path, linked",
    [("tests/contracts.py", True), ("../private.py", False), ("C:/secret.py", False), ("/etc/secrets.py", False)],
)
def test_contract_source_links_are_pinned_and_contained(path: str, linked: bool) -> None:
    suite = SuiteCoverage(name="orders", profiles={}, source=SourceLocation(path=path, line=7, kind="contract setup"))
    body = render({"orders": suite}, repository_url="https://github.com/example/app", revision="a" * 40)
    assert ("[View contract setup]" in body) == linked
    if linked:
        assert f"/blob/{'a' * 40}/tests/contracts.py#L7" in body


def test_disabled_exploration_does_not_count_as_blocked_execution() -> None:
    suite = SuiteCoverage(
        name="orders", profiles={}, exploration={"schedule": CaseEvidence(family="receipts", collected=True)}
    )
    assert counts(suite)["blocked"] == 0
    assert "Disabled or filtered out" in render({"orders": suite})
    assert suite.exploration is not None
    suite.exploration["schedule"].selected = True
    assert counts(suite)["blocked"] == 1


def test_older_reports_do_not_invent_timing_or_exploration() -> None:
    body = render({"orders": SuiteCoverage(name="orders", profiles={})})
    assert "Test time: not reported" in body
    assert "Hypothesis · Not reported" in body
    assert "Contract source: not reported" in body
