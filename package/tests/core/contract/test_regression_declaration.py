from contextlib import nullcontext
from unittest.mock import patch

import pytest

from pytest_obligation.contract import ExtraProof, NotApplicable, ObligationContract, Profile, contract_cases
from pytest_obligation.profiles.fact_derived_obligations import (
    assert_unrecorded_obligation_is_discovered,
)
from pytest_obligation.profiles.harmless_replay import assert_replay_converges
from pytest_obligation.references.in_memory import (
    EdgeTriggeredDeriver,
    InMemoryReplayEffect,
    MaterialisingDeriver,
    materialising_derivation_binding,
    reference_replay_safety_binding,
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


def test_replay_controls_validate_production_binding_before_detecting_duplicates() -> None:
    original = InMemoryReplayEffect.execute

    def duplicate(effect: InMemoryReplayEffect, operation_id: int) -> None:
        original(effect, operation_id)
        if effect.executions > 1:
            effect.outputs[operation_id] += ":duplicate"

    control = RegressionControl(
        binding=reference_replay_safety_binding,
        proof=assert_replay_converges,
        regression=lambda: patch.object(InMemoryReplayEffect, "execute", duplicate),
        match="in-memory replay-safe effect",
    )
    control()
    with pytest.raises(AssertionError, match="did not detect"):
        control.model_copy(update={"regression": nullcontext})()
