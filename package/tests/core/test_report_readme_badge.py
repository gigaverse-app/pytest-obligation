"""A report kept in a README between markers, and its headline as a shields.io endpoint badge."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pytest_obligation.debt import DebtEntry
from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SourceLocation, SuiteCoverage
from pytest_obligation.reporting import __main__ as report_cli
from pytest_obligation.reporting import readme
from pytest_obligation.reporting.badge import badge

PASSED = {"setup": ["passed"], "call": ["passed"], "teardown": ["passed"]}
KNOWN = {"setup": ["passed"], "call": ["xfail"], "teardown": ["passed"]}
FAILED = {"setup": ["passed"], "call": ["failed"], "teardown": ["passed"]}
XPASS = {"setup": ["passed"], "call": ["xpass"], "teardown": ["passed"]}
DOCUMENT = f"# A fork\n\nIntroduction.\n\n{readme.START}\nold report\n{readme.END}\n\nThe rest.\n"


def _case(outcomes: dict[str, list[str]], seconds: float = 0.5, *, known: bool = False) -> CaseEvidence:
    return CaseEvidence(
        family="history",
        collected=True,
        selected=True,
        outcomes=outcomes,
        durations=[seconds],
        debt=DebtEntry(case="history", kind="known-defect", ticket="https://example.com/1", reason="Diverges.")
        if known
        else None,
    )


def _suite(*cases: CaseEvidence, seconds: float = 3.0) -> SuiteCoverage:
    return SuiteCoverage(
        name="worker",
        source=SourceLocation(path="tests/test_worker.py", line=7),
        session_seconds=seconds,
        profiles={
            "A": ProfileCoverage(
                title="recovery",
                assessment=Assessment(state="claimed"),
                cases={f"case-{index}": case for index, case in enumerate(cases)},
            )
        },
    )


def test_embed_replaces_only_the_text_between_the_markers() -> None:
    updated = readme.embed(DOCUMENT, "new report\n")
    assert updated == f"# A fork\n\nIntroduction.\n\n{readme.START}\nnew report\n{readme.END}\n\nThe rest.\n"
    assert readme.embed(updated, "new report") == updated


@pytest.mark.parametrize(
    "document",
    [
        "no markers at all\n",
        f"{readme.START}\nonly the start\n",
        f"{readme.START}\n{readme.START}\n{readme.END}\n",
        f"{readme.END}\nreversed\n{readme.START}\n",
    ],
    ids=["none", "no-end", "two-starts", "reversed"],
)
def test_a_document_without_one_ordered_pair_of_markers_is_refused(document: str) -> None:
    with pytest.raises(ValueError, match="must contain"):
        readme.embed(document, "report")


def test_update_reports_whether_the_document_changed(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(DOCUMENT, encoding="utf-8")
    assert readme.update(path, "report") is True
    assert readme.update(path, "report") is False


@pytest.mark.parametrize(
    ("cases", "outcome", "message", "color"),
    [
        ([_case(PASSED), _case(PASSED)], "success", "2 passed", "brightgreen"),
        ([_case(PASSED), _case(KNOWN, known=True)], "success", "1 passed · 1 known defect", "yellow"),
        ([_case(PASSED), _case(XPASS, known=True)], "failure", "1 passed · 1 blocked", "red"),
        ([_case(PASSED), _case(XPASS, known=True)], "success", "1 passed · 1 blocked", "orange"),
        ([_case(KNOWN, known=True), _case(FAILED)], "failure", "0 passed · 1 known defect · 1 failing", "red"),
    ],
    ids=["all-passed", "known-defect", "fixed-upstream-fails-the-run", "unexpected-pass", "unexpected-failure"],
)
def test_the_badge_is_the_reports_headline(cases: list[CaseEvidence], outcome: str, message: str, color: str) -> None:
    value = badge({"worker": _suite(*cases)}, unavailable="", test_outcome=outcome)  # type: ignore[arg-type]
    assert (value.message, value.color) == (message, color)


def test_missing_evidence_never_shows_a_green_badge() -> None:
    assert badge({}, unavailable="", test_outcome="success").color == "lightgrey"
    unavailable = badge({"worker": _suite(_case(PASSED))}, unavailable="Expected 2 reports.", test_outcome="success")
    assert (unavailable.message, unavailable.color) == ("evidence unavailable", "lightgrey")


def _run(root: Path, suite: SuiteCoverage, run: int) -> None:
    (root / "profiles.json").write_bytes(TypeAdapter(dict[str, SuiteCoverage]).dump_json({"tests.Worker": suite}))
    report_cli.main(
        [
            "--input",
            str(root / "profiles.json"),
            "--output",
            str(root / f"run-{run}" / "report.md"),
            "--source",
            f"run {run}",
            "--run-url",
            f"https://github.com/owner/app/actions/runs/{run}",
            "--repository-url",
            "https://github.com/owner/app",
            "--revision",
            str(run) * 40,
            "--test-outcome",
            "success",
            "--readme",
            str(root / "README.md"),
            "--readme-source",
            "daily run against upstream main",
            "--badge",
            str(root / "badge.json"),
        ]
    )


def test_the_readme_copy_changes_only_when_the_evidence_does(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(DOCUMENT, encoding="utf-8")
    _run(tmp_path, _suite(_case(PASSED), _case(KNOWN, known=True), seconds=3.0), run=1)
    first = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert first.startswith("# A fork\n\nIntroduction.\n\n") and first.endswith(f"{readme.END}\n\nThe rest.\n")
    assert "known expected" in first and "daily run against upstream main" in first
    # The PR comment keeps run-specific times, the run link and the commit-pinned source link; the README does not.
    comment = (tmp_path / "run-1" / "report.md").read_text(encoding="utf-8")
    for run_specific in ("elapsed", "summed check time", "actions/runs/1", "blob/" + "1" * 40):
        assert run_specific in comment and run_specific not in first
    assert json.loads((tmp_path / "badge.json").read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "label": "pytest-obligation",
        "message": "1 passed · 1 known defect",
        "color": "yellow",
    }

    # Another run with other times, run link and revision leaves the document as it was.
    _run(tmp_path, _suite(_case(PASSED, 0.9), _case(KNOWN, 1.2, known=True), seconds=7.5), run=2)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == first

    # A finding that moves does change it.
    _run(tmp_path, _suite(_case(PASSED), _case(PASSED)), run=3)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") != first
    assert json.loads((tmp_path / "badge.json").read_text(encoding="utf-8"))["color"] == "brightgreen"


def test_a_readme_without_markers_fails_the_report_in_words(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# no markers\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run(tmp_path, _suite(_case(PASSED)), run=1)
    assert "must contain <!-- pytest-obligation:start -->" in capsys.readouterr().err
