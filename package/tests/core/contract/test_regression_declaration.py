from contextlib import nullcontext
from unittest.mock import patch

import pytest

from pytest_obligation.contract import ExtraProof, NotApplicable, ObligationContract, Profile, contract_cases
from pytest_obligation.profiles.fact_derived_obligations import (
    assert_unrecorded_obligation_is_discovered,
)
from pytest_obligation.references.in_memory import (
    EdgeTriggeredDeriver,
    MaterialisingDeriver,
    materialising_derivation_binding,
)
from pytest_obligation.regression_controls import RegressionControl


def test_generated_extra_proof_detects_fault_and_restores_real_reference() -> None:
    control = RegressionControl(
        binding=materialising_derivation_binding,
        proof=assert_unrecorded_obligation_is_discovered,
        regression=lambda: patch.object(MaterialisingDeriver, "derive", EdgeTriggeredDeriver.derive),
        match="was not discovered",
    )
    contract = ObligationContract(
        name="reference derivation sensitivity",
        profiles={
            profile: NotApplicable("This declaration measures sensitivity of one configured shared proof.")
            for profile in Profile
        },
        extras=(ExtraProof(name="missing-derivation", run=control),),
    )
    cases = [p.values[0] for p in contract_cases(contract) if p.values[0].id == "extra-missing-derivation"]
    assert len(cases) == 1
    cases[0].run()
    with pytest.raises(AssertionError, match="did not detect"):
        control.model_copy(update={"regression": nullcontext})()


def test_a_regression_declaration_rejects_a_test_written_proof() -> None:
    with pytest.raises(AssertionError, match="owned by the shared harness"):
        RegressionControl(
            binding=materialising_derivation_binding,
            proof=lambda value: None,
            regression=nullcontext,
            match="anything",
        )()
