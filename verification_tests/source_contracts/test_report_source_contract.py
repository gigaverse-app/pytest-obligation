"""Current-source proofs plus independent real Pydantic boundary observations."""

import json
from pathlib import Path

import pytest
from veripy.backends.dafny.driver import verify_dafny_file
from veripy.backends.dafny.native_heap import DafnyHeapBackend
from veripy.frontend.extract import parse_source

from pytest_obligation.profiles import reporting
from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
from scripts.source_contracts.mutations import mutate_source

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "package/src/pytest_obligation/profiles/reporting.py"


def suite(*, complete: bool = False, exploration: bool = False) -> SuiteCoverage:
    def case():
        return CaseEvidence(
            family="delivery",
            collected=complete,
            selected=complete,
            outcomes={phase: ["passed"] for phase in ("setup", "call", "teardown")} if complete else {},
            durations=[0.125] if complete else [],
        )

    return SuiteCoverage(
        name="independent expectation",
        profiles={
            "A": ProfileCoverage(
                title="Admission", assessment=Assessment(state="claimed"), cases={"one": case(), "two": case()}
            )
        },
        additional_cases={"extra": case()},
        exploration={"history": case()} if exploration else None,
    )


def proof(source: str, work: Path):
    encoded = DafnyHeapBackend().encode(
        source, parse_source(source), module_name="production_reporting", proof_lemmas=[]
    )
    work.mkdir(parents=True, exist_ok=True)
    output = work / "reporting.dfy"
    output.write_text(encoded.dafny_source)
    result = verify_dafny_file(output, encoded.line_map)
    (work / "backend.log").write_text(result.raw or result.error or "")
    retained = (
        ROOT
        / ".artifacts/source-contracts/backend"
        / (work.name if work.name in ("early-evidence-write", "replace-retained-case") else "production")
    )
    retained.mkdir(parents=True, exist_ok=True)
    (retained / "source.py").write_text(source)
    (retained / "reporting.dfy").write_text(encoded.dafny_source)
    (retained / "backend.log").write_text(result.raw or result.error or "")
    (retained / "translation.json").write_text(json.dumps(encoded.translation, indent=2) + "\n")
    (retained / "line-map.json").write_text(json.dumps(encoded.line_map, indent=2) + "\n")
    return result, encoded


def test_actual_source_proves_and_imports_current_tree(tmp_path):
    assert Path(reporting.__file__).resolve() == SOURCE.resolve()
    result, encoded = proof(SOURCE.read_text(), tmp_path)
    assert result.ok, result.raw
    assert encoded.methods == ["merge_reports"]
    assert len(encoded.translation["write_effects"]) == 7
    assert all(
        event["identity_preserving"] and event["evidence_monotone"] for event in encoded.translation["write_effects"]
    )


@pytest.mark.parametrize("mutant", ["early-evidence-write", "replace-retained-case"])
def test_actual_source_semantic_mutants_fail_dafny(mutant, tmp_path):
    source = mutate_source(SOURCE.read_text(), mutant)
    # Execute compilation, not just parse: failures must be semantic proof errors.
    compile(source, str(tmp_path / f"{mutant}.py"), "exec")
    result, _ = proof(source, tmp_path / mutant)
    assert not result.ok and result.error is None, result.raw
    assert any(d.py_line is not None and "assertion" in d.message for d in result.diagnostics), result.raw


@pytest.mark.parametrize("exploration", [False, True])
def test_compatible_accumulation_retains_every_borrowed_identity(exploration):
    initial = suite(exploration=exploration)
    shard = suite(complete=True, exploration=exploration)
    target = {"main": initial}
    profile = initial.profiles["A"]
    groups = [*initial.case_groups(), initial.exploration or {}]
    references = [
        (mapping, key, case, case.outcomes, case.failures, case.durations)
        for mapping in groups
        for key, case in mapping.items()
    ]
    incoming_before = shard.model_dump(round_trip=True)
    for repetition in range(1, 4):
        reporting.merge_reports(target, {"main": shard, "new": suite(complete=True, exploration=exploration)})
        assert target["main"] is initial and initial.profiles["A"] is profile
        for mapping, key, case, outcomes, failures, durations in references:
            assert mapping[key] is case
            assert case.outcomes is outcomes and case.failures is failures and case.durations is durations
            assert case.collected and case.selected
            assert case.outcomes == {phase: ["passed"] * repetition for phase in ("setup", "call", "teardown")}
            assert case.durations == [0.125] * repetition
        assert initial.verified
        assert shard.model_dump(round_trip=True) == incoming_before


@pytest.mark.parametrize("mismatch", ["family", "declaration", "case-set", "source", "assessment", "name"])
def test_late_validation_rejection_preserves_both_inputs(mismatch):
    target = {"first": suite(), "last": suite()}
    shard = {"first": suite(complete=True), "new": suite(complete=True), "last": suite(complete=True)}
    last = shard["last"]
    case = last.profiles["A"].cases["two"]
    if mismatch == "family":
        case.family = "incompatible"
    elif mismatch == "declaration":
        case.declaration = "not applicable"
    elif mismatch == "case-set":
        last.additional_cases.clear()
    elif mismatch == "source":
        from pytest_obligation.profiles.coverage import SourceLocation

        last.source = SourceLocation(path="different.py", line=1)
    elif mismatch == "assessment":
        last.profiles["A"].assessment = Assessment(state="declined")
    else:
        last.name = "other"
    references = dict(target)
    before = {key: value.model_dump(round_trip=True) for key, value in target.items()}
    incoming_before = {key: value.model_dump(round_trip=True) for key, value in shard.items()}
    with pytest.raises(AssertionError):
        reporting.merge_reports(target, shard)
    assert {key: value.model_dump(round_trip=True) for key, value in target.items()} == before
    assert {key: value.model_dump(round_trip=True) for key, value in shard.items()} == incoming_before
    assert all(target[key] is value for key, value in references.items())


def test_external_case_group_contract_yields_borrowed_maps_without_writes():
    report = suite(exploration=True)
    before = report.model_dump(round_trip=True)
    groups = list(report.case_groups())
    assert len(groups) == 2
    assert groups[0] is report.additional_cases
    assert groups[1] is report.profiles["A"].cases
    assert report.model_dump(round_trip=True) == before
