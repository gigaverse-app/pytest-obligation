"""Selection-only checks stay visible without claiming full recovery coverage."""

import json
from html import unescape

import pytest
from pydantic import TypeAdapter

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.reporting.markdown import render


@pytest.mark.parametrize("workers", [0, 2])
@pytest.mark.parametrize("scenario", ["passed", "known defect", "failed", "teardown", "filtered", "unscheduled"])
def test_generated_selection_evidence_is_reported(pytester, workers, scenario):
    # This self-test host supplies controlled planner observations. The actual
    # suite generator, pytest execution, xdist merge and sticky renderer all run.
    pytester.makepyfile(
        sample_selection="""
def due_work():
    # ARRANGE: one row in a controlled reporting specimen.
    # REAL PRODUCTION: this specimen module owns the selection.
    # EXTERNAL SEAM: the self-test inspector supplies planner observations.
    # OBSERVE: emitted JSON and actual pytest outcomes are checked externally.
    return [1]
"""
    )
    pytester.makeconftest(f"""
import pytest
from pytest_obligation.host import Host, configure
class Inspector:
    def understands(self, selection): return isinstance(selection, list)
    def index_served(self, selection): return ({scenario!r} not in ('known defect', 'failed'), 'missing index')
    def replica_read(self, selection): return None
configure(Host(production_packages=frozenset({{'sample_selection'}}), selection_inspectors=(Inspector(),)))
@pytest.fixture(autouse=True)
def teardown_control(request):
    yield
    if {scenario!r} == 'teardown' and request.node.callspec.params['case'].id == 'assert_selection_is_index_served':
        raise RuntimeError('cleanup failed')
""")
    source = pytester.makepyfile(
        test_selection=f"""
from pytest_obligation import Adoption, ScheduledSelection, scheduled_selection_suite
from sample_selection import due_work
selection = ScheduledSelection(
    name='Hourly repair query', due_work=due_work, adoption=Adoption.LEGACY,
    gaps={{'assert_selection_is_index_served': 'Missing index'}} if {scenario!r} == 'known defect' else {{}},
    assert_scheduled=None if {scenario!r} == 'unscheduled' else lambda: None,
    unscheduled_because='Driven by an external runbook' if {scenario!r} == 'unscheduled' else None,
)
@scheduled_selection_suite(selection)
class TestSelection: pass
"""
    )
    suite = f"{source.stem}.TestSelection"
    baseline = pytester.path / "debt.json"
    baseline.write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "suite": suite,
                        "debt": [
                            {
                                "case": "assert_selection_is_index_served",
                                "kind": "known-defect",
                                "reason": "Missing index",
                                "ticket": "https://example.com/BUG-1",
                            }
                        ],
                    }
                ]
            }
            if scenario == "known defect"
            else {"suites": []}
        )
    )
    destination = pytester.path / "report.json"
    args = ["-q", "-n", str(workers), f"--due-work-profile-report={destination}", "--due-work-summary"]
    if scenario == "filtered":
        args += ["-k", "actually_scheduled"]
    if scenario == "known defect":
        args += [f"--due-work-debt-baseline={baseline}"]
    result = pytester.runpytest_subprocess(*args)
    assert result.ret == (pytest.ExitCode.TESTS_FAILED if scenario in ("failed", "teardown") else pytest.ExitCode.OK)
    reports = TypeAdapter(dict[str, SuiteCoverage]).validate_json(destination.read_bytes())
    assert suite in reports, "scheduled selections must not disappear from the report"
    report = reports[suite]
    assert set(report.profiles) == {"selection"}, "selection checks do not establish full profile A"
    assert report.verified == (scenario == "passed")
    profile = report.profiles["selection"]
    assert len(profile.cases) >= 3
    body = unescape(render(reports))
    assert "Scheduled selection and loop" in body
    assert "Unfinished work gets recovered" not in body
    if scenario == "known defect":
        case = profile.cases["assert_selection_is_index_served"]
        assert case.debt is not None
        assert case.debt.ticket == "https://example.com/BUG-1"
        assert case.outcomes["call"] == ["xfail"]
        assert "Known defects" in body and "Missing index" in body
    if scenario == "filtered":
        assert not profile.cases["assert_selection_is_index_served"].selected
    if scenario == "unscheduled":
        assert profile.families["schedule evidence"].state == "declined"
        assert "Driven by an external runbook" in body
