"""Declared defects, missing assessments and exclusions must not become one to-do list."""

import pytest

from pytest_obligation.debt import DebtEntry
from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
from pytest_obligation.profiles.reporting import merge_reports
from pytest_obligation.reporting.markdown import counts, render


def specimen() -> SuiteCoverage:
    return SuiteCoverage(
        name="membership",
        profiles={
            "E": ProfileCoverage(
                title="Convergence",
                assessment=Assessment(state="claimed"),
                cases={
                    "late": CaseEvidence(
                        family="interleaving",
                        collected=True,
                        selected=True,
                        outcomes={"call": ["xfail"]},
                        debt=DebtEntry(
                            case="late",
                            kind="known-defect",
                            reason="An older grant restores access.",
                            ticket="https://linear.app/example/issue/BE-1",
                        ),
                    ),
                },
                families={"snapshot": Assessment(state="not assessed", because="No snapshot binding yet.")},
            ),
            "I": ProfileCoverage(
                title="Admission", assessment=Assessment(state="not assessed", because="No admission binding yet.")
            ),
            "B": ProfileCoverage(
                title="Ownership", assessment=Assessment(state="declined", because="A database lock owns this work.")
            ),
            "D": ProfileCoverage(
                title="Retention", assessment=Assessment(state="not applicable", because="No retention process exists.")
            ),
        },
    )


def test_actionable_sections_preserve_reasons_and_ticket_links() -> None:
    body = render({"membership": specimen()})
    assert "Known defects" in body
    assert "An older grant restores access." in body
    assert "[https://linear.app/example/issue/BE-1](https://linear.app/example/issue/BE-1)" in body
    assert "Unassessed guarantees and scenarios" in body
    assert "No snapshot binding yet." in body
    assert "No admission binding yet." in body
    assert "Deliberate exclusions" in body
    assert "A database lock owns this work." in body
    assert "No retention process exists." in body
    assert "Run the missing checks, or repair their setup/cleanup." not in body


def test_known_defect_still_counts_as_a_guarantee_gap_after_families_are_assessed() -> None:
    suite = specimen()
    suite.profiles = {"E": suite.profiles["E"]}
    suite.profiles["E"].families = {}
    assert counts(suite)["gaps"] == 1


def test_undeclared_expected_failure_is_not_invented_as_a_known_defect() -> None:
    suite = SuiteCoverage(
        name="old report",
        profiles={},
        additional_cases={
            "legacy": CaseEvidence(family="unknown", collected=True, selected=True, outcomes={"call": ["xfail"]}),
        },
    )
    body = render({"old": suite})
    assert "**Known defects" not in body
    assert "classification was not reported" in body


@pytest.mark.parametrize(
    "ticket", ["javascript:alert(1)", 'https://example.com/"bad', "https://example.com/)bad", "https://[", "BE-1"]
)
def test_ticket_links_do_not_render_unsafe_urls_or_invent_issue_trackers(ticket: str) -> None:
    suite = specimen()
    case = suite.profiles["E"].cases["late"]
    assert case.debt is not None
    case.debt = case.debt.model_copy(update={"ticket": ticket})
    assert f"]({ticket})" not in render({"suite": suite})


def test_shards_must_agree_on_debt_metadata() -> None:
    suite = specimen()
    incoming = suite.model_copy(deep=True)
    incoming.profiles["E"].cases["late"].debt = None
    with pytest.raises(AssertionError, match="debt"):
        merge_reports({"suite": suite}, {"suite": incoming})


def test_identical_exclusions_are_not_repeated_but_distinct_family_reasons_survive() -> None:
    suite = specimen()
    reason = "No independent receipt application API."
    other = "The legacy callback still needs separate review."
    profile = suite.profiles["E"]
    profile.assessment = Assessment(state="declined", because=reason)
    profile.families = {
        "snapshot": profile.assessment,
        "receipt": Assessment(state="not applicable", because=other),
    }
    body = render({"suite": suite})
    assert body.count(reason) == 1
    assert body.count(other) == 1
    assert body.count("No retention process exists.") == 1


def test_supported_guarantee_keeps_family_exclusion_in_one_decision_section() -> None:
    suite = specimen()
    profile = suite.profiles["E"]
    profile.cases = {
        "ok": CaseEvidence(
            family="replay",
            collected=True,
            selected=True,
            outcomes={phase: ["passed"] for phase in ("setup", "call", "teardown")},
        )
    }
    reason = "This application has no snapshot API."
    profile.families = {"snapshot": Assessment(state="not applicable", because=reason)}
    assert profile.verified
    body = render({"suite": suite})
    assert body.count(reason) == 1
    assert "1 supported guarantees" in body
