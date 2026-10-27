"""Independent CI lanes contribute evidence without hiding an incomplete lane."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
from pytest_obligation.reporting.__main__ import main
from pytest_obligation.reporting.artifact import RenderManifest, load, stage
from pytest_obligation.reporting.compose import merge_evidence

REVISION = "a" * 40


def lane(root: Path, name: str, selected: str, *, outcome: str = "passed", revision: str = REVISION) -> Path:
    root.mkdir(exist_ok=True)
    report = root / f"{name}.json"
    cases = {
        key: CaseEvidence(
            family="delivery",
            collected=True,
            selected=key == selected,
            outcomes={"setup": ["passed"], "call": [outcome], "teardown": ["passed"]} if key == selected else {},
        )
        for key in ("unit", "worker")
    }
    report.write_bytes(
        TypeAdapter(dict[str, SuiteCoverage]).dump_json(
            {
                "tests.TestDelivery": SuiteCoverage(
                    name="Delivery",
                    profiles={
                        "A": ProfileCoverage(title="Recovery", assessment=Assessment(state="claimed"), cases=cases),
                    },
                ),
            }
        )
    )
    directory = root / name
    stage(
        directory,
        RenderManifest(
            expected_reports=1,
            test_outcome="failure" if outcome == "failed" else "success",
            graphics=False,
            revision=revision,
        ),
        reports=[report],
        junit=[],
        inventory=None,
        markdown="not trusted",
    )
    return directory


def aggregate(root: Path, *lanes: Path) -> tuple[str, Path]:
    artifact = root / "aggregate"
    main(
        [
            "--input",
            str(root / "no-raw-reports-*.json"),
            "--test-outcome",
            "skipped",
            "--output",
            str(root / "report.md"),
            "--revision",
            REVISION,
            "--stage-artifact",
            str(artifact),
            *(arg for path in lanes for arg in ("--evidence-input", str(path))),
        ]
    )
    return (root / "report.md").read_text(), artifact


def evidence(artifact: Path):
    staged = load(artifact)
    assert staged.manifest is not None
    return merge_evidence(
        staged.reports,
        expected_reports=staged.manifest.expected_reports,
        test_outcome=staged.manifest.test_outcome,
        inventory=None,
        problems=staged.problems,
        junit=None,
    )


def test_complementary_jobs_complete_each_check_once(tmp_path: Path):
    unit = lane(tmp_path, "units", "unit")
    worker = lane(tmp_path, "workers", "worker")
    _, artifact = aggregate(tmp_path, unit, worker, worker)
    merged = evidence(artifact)
    assert not merged.unavailable
    cases = merged.reports["tests.TestDelivery"].profiles["A"].cases
    assert all(case.passed for case in cases.values())
    assert cases["worker"].outcomes["call"] == ["passed"]


@pytest.mark.parametrize("missing", ["directory", "report", "revision"])
def test_unavailable_lane_preserves_other_evidence_after_restaging(tmp_path: Path, missing: str):
    unit = lane(tmp_path, "units", "unit")
    worker = lane(tmp_path, "workers", "worker", revision="b" * 40 if missing == "revision" else REVISION)
    if missing == "directory":
        worker = tmp_path / "absent"
    elif missing == "report":
        (worker / "reports" / "0001.json").unlink()
    _, artifact = aggregate(tmp_path, unit, worker)
    merged = evidence(artifact)
    assert merged.unavailable
    cases = merged.reports["tests.TestDelivery"].profiles["A"].cases
    assert cases["unit"].passed
    assert not cases["worker"].passed


def test_failed_lane_remains_failed_when_another_job_passes(tmp_path: Path):
    unit = lane(tmp_path, "units", "unit")
    worker = lane(tmp_path, "workers", "worker", outcome="failed")
    _, artifact = aggregate(tmp_path, unit, worker)
    manifest = load(artifact).manifest
    assert manifest is not None and manifest.test_outcome == "failure"
    assert not evidence(artifact).reports["tests.TestDelivery"].verified


def test_a_passing_repeat_cannot_hide_another_jobs_failure(tmp_path: Path):
    failing = lane(tmp_path, "failing", "worker", outcome="failed")
    passing = lane(tmp_path, "passing", "worker")
    _, artifact = aggregate(tmp_path, passing, failing)
    merged = evidence(artifact)
    case = merged.reports["tests.TestDelivery"].profiles["A"].cases["worker"]
    assert not case.passed
    assert "failed" in case.outcomes["call"]


def test_an_extra_report_cannot_replace_another_lanes_missing_report(tmp_path: Path):
    unit = lane(tmp_path, "units", "unit")
    worker = lane(tmp_path, "workers", "worker")
    (unit / "reports" / "extra.json").write_bytes((unit / "reports" / "0001.json").read_bytes())
    (worker / "reports" / "0001.json").unlink()
    _, artifact = aggregate(tmp_path, unit, worker)
    assert evidence(artifact).unavailable
    manifest = load(artifact).manifest
    assert manifest is not None and manifest.version == 2 and manifest.evidence_unavailable


def test_separate_pytest_jobs_supply_complementary_generated_checks(pytester: pytest.Pytester):
    pytester.makepyfile("""
from pytest_obligation import Claim, NotApplicable, ObligationContract, Profile, due_work_contract_suite
from pytest_obligation.references.in_memory import reference_derivation_binding

@due_work_contract_suite(ObligationContract(
    name="catalog recovery", derivation=reference_derivation_binding,
    profiles={**{p: NotApplicable("Outside this contract.") for p in Profile}, Profile.F: Claim()},
))
class TestCatalog:
    pass
""")
    lanes = []
    for name, selection in (("unit", "production_bound"), ("worker", "not production_bound")):
        report = pytester.path / f"{name}.json"
        result = pytester.runpytest_subprocess("-q", "-k", selection, "--due-work-profile-report", str(report))
        assert result.ret == 0
        directory = pytester.path / name
        stage(
            directory,
            RenderManifest(expected_reports=1, test_outcome="success", graphics=False, revision=REVISION),
            reports=[report],
            junit=[],
            inventory=None,
            markdown="",
        )
        lanes.append(directory)
    _, artifact = aggregate(pytester.path, *lanes)
    merged = evidence(artifact)
    assert not merged.unavailable
    assert len(merged.reports) == 1
    suite = next(iter(merged.reports.values()))
    assert suite.profiles["F"].verified
    assert all(case.outcomes["call"] == ["passed"] for case in suite.profiles["F"].cases.values())
