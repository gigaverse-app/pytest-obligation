"""The acknowledged-effect proofs, exercised against teardown mutations in both directions."""

from contextlib import nullcontext

import pytest

from pytest_obligation.profiles.acknowledged_effects import (
    AcknowledgedEffect,
    assert_acknowledged_effect_contract,
    assert_an_acknowledgement_does_not_discharge,
    assert_an_applied_acknowledgement_discharges,
)
from pytest_obligation.references.in_memory import (
    InMemoryAcknowledgingTeardown,
    reference_acknowledged_effect_binding,
)


def test_a_teardown_that_waits_for_the_provider_passes() -> None:
    assert_acknowledged_effect_contract(reference_acknowledged_effect_binding())


def test_a_teardown_that_trusts_the_reply_is_caught() -> None:
    # The defect this proof exists for: a task id is treated as the deletion itself.
    class _TrustsTheReply(InMemoryAcknowledgingTeardown):
        def run_once(self, operation_id: int) -> None:
            if operation_id in self.owed:
                self.request_deletion(operation_id)
                del self.owed[operation_id]

    binding = reference_acknowledged_effect_binding(_TrustsTheReply())
    with pytest.raises(AssertionError, match="discharged the operation on the provider's acknowledgement alone"):
        assert_an_acknowledgement_does_not_discharge(binding)
    # Discharging on the reply also ends up discharged once the provider applies,
    # so the second proof must refuse the history rather than pass it.
    with pytest.raises(AssertionError, match="discharged the operation before the provider applied it"):
        assert_an_applied_acknowledgement_discharges(binding)


def test_a_teardown_that_never_discharges_is_caught() -> None:
    # Keeping everything owed satisfies the first proof; the second rules it out.
    class _NeverDischarges(InMemoryAcknowledgingTeardown):
        def run_once(self, operation_id: int) -> None:
            if operation_id in self.owed and self.owed[operation_id] is None:
                self.owed[operation_id] = self.request_deletion(operation_id)

    binding = reference_acknowledged_effect_binding(_NeverDischarges())
    assert_an_acknowledgement_does_not_discharge(binding)
    with pytest.raises(AssertionError, match="further production run\\(s\\) left the operation owed"):
        assert_an_applied_acknowledgement_discharges(binding)


def test_a_failed_task_is_requested_again() -> None:
    teardown = InMemoryAcknowledgingTeardown()
    operation = teardown.make_owed()
    with teardown.tasks.held():
        teardown.run_once(operation)
    teardown.tasks.fail(teardown.tasks.pending[0])

    teardown.run_once(operation)

    assert teardown.acknowledgement_count(operation) == 2
    assert teardown.applied(operation)
    assert teardown.owed_work() == []


def test_a_hold_that_does_not_hold_is_refused() -> None:
    teardown = InMemoryAcknowledgingTeardown()
    binding = reference_acknowledged_effect_binding(teardown)
    leaky = AcknowledgedEffect.model_validate(binding.model_dump() | {"hold_acknowledgements": lambda _: nullcontext()})

    with pytest.raises(AssertionError, match="hold_acknowledgements does not hold"):
        assert_an_acknowledgement_does_not_discharge(leaky)


def test_a_run_that_never_reaches_the_provider_is_refused() -> None:
    class _SkipsTheProvider(InMemoryAcknowledgingTeardown):
        def run_once(self, operation_id: int) -> None:
            return None

    with pytest.raises(AssertionError, match="never reached the acknowledging provider"):
        assert_an_acknowledgement_does_not_discharge(reference_acknowledged_effect_binding(_SkipsTheProvider()))


def test_work_that_is_not_owed_cannot_be_measured() -> None:
    class _OwesNothing(InMemoryAcknowledgingTeardown):
        def owed_work(self) -> list[int]:
            return []

    with pytest.raises(AssertionError, match="did not create work production owes"):
        assert_an_acknowledgement_does_not_discharge(reference_acknowledged_effect_binding(_OwesNothing()))


def test_a_discharge_budget_below_one_is_refused() -> None:
    binding = reference_acknowledged_effect_binding()
    with pytest.raises(ValueError, match="max_runs_to_discharge must be at least one"):
        AcknowledgedEffect.model_validate(binding.model_dump() | {"max_runs_to_discharge": 0})


def test_observation_clock_cannot_discharge_the_operation():
    teardown = InMemoryAcknowledgingTeardown()
    binding = reference_acknowledged_effect_binding(teardown).model_copy(
        update={"advance_to_observation": lambda operation: teardown.owed.pop(operation)}
    )
    with pytest.raises(AssertionError, match="advancing observation time discharged"):
        assert_an_applied_acknowledgement_discharges(binding)


def test_observation_clock_can_advance_without_changing_the_obligation():
    binding = reference_acknowledged_effect_binding().model_copy(
        update={"advance_to_observation": lambda operation: None}
    )
    assert_acknowledged_effect_contract(binding)
