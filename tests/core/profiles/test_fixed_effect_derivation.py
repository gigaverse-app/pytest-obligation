"""Fixed effects still prove discovery, stable derivation and terminal settlement."""

from typing import Any, cast

import pytest

from pytest_obligation.contract import Claim, Profile, contract_cases
from pytest_obligation.profiles.fact_derived_obligations import (
    FixedEffectDerived,
    assert_fixed_effect_derived_contract,
    assert_settled_obligation_is_not_rediscovered,
    assert_unrecorded_obligation_is_discovered,
)
from pytest_obligation.references.in_memory import (
    MaterialisingDeriver,
    SelectionIsTheDerivation,
    materialising_derivation_binding,
    reference_derivation_binding,
)
from tests.core.contract.declarations import dispositions
from tests.core.contract.test_contract import _contract


def fixed_binding(impl=None):
    # ARRANGE: one constant effect per product identity, with no replacement command.
    # REAL PRODUCTION: shared reference derivation, selection and settlement owners.
    # EXTERNAL SEAM: no external service; this is the harness reference implementation.
    # OBSERVE: actual outstanding identities and persisted reference records.
    source = (
        reference_derivation_binding(impl)
        if isinstance(impl, SelectionIsTheDerivation)
        else materialising_derivation_binding(impl)
    )
    return FixedEffectDerived(**{name: getattr(source, name) for name in FixedEffectDerived.model_fields})


@pytest.mark.parametrize("impl", [MaterialisingDeriver, SelectionIsTheDerivation])
def test_fixed_effects_pass_without_a_replacement_callback(impl):
    binding = fixed_binding(impl())
    assert not hasattr(binding, "move_desired_state")
    assert_fixed_effect_derived_contract(binding)


def test_an_unrecorded_fixed_effect_cannot_require_an_admission_hook():
    class EdgeTriggered(MaterialisingDeriver):
        def derive(self):
            pass

    with pytest.raises(AssertionError, match="was not discovered"):
        assert_unrecorded_obligation_is_discovered(fixed_binding(EdgeTriggered()))


@pytest.mark.parametrize("defect", ["never settles", "revives settled"])
def test_settlement_cannot_hide_a_fixed_effect_that_is_still_owed(defect):
    class Broken(MaterialisingDeriver):
        def settle(self, product_id):
            if defect == "revives settled":
                super().settle(product_id)
                self.products[product_id].applied = None

    with pytest.raises(AssertionError, match="settle.*outstanding|rediscovered.*settled"):
        assert_settled_obligation_is_not_rediscovered(fixed_binding(Broken()))


def test_the_fixed_effect_contract_generates_its_actual_guarantees():
    contract = _contract(profiles=dispositions(F=Claim()), derivation=None, fixed_effect_derivation=fixed_binding)
    cases = [p.values[0] for p in contract_cases(contract) if p.values[0].profile is Profile.F]
    assert cases
    assert all(case.family == "fixed_effect_derivation" for case in cases)
    assert not any("moved_desired" in case.id for case in cases)
    assert any("settled_obligation_is_not_rediscovered" in case.id for case in cases)
    for case in cases:
        case.run()


def test_fixed_and_mutable_contract_shapes_cannot_be_mixed():
    from pytest_obligation.contract import ObligationContractDesignError
    from pytest_obligation.profiles.fact_derived_obligations import assert_fixed_effect_bindings_are_production_bound

    with pytest.raises(ObligationContractDesignError, match="not both"):
        _contract(fixed_effect_derivation=fixed_binding)
    with pytest.raises(AssertionError, match="requires FixedEffectDerived"):
        assert_fixed_effect_bindings_are_production_bound(cast(Any, materialising_derivation_binding()))


@pytest.mark.parametrize("defect", [None, "missing selection", "missing dispatch"])
def test_fixed_effects_still_require_actual_recovery_consumption(defect):
    from types import SimpleNamespace

    from pytest_obligation.coherence import assert_automatic_recovery_consumes_derived_obligations

    impl = MaterialisingDeriver()
    binding = fixed_binding(impl).model_copy(update={"make_recovery_eligible": lambda _identity: None})
    dispatched = []

    def tick():
        for identity in impl.outstanding():
            if defect != "missing dispatch":
                dispatched.append(identity)
            impl.settle(identity)

    sweep = SimpleNamespace(
        name="fixed-effect recovery",
        due_work=(lambda: []) if defect == "missing selection" else impl.outstanding,
        run_tick=tick,
        dispatched_ids=lambda: dispatched,
        identity_of=lambda identity: identity,
    )
    if defect:
        with pytest.raises(AssertionError, match="does not select|did not dispatch"):
            assert_automatic_recovery_consumes_derived_obligations(sweep, binding)
    else:
        assert_automatic_recovery_consumes_derived_obligations(sweep, binding)
        assert len(dispatched) == 1  # No fictitious replacement operation was constructed.
