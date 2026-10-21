"""Runtime inventories, rather than names or declarations, determine owed proofs."""

from dataclasses import dataclass
from functools import wraps

import pytest

from pytest_obligation.collection import assert_collected_proofs
from pytest_obligation.contract import Adoption, Claim, NotApplicable, ObligationContract, Profile, contract_cases
from pytest_obligation.models import ObligationContractDesignError
from pytest_obligation.poison import PoisonStalled
from pytest_obligation.profiles.automatic_recovery import DueWorkSweep
from pytest_obligation.recovery import validate_recovery_bindings


@dataclass
class _Runtime:
    def cleanup(self):
        pass


def test_exact_runtime_inventory_accepts_fresh_bound_methods():
    runtime = _Runtime()
    validate_recovery_bindings({"cleanup": runtime.cleanup}, {"cleanup": runtime.cleanup})


@pytest.mark.parametrize("defect", ["missing", "stale", "other-receiver", "wrapped", "other-callback"])
def test_missing_or_incorrect_declaration_cannot_certify_a_runtime_step(defect):
    runtime = _Runtime()
    declared = {"cleanup": runtime.cleanup}
    if defect == "missing":
        declared.clear()
    elif defect == "stale":
        declared["retired"] = runtime.cleanup
    elif defect == "other-receiver":
        declared["cleanup"] = _Runtime().cleanup
    elif defect == "wrapped":

        @wraps(runtime.cleanup)
        def wrapper():
            runtime.cleanup()

        declared["cleanup"] = wrapper
    else:
        declared["cleanup"] = lambda: None
    with pytest.raises(ObligationContractDesignError):
        validate_recovery_bindings({"cleanup": runtime.cleanup}, declared)


def test_removed_generated_case_fails_collection():
    with pytest.raises(AssertionError, match="lost collected proofs"):
        assert_collected_proofs({"cleanup[healthy]", "cleanup[poisoned]"}, {"cleanup[healthy]"}, "native")


def test_legacy_page_gap_catches_only_the_declared_defect():
    def sweep() -> DueWorkSweep:
        # ARRANGE: metadata-only declaration; this fixture must never run.
        # REAL PRODUCTION: the contract compiler runs in the enclosing test.
        # EXTERNAL SEAM: none.
        # OBSERVE: the compiled case must catch only its declared defect type.
        raise AssertionError("collection must not execute a product fixture")

    proof = "assert_a_poisoned_page_does_not_starve_or_abandon_work"
    contract = ObligationContract(
        name="legacy page",
        adoption=Adoption.LEGACY,
        sweep=sweep,
        profiles={
            profile: Claim(gaps={f"{proof}[stalled]": "the known bare loop aborts on its first failed row"})
            if profile is Profile.A
            else NotApplicable("unrelated to this collection control")
            for profile in Profile
        },
    )
    case = next(parameter for parameter in contract_cases(contract) if parameter.id == f"A-{proof}")
    mark = next(mark for mark in case.marks if mark.name == "xfail")
    assert mark.kwargs["strict"] is True
    assert mark.kwargs["raises"] is PoisonStalled
