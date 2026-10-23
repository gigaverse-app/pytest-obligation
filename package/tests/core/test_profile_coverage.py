"""Reports cannot promote declarations, filtered runs, or failed teardown into verified guarantees."""

import os
from pathlib import Path

import pytest

from pytest_obligation.profiles.coverage import (
    Assessment,
    CaseEvidence,
    ProfileCoverage,
    SuiteCoverage,
)
from pytest_obligation.profiles.reporting import merge_reports


def coverage() -> ProfileCoverage:
    return ProfileCoverage(
        title="Harmless Replay",
        assessment=Assessment(state="claimed"),
        cases={"first": CaseEvidence(family="replay"), "duplicate": CaseEvidence(family="replay")},
    )


@pytest.mark.parametrize(
    "missing",
    ["collection", "selection", "setup", "call", "teardown", "family", "declined family", "unfinished repeat"],
)
def test_verification_requires_complete_executed_evidence(missing: str) -> None:
    profile = coverage()
    for case in profile.cases.values():
        case.collected = True
        case.selected = True
        case.outcomes = {phase: ["passed"] for phase in ("setup", "call", "teardown")}
    assert profile.verified
    first = profile.cases["first"]
    if missing == "collection":
        first.collected = False
    elif missing == "selection":
        first.selected = False
    elif missing == "unfinished repeat":
        first.outcomes["setup"].append("passed")
    elif missing == "declined family":
        profile.families["declined"] = Assessment(state="declined", because="Not claimed by this adopter.")
    elif missing == "family":
        profile.families["unbound"] = Assessment(state="not assessed", because="Missing production binding.")
    else:
        first.outcomes[missing] = ["failed"]
    assert not profile.verified


@pytest.mark.parametrize("outcome", ["skipped", "xfail", "xpass", "failed"])
def test_nonpassing_call_cannot_verify_the_profile_or_contract(outcome: str) -> None:
    profile = coverage()
    for case in profile.cases.values():
        case.collected = case.selected = True
        case.outcomes = {phase: ["passed"] for phase in ("setup", "call", "teardown")}
    suite = SuiteCoverage(name="effect", profiles={"H": profile})
    assert suite.verified
    profile.cases["first"].outcomes["call"] = [outcome]
    assert not suite.verified


def test_a_contract_with_no_claims_is_not_vacuously_verified() -> None:
    suite = SuiteCoverage(
        name="unclaimed", profiles={"H": ProfileCoverage(title="Replay", assessment=Assessment(state="not applicable"))}
    )
    assert not suite.verified


def test_distributed_results_cannot_erase_failure_or_change_expected_coverage() -> None:
    initial = SuiteCoverage(name="effect", profiles={"H": coverage()})
    incoming = initial.model_copy(deep=True)
    incoming.profiles["H"].cases["first"].outcomes = {"call": ["failed"]}
    initial.profiles["H"].cases["first"].outcomes = {"call": ["passed"]}
    merged = {"suite": initial}
    merge_reports(merged, {"suite": incoming})
    assert initial.profiles["H"].cases["first"].outcomes["call"] == ["passed", "failed"]
    assert not initial.profiles["H"].verified
    incoming.profiles["H"].cases.pop("duplicate")
    with pytest.raises(AssertionError, match="workers disagree"):
        merge_reports(merged, {"suite": incoming})


@pytest.mark.parametrize("workers", [0, 2])
def test_native_filtered_report_keeps_unselected_proofs_and_missing_families(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, workers: int
) -> None:
    import json

    monkeypatch.setenv("DUE_WORK_REFERENCE_OUTCOME", "conforming")
    monkeypatch.setenv("PYTHONPATH", str(pytestconfig.rootpath), prepend=os.pathsep)
    specimen = Path(__file__).parent / "contract" / "reference_contract_cases.py"
    destination = pytester.path / "profiles.json"
    result = pytester.runpytest_subprocess(
        str(specimen) + "::TestInMemoryReferenceContract",
        "-q",
        "-n",
        str(workers),
        "-k",
        "assert_current_snapshot_writes",
        f"--due-work-profile-report={destination}",
        "--due-work-summary",
    )
    assert result.ret == pytest.ExitCode.OK
    report = next(iter(json.loads(destination.read_text()).values()))
    convergence = report["profiles"]["E"]
    assert sum(case["selected"] for case in convergence["cases"].values()) == 1
    assert len(convergence["cases"]) > 1
    assert convergence["families"]["IN_FLIGHT"]["state"] == "not assessed"
    assert not convergence["verified"]
    assert report["profiles"]["I"]["assessment"]["state"] == "not applicable"
    result.stdout.fnmatch_lines(
        [
            "*UNVERIFIED: in-memory reference*",
            "*IN_FLIGHT: not assessed*",
            "*deselected*",
        ]
    )
    assert not report["verified"]


def test_executable_gap_and_decline_probes_are_reported_without_becoming_verified(pytester: pytest.Pytester) -> None:
    import json

    pytester.makepyfile("""
from functools import partial
from pytest_obligation import Adoption, Decline, ObligationContract, KnownGap, NotApplicable, Profile, due_work_contract_suite
from pytest_obligation.references.in_memory import assert_the_reference_capability_exists, assert_self_test_probe_fires
contract = ObligationContract(
    name="executed assessment controls", adoption=Adoption.LEGACY,
    profiles={**{p: NotApplicable("Outside this reporting control.") for p in Profile},
        Profile.A: Decline("The alternative behavior has a real probe.", prove=partial(assert_self_test_probe_fires, [])),
        Profile.I: KnownGap("The reference capability is deliberately missing.", detect=assert_the_reference_capability_exists)},
)
@due_work_contract_suite(contract)
class TestAssessmentProbes:
    pass
""")
    destination = pytester.path / "profiles.json"
    result = pytester.runpytest_subprocess("-q", f"--due-work-profile-report={destination}", "--due-work-summary")
    assert result.ret == pytest.ExitCode.OK
    report = next(iter(json.loads(destination.read_text()).values()))["profiles"]
    assert report["I"]["cases"]["I-known_gap"]["outcomes"]["call"] == ["xfail"]
    assert report["A"]["cases"]["A-declined"]["passed"]
    assert not report["A"]["verified"] and not report["I"]["verified"]
    result.stdout.fnmatch_lines(
        [
            "*UNVERIFIED: executed assessment controls*",
            "*A*declined*The alternative behavior has a real probe.*",
            "*I*known gap*The reference capability is deliberately missing.*",
            "*call=xfail*",
        ]
    )
