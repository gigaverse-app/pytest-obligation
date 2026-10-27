"""Lifecycle oracles reject missing promises, premature settlement and inert seams."""

from contextlib import contextmanager

import pytest

from pytest_obligation.contract import NotApplicable, ObligationContract, Profile, contract_cases
from pytest_obligation.lifecycle import (
    assert_competing_transition_preserves_effects,
    assert_pending_admission_preserves_effects,
    assert_settled_admission_preserves_effects,
)
from pytest_obligation.references.lifecycle import admission_example, settlement_example


@pytest.mark.parametrize(
    "proof", [assert_pending_admission_preserves_effects, assert_settled_admission_preserves_effects]
)
def test_overlap_controls(proof):
    proof(admission_example())
    for fault in ("retain-first", "duplicate"):
        with pytest.raises(AssertionError, match="lost or duplicated"):
            proof(admission_example(fault))


@pytest.mark.parametrize(
    "fault, message",
    [(None, None), ("discard", "discarded"), ("duplicate", "duplicated"), ("unreached", "never reached")],
)
def test_checkpoint_controls(fault, message):
    if message is None:
        assert_competing_transition_preserves_effects(settlement_example(fault))
    else:
        with pytest.raises(AssertionError, match=message):
            assert_competing_transition_preserves_effects(settlement_example(fault))


def test_ignored_or_vacuous_bindings_are_rejected():
    with pytest.raises(AssertionError, match="production"):
        assert_pending_admission_preserves_effects(admission_example().model_copy(update={"later": lambda: None}))
    with pytest.raises(AssertionError, match="hide the additional"):
        assert_pending_admission_preserves_effects(
            admission_example().model_copy(update={"expected_combined": ("receipt",)})
        )
    with pytest.raises(AssertionError, match="changed no product state"):
        assert_competing_transition_preserves_effects(
            settlement_example().model_copy(update={"observe_competing": lambda: 0})
        )


@pytest.mark.parametrize("phase", ["enter", "exit"])
def test_checkpoint_outside_operation_is_rejected(phase):
    @contextmanager
    def during(checkpoint):
        if phase == "enter":
            checkpoint()
        yield
        if phase == "exit":
            checkpoint()

    with pytest.raises(AssertionError, match="outside the production"):
        assert_competing_transition_preserves_effects(settlement_example().model_copy(update={"during": during}))


def test_generated_histories_have_separate_report_identities():
    contract = ObligationContract(
        name="lifecycle specimen",
        profiles={p: NotApplicable("No framework in this core specimen") for p in Profile},
        admission_overlaps={"repair_then_full": admission_example},
        settlement_interleavings={"provider_read": settlement_example},
    )
    cases = [
        p.values[0]
        for p in contract_cases(contract)
        if p.id.startswith(("admission-overlap-", "settlement-interleaving-"))
    ]
    assert len(cases) == 3
    assert len({case.id for case in cases}) == 3
    for case in cases:
        case.run()


def test_a_production_error_handler_cannot_hide_a_failed_checkpoint_control():
    example = settlement_example("swallow").model_copy(update={"observe_competing": lambda: 0})
    with pytest.raises(AssertionError, match="changed no product state"):
        assert_competing_transition_preserves_effects(example)
