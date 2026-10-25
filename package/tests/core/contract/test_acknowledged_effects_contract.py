"""Profile C's acknowledged-effect binding, declared on a domain contract."""

import pytest

from pytest_obligation.contract import (
    Adoption,
    Claim,
    ObligationContract,
    ObligationContractDesignError,
    Profile,
    suite_cases,
)
from pytest_obligation.references.in_memory import reference_acknowledged_effect_binding
from tests.core.contract.declarations import dispositions


def _annotated_acknowledged_teardown():
    # ARRANGE — the reference binding builds a fresh owed in-memory teardown.
    # REAL PRODUCTION — this self-test delegates to the harness reference teardown.
    # EXTERNAL SEAM — the reference's AsyncTasks provider holds and applies acknowledgements.
    # OBSERVE — the reference reads its owed set, acknowledgement count and provider state.
    return reference_acknowledged_effect_binding()


def test_profile_c_can_be_claimed_through_acknowledged_effects_alone() -> None:
    contract = ObligationContract(
        name="acknowledged teardown",
        profiles=dispositions(C=Claim()),
        acknowledged_effects={"delete users": _annotated_acknowledged_teardown},
    )

    cases = [param.values[0] for param in suite_cases(contract) if param.values[0].profile is Profile.C]

    assert {case.id for case in cases} == {
        "C-delete users-assert_acknowledgement_bindings_are_production_bound",
        "C-delete users-assert_an_acknowledgement_does_not_discharge",
        "C-delete users-assert_an_applied_acknowledgement_discharges",
    }
    for case in cases:
        case.run()


def test_an_unnamed_acknowledged_effect_is_refused() -> None:
    with pytest.raises(ObligationContractDesignError, match="acknowledged_effects name each acknowledging effect"):
        ObligationContract(
            name="unnamed acknowledgement",
            profiles=dispositions(C=Claim()),
            acknowledged_effects={" ": _annotated_acknowledged_teardown},
        )


def test_the_acknowledgement_binding_guard_cannot_be_waived() -> None:
    with pytest.raises(ObligationContractDesignError, match="names a binding-integrity proof"):
        ObligationContract(
            name="waived guard",
            profiles=dispositions(
                C=Claim(gaps={"assert_acknowledgement_bindings_are_production_bound": "self-test"}),
            ),
            acknowledged_effects={"delete users": _annotated_acknowledged_teardown},
        )


def test_a_legacy_gap_on_the_discharge_proof_is_accepted() -> None:
    contract = ObligationContract(
        name="legacy teardown",
        adoption=Adoption.LEGACY,
        profiles=dispositions(
            C=Claim(gaps={"assert_an_acknowledgement_does_not_discharge": "the teardown trusts the task reply"}),
        ),
        acknowledged_effects={"delete users": _annotated_acknowledged_teardown},
    )

    assert any(
        param.values[0].id.endswith("assert_an_acknowledgement_does_not_discharge") for param in suite_cases(contract)
    )
