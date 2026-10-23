"""Exercise the terminal contract verdict through real generated pytest suites."""

import pytest


@pytest.fixture
def contract_project(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makepyfile("""
from pytest_obligation import Claim, NotApplicable, ObligationContract, Profile, due_work_contract_suite
from pytest_obligation.references.in_memory import reference_derivation_binding

contract = ObligationContract(
    name="catalog derivation",
    profiles={**{p: NotApplicable("Outside this contract.") for p in Profile}, Profile.F: Claim()},
    derivation=reference_derivation_binding,
)
@due_work_contract_suite(contract)
class TestCatalog:
    pass
""")
    return pytester


@pytest.mark.parametrize("workers", [0, 2])
def test_complete_contract_is_verified_without_a_json_file(contract_project: pytest.Pytester, workers: int) -> None:
    result = contract_project.runpytest_subprocess("-q", "-n", str(workers), "--due-work-summary")
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "*contract evidence (collected suites only)*",
            "  VERIFIED: catalog derivation*",
            "*A*not applicable*Outside this contract.*",
            "*F Fact-Derived Obligations: VERIFIED;*",
        ]
    )


@pytest.mark.parametrize("workers", [0, 2])
def test_teardown_failure_cannot_be_reported_as_a_verified_contract(
    contract_project: pytest.Pytester, workers: int
) -> None:
    contract_project.makeconftest("""
import pytest
@pytest.fixture(autouse=True)
def broken_teardown():
    yield
    raise RuntimeError("cleanup failed")
""")
    result = contract_project.runpytest_subprocess("-q", "-n", str(workers), "--due-work-summary")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*UNVERIFIED: catalog derivation*", "*teardown=failed*"])
    assert "  VERIFIED:" not in result.stdout.str()


def test_deselecting_the_entire_contract_keeps_its_missing_evidence(contract_project: pytest.Pytester) -> None:
    result = contract_project.runpytest_subprocess("-q", "-k", "no_such_case", "--due-work-summary")
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    result.stdout.fnmatch_lines(["*UNVERIFIED: catalog derivation*", "*deselected*"])


def test_selecting_one_node_reports_the_expected_uncollected_proofs(contract_project: pytest.Pytester) -> None:
    source = next(contract_project.path.glob("test_*.py"))
    result = contract_project.runpytest_subprocess(
        f"{source}::TestCatalog::test_due_work_contract[F-assert_derivation_is_idempotent]",
        "-q",
        "--due-work-summary",
    )
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*UNVERIFIED: catalog derivation*", "*not collected*"])


@pytest.mark.parametrize("workers", [0, 2])
def test_a_failed_extra_proof_cannot_leave_a_verified_contract(contract_project: pytest.Pytester, workers: int) -> None:
    source = next(contract_project.path.glob("test_*.py"))
    text = source.read_text()
    text = (
        text.replace(
            "from pytest_obligation import Claim,",
            "from pytest_obligation import ExtraProof, Claim,",
        )
        .replace(
            "from pytest_obligation.references.in_memory import reference_derivation_binding",
            "from pytest_obligation.references.in_memory import reference_derivation_binding, "
            "assert_the_reference_capability_exists",
        )
        .replace(
            "derivation=reference_derivation_binding,",
            "derivation=reference_derivation_binding,\n"
            "    extras=(ExtraProof(name='required-extra', run=assert_the_reference_capability_exists),),",
        )
    )
    source.write_text(text)
    result = contract_project.runpytest_subprocess("-q", "-n", str(workers), "--due-work-summary")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*UNVERIFIED: catalog derivation*", "*required-extra*call=failed*"])


def test_a_single_assessment_teardown_failure_blocks_the_contract_verdict(contract_project: pytest.Pytester) -> None:
    contract_project.makeconftest("""
import pytest
@pytest.fixture(autouse=True)
def broken_assessment(request):
    yield
    if request.node.callspec.params["case"].id == "A-not_applicable":
        raise RuntimeError("assessment cleanup failed")
""")
    result = contract_project.runpytest_subprocess("-q", "--due-work-summary")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*UNVERIFIED: catalog derivation*", "*A-not_applicable*teardown=failed*"])
