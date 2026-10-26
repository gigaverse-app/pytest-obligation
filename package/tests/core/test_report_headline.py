"""The headline's one counting rule, at every point of a run's lifecycle."""

from pathlib import Path
from typing import Any

import pytest

from pytest_obligation.profiles.coverage import CaseEvidence, SourceLocation, SuiteCoverage
from pytest_obligation.reporting.artifact import TestOutcome
from pytest_obligation.reporting.compose import merge_evidence, render_merged
from pytest_obligation.reporting.inventory import Application, ApplicationInventory
from pytest_obligation.reporting.markdown import headline, render

PASSED = {"setup": ["passed"], "call": ["passed"], "teardown": ["passed"]}


def _suite(*cases: CaseEvidence) -> SuiteCoverage:
    return SuiteCoverage(name="orders", profiles={}, additional_cases={f"c{i}": c for i, c in enumerate(cases)})


RAN = _suite(CaseEvidence(family="derive", collected=True, selected=True, outcomes=PASSED))
#: A deselected check counts as skipped, and as blocked: the contract did not get its result.
RAN_WITH_A_SKIP = _suite(
    CaseEvidence(family="derive", collected=True, selected=True, outcomes=PASSED),
    CaseEvidence(family="replay", collected=True, selected=False),
)
NOTHING_RECORDED = _suite(CaseEvidence(family="derive", collected=True, selected=True))
#: An application the inventory declares and no report covers.
DECLARED = ApplicationInventory(
    applications={
        "tests.Orders": Application(name="orders", source=SourceLocation(path="t.py", line=1)),
        "tests.Billing": Application(name="billing", source=SourceLocation(path="t.py", line=9)),
    }
)


def _headline(
    reports: dict[str, SuiteCoverage],
    *,
    inventory: ApplicationInventory | None = None,
    unavailable: str = "",
    test_outcome: str = "success",
    running: bool = False,
    collected_skips: int | None = None,
    skips_unknown: str = "",
) -> dict[str, int | None]:
    return headline(
        reports,
        inventory=inventory,
        unavailable=unavailable,
        test_outcome=test_outcome,
        running=running,
        collected_skips=collected_skips,
        skips_unknown=skips_unknown,
    ).values


@pytest.mark.parametrize(
    ("reports", "overrides", "expected"),
    [
        pytest.param(
            {"tests.Orders": RAN_WITH_A_SKIP},
            {},
            dict(applications=1, passed=1, failed=0, blocked=1, gaps=0, rejected=0, skipped=1),
            id="succeeded without an inventory: every count, skips included, covers the reports",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {},
            dict(applications=1, passed=1, failed=0, blocked=0, gaps=0, rejected=0, skipped=0),
            id="succeeded with nothing skipped: a final zero",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {"running": True},
            dict(applications=1, passed=1, failed=None, blocked=None, gaps=None, rejected=None, skipped=None),
            id="still running: no zero is final, recorded counts stay",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {"test_outcome": "failure"},
            dict(applications=1, passed=1, failed=0, blocked=0, gaps=0, rejected=0, skipped=0),
            id="failed after recording everything: the zeros are results",
        ),
        pytest.param(
            {"tests.Orders": NOTHING_RECORDED},
            {"test_outcome": "failure"},
            dict(applications=1, passed=None, failed=None, blocked=1, gaps=None, rejected=None, skipped=None),
            id="failed before any check ran: zeros are unknown",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {"test_outcome": "cancelled"},
            dict(applications=1, passed=1, failed=None, blocked=None, gaps=None, rejected=None, skipped=None),
            id="cancelled: nothing proves the zeros",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {"unavailable": "Expected 2 reports; found 1."},
            dict(applications=1, passed=1, failed=None, blocked=None, gaps=None, rejected=None, skipped=None),
            id="a report missing after success: no green zero for what it would have held",
        ),
        pytest.param(
            {},
            {"test_outcome": "unknown", "unavailable": "The evidence artifact has no valid render manifest."},
            dict(applications=None, passed=None, failed=None, blocked=None, gaps=None, rejected=None, skipped=None),
            id="nothing readable: even the application count is unknown",
        ),
        pytest.param(
            {"tests.Orders": RAN_WITH_A_SKIP},
            {"inventory": DECLARED},
            dict(applications=2, passed=1, failed=0, blocked=1, gaps=0, rejected=0, skipped=None),
            id="a declared application without a report: skips are a lower bound",
        ),
        pytest.param(
            {"tests.Orders": RAN_WITH_A_SKIP},
            {"inventory": DECLARED, "collected_skips": 7},
            dict(applications=2, passed=1, failed=0, blocked=1, gaps=0, rejected=0, skipped=7),
            id="JUnit joined to the collected inventory: the exact skip count",
        ),
        pytest.param(
            {"tests.Orders": RAN},
            {"skips_unknown": "Expected JUnit reports are missing."},
            dict(applications=1, passed=1, failed=0, blocked=0, gaps=0, rejected=0, skipped=None),
            id="JUnit could not classify skips: only the skip count is unknown",
        ),
    ],
)
def test_each_count_is_what_the_evidence_holds_and_unknown_only_where_it_cannot_say(
    reports: dict[str, SuiteCoverage], overrides: dict[str, Any], expected: dict[str, int | None]
) -> None:
    assert _headline(reports, **overrides) == expected


def test_a_lower_bound_skip_count_says_how_many_are_known_and_why() -> None:
    shown = headline(
        {"tests.Orders": RAN_WITH_A_SKIP},
        inventory=DECLARED,
        unavailable="",
        test_outcome="success",
        running=False,
        collected_skips=None,
        skips_unknown="",
    )
    assert (shown.skips_known, shown.skips_unknown) == (1, "Applications without a report have no measured test count.")
    body = render({"tests.Orders": RAN_WITH_A_SKIP}, inventory=DECLARED, test_outcome="success")
    # No status box applies, so the line under the counts explains the one ?.
    assert "> [!" not in body
    assert "<sub>Skipped tests: **1 known**. Applications without a report have no measured test count.</sub>" in body
    assert "Checks skipped: **1 known**." in body


def test_the_smoke_report_without_an_inventory_shows_a_number_for_skips() -> None:
    """pytest-obligation's own sticky reports without an inventory; its skip count is still known."""
    body = render({"tests.Orders": RAN_WITH_A_SKIP}, graphics=True, test_outcome="success")
    assert 'alt="1 skipped tests"' in body
    assert "unknown" not in body.split("<details>")[0]
    assert "Checks skipped: **1**." in body


@pytest.mark.parametrize("test_outcome", ["success", "failure"])
def test_junit_problems_leave_the_evidence_available_and_only_the_skip_count_unknown(
    tmp_path: Path, test_outcome: TestOutcome
) -> None:
    report = tmp_path / "shard-1.json"
    report.write_text('{"tests.Orders": ' + RAN.model_dump_json() + "}")
    inventory = ApplicationInventory(applications={"tests.Orders": DECLARED.applications["tests.Orders"]})
    evidence = merge_evidence(
        [report], expected_reports=1, test_outcome=test_outcome, inventory=inventory, problems=[], junit=[]
    )
    assert evidence.unavailable == ""
    assert evidence.skips_unknown == "Expected JUnit reports are missing."
    body = render_merged(
        evidence,
        test_outcome=test_outcome,
        inventory=inventory,
        run_url="",
        source="",
        asset_ref="main",
        repository_url="",
        revision="",
        graphics=False,
    )
    assert "Evidence unavailable" not in body
    assert "**1 applications · 1 contract checks passed · 0 contract failures" in body
    assert "? skipped tests**" in body
    # A failed step gets its own box, and nothing else.
    assert [line for line in body.splitlines() if line.startswith("> [!")] == (
        ["> [!CAUTION]"] if test_outcome == "failure" else []
    )
