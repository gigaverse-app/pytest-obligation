"""A proven exemption is visible evidence with a deliberately narrow claim."""

from html import unescape

import pytest
from pydantic import TypeAdapter

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.reporting.inventory import discover
from pytest_obligation.reporting.markdown import render


def test_static_inventory_keeps_unexecuted_exemptions(tmp_path):
    (tmp_path / "test_exemption.py").write_text(
        "raise RuntimeError('inventory must not import')\n"
        "from pytest_obligation import exempt_due_work_suite as exempt\n"
        "@exempt(source, reason=reason, prove=proof)\nclass TestCacheExemption: pass\n"
    )
    inventory = discover(tmp_path, ["."])
    assert "test_exemption.TestCacheExemption" in inventory.applications
    body = unescape(render({}, inventory=inventory))
    assert "TestCacheExemption" in body and "Not run" in body


@pytest.mark.parametrize("workers", [0, 2])
@pytest.mark.parametrize("scenario", ["passed", "failed", "teardown", "filtered", "mixed"])
def test_exemption_proof_evidence_is_preserved(pytester, workers, scenario):
    pytester.makepyfile(
        cache_app=f"""
entries = set()
def publish(): pass
def strand():
    entries.clear()
    return 7
def observe(key): return key in entries
def absorb(key):
    if {scenario!r} != 'failed': entries.add(key)
"""
    )
    pytester.makeconftest(f"""
import pytest
from pytest_obligation.host import Host, configure
configure(Host(production_packages=frozenset({{'cache_app'}})))
@pytest.fixture(autouse=True)
def teardown_control():
    yield
    if {scenario!r} == 'teardown': raise RuntimeError('cleanup failed')
""")
    pytester.makepyfile(
        test_exemption="""
from pytest_obligation import DueWorkSource, LossIsAbsorbedElsewhere, exempt_due_work_suite
import cache_app
@exempt_due_work_suite(
    DueWorkSource(cache_app.publish),
    reason='The next request re-derives the summary from persisted facts',
    prove=LossIsAbsorbedElsewhere(strand=cache_app.strand, observe=cache_app.observe, absorb=cache_app.absorb),
)
class TestCacheExemption: pass
"""
    )
    if scenario == "mixed":
        source = pytester.path / "test_exemption.py"
        text = source.read_text()
        text = """from pytest_obligation import Claim, NotApplicable, ObligationContract, Profile, due_work_contract_suite
from pytest_obligation.references.in_memory import reference_derivation_binding
contract = ObligationContract(name='Derivation with an exempt shortcut',
    profiles={**{p: NotApplicable('Outside this specimen') for p in Profile}, Profile.F: Claim()},
    derivation=reference_derivation_binding)
""" + text.replace("@exempt_due_work_suite(", "@due_work_contract_suite(contract)\n@exempt_due_work_suite(")
        source.write_text(text)
    destination = pytester.path / "report.json"
    args = ["-q", "-n", str(workers), f"--due-work-profile-report={destination}", "--due-work-summary"]
    if scenario == "filtered":
        args += ["-k", "no_matching_case"]
    result = pytester.runpytest_subprocess(*args)
    expected_exit = (
        pytest.ExitCode.OK
        if scenario in ("passed", "mixed")
        else pytest.ExitCode.NO_TESTS_COLLECTED
        if scenario == "filtered"
        else pytest.ExitCode.TESTS_FAILED
    )
    assert result.ret == expected_exit
    reports = TypeAdapter(dict[str, SuiteCoverage]).validate_json(destination.read_bytes())
    assert set(reports) == {"test_exemption.TestCacheExemption"}
    report = reports["test_exemption.TestCacheExemption"]
    if scenario == "mixed":
        assert report.profiles["F"].verified
        assert report.profiles["A"].assessment.state == "not applicable"
    else:
        assert set(report.profiles) == {"exemption"}
    assert report.verified == (scenario in ("passed", "mixed"))
    cases = report.profiles["exemption"].cases
    assert list(cases) == ["test_the_exemption_holds"]
    case = cases["test_the_exemption_holds"]
    assert case.selected == (scenario != "filtered")
    body = unescape(render(reports))
    assert "Handoff exemption" in body
    assert "The next request re-derives the summary from persisted facts" in body
    if scenario != "mixed":
        assert "Unfinished work gets recovered" not in body
    if scenario in ("failed", "teardown"):
        assert case.failures
