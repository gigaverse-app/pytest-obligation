"""Per-fault diagnostics retain their meaning without serializing application data."""

import pytest

from pytest_obligation.crash_histories import Findings, HistoryRun, assert_findings_hold
from pytest_obligation.history_evidence import capture_histories


def test_a_changed_stage_is_reported_before_the_findings_assertion_fails() -> None:
    def run(label: str, outcome: str, interrupted: bool = True) -> HistoryRun:
        return HistoryRun(label=label, before="pending", midway="pending", after=outcome, interrupted=interrupted)

    runs = [
        run("normal operation", "secret delivered", False),
        run("after commit", "secret delivered"),
        run("lost publish", "secret lost"),
        run("new regression", "secret duplicate"),
        run("not reached", "secret delivered", False),
    ]
    with capture_histories() as evidence:
        with pytest.raises(AssertionError):
            assert_findings_hold("place order", runs, Findings("secret delivered", {"lost publish": "secret lost"}))
    assert [row["status"] for row in evidence] == [
        "baseline",
        "matches baseline",
        "matches pinned divergence",
        "changed from pinned outcome",
        "fault not reached",
    ]
    assert "secret" not in str(evidence)


@pytest.mark.parametrize("workers", [0, 2])
def test_stage_evidence_survives_xfail_xdist_and_junit(pytester: pytest.Pytester, workers: int) -> None:
    pytester.makepyfile("""
import pytest
from pytest_obligation.crash_histories import Findings, HistoryRun, HistoriesDiverged, assert_findings_hold, assert_histories_converge

@pytest.mark.due_work
@pytest.mark.xfail(strict=True, raises=HistoriesDiverged, reason="known lost publish")
def test_history():
    runs = [HistoryRun(label="normal operation", before=None, midway="private payload", after="private payload"),
            HistoryRun(label="publish lost", before=None, midway=None, after=None, interrupted=True)]
    assert_findings_hold("send", runs, Findings("private payload", {"publish lost": None}))
    assert_histories_converge("send", runs)
""")
    result = pytester.runpytest_subprocess("-q", "-n", str(workers), "--due-work-summary", "--junitxml=results.xml")
    result.assert_outcomes(xfailed=1)
    result.stdout.fnmatch_lines(["*observed history stages*", "*send | publish lost: matches pinned divergence*"])
    import json
    from xml.etree import ElementTree

    document = ElementTree.parse(pytester.path / "results.xml")
    payload = document.find(".//property[@name='obligation_histories']")
    assert payload is not None
    rows = json.loads(payload.attrib["value"])
    assert rows[-1] == {"history": "send", "stage": "publish lost", "status": "matches pinned divergence"}
    assert "private payload" not in payload.attrib["value"]
