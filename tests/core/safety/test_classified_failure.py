"""The outcome-classification proof, exercised against lifecycle mutations in both directions."""

from datetime import timedelta

import pytest

from pytest_obligation.profiles.job_retry_limits import (
    PROVIDER_WAIT_MARGIN,
    ClassifiedFailure,
    FailureClass,
    assert_classified_failure_contract,
    assert_failure_takes_its_declared_class,
)
from pytest_obligation.references.in_memory import (
    REFERENCE_RETRY_DELAY,
    InMemoryClassifyingLifecycle,
    InMemoryThrottledLifecycle,
    reference_classified_failure_binding,
    reference_throttled_failure_binding,
)


@pytest.mark.parametrize("classification", list(FailureClass))
def test_a_conforming_classification_passes(classification: FailureClass) -> None:
    assert_classified_failure_contract(reference_classified_failure_binding(classification=classification))


def test_the_product_outcome_is_optional() -> None:
    assert_failure_takes_its_declared_class(reference_classified_failure_binding(with_product=False))


def test_a_permanent_failure_classified_retryable_is_caught() -> None:
    # Production retries what the application declared permanent: it will repeat a call that cannot succeed.
    lifecycle = InMemoryClassifyingLifecycle(FailureClass.RETRYABLE)
    with pytest.raises(AssertionError, match="declared terminal was not terminal after one execution"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(lifecycle, classification=FailureClass.TERMINAL)
        )


def test_a_transient_failure_classified_terminal_is_caught() -> None:
    lifecycle = InMemoryClassifyingLifecycle(FailureClass.TERMINAL)
    with pytest.raises(AssertionError, match="declared retryable became terminal after one execution"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(lifecycle, classification=FailureClass.RETRYABLE)
        )


def test_a_terminal_failure_left_in_due_selection_is_caught() -> None:
    class _StillSelected(InMemoryClassifyingLifecycle):
        def due_work(self) -> list[int]:
            return list(self.rows)

    with pytest.raises(AssertionError, match="remains in ordinary due selection"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(_StillSelected(FailureClass.TERMINAL))
        )


def test_a_stale_runner_that_reaches_the_dependency_after_a_terminal_failure_is_caught() -> None:
    class _RunsAgain(InMemoryClassifyingLifecycle):
        def run_once(self, operation_id: int) -> None:
            if self.rows[operation_id].state == "TERMINAL":
                self.rows[operation_id].executions += 1
                return
            super().run_once(operation_id)

    with pytest.raises(AssertionError, match="reached the failing dependency again"):
        assert_failure_takes_its_declared_class(reference_classified_failure_binding(_RunsAgain(FailureClass.TERMINAL)))


@pytest.mark.parametrize("classification", list(FailureClass))
def test_a_classification_the_product_never_shows_is_caught(classification: FailureClass) -> None:
    class _Invisible(InMemoryClassifyingLifecycle):
        def product_outcome(self, operation_id: int) -> str | None:
            return None

    with pytest.raises(AssertionError, match="classification is invisible to the product"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(_Invisible(classification), classification=classification)
        )


def test_a_retryable_failure_due_again_at_once_is_a_hot_loop() -> None:
    class _NoWait(InMemoryClassifyingLifecycle):
        def run_once(self, operation_id: int) -> None:
            super().run_once(operation_id)
            self.rows[operation_id].state = "DUE"

    retryable = FailureClass.RETRYABLE
    with pytest.raises(AssertionError, match="hot loop"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(_NoWait(retryable), classification=retryable)
        )
    # A policy with no retry delay declares waits=False and is accepted.
    assert_failure_takes_its_declared_class(
        reference_classified_failure_binding(_NoWait(retryable), classification=retryable, waits=False)
    )


def test_a_retryable_failure_that_is_lost_is_caught() -> None:
    class _Forgets(InMemoryClassifyingLifecycle):
        def run_once(self, operation_id: int) -> None:
            super().run_once(operation_id)
            self.rows[operation_id].state = "LOST"

    retryable = FailureClass.RETRYABLE
    with pytest.raises(AssertionError, match="never became due again"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(_Forgets(retryable), classification=retryable)
        )


def test_a_classification_that_never_reaches_the_dependency_is_caught() -> None:
    class _SkipsDependency(InMemoryClassifyingLifecycle):
        def run_once(self, operation_id: int) -> None:
            self.rows[operation_id].state = "TERMINAL"
            self.product[operation_id] = "failed"

    with pytest.raises(AssertionError, match="recorded 0 new attempts"):
        assert_failure_takes_its_declared_class(
            reference_classified_failure_binding(_SkipsDependency(FailureClass.TERMINAL))
        )


def test_a_product_observation_without_its_expected_value_is_refused() -> None:
    binding = reference_classified_failure_binding()
    with pytest.raises(ValueError, match="product_outcome and expected_product_outcome together"):
        ClassifiedFailure.model_validate(binding.model_dump() | {"expected_product_outcome": None})


def test_a_retry_that_waits_out_the_providers_declared_wait_passes() -> None:
    assert_classified_failure_contract(reference_throttled_failure_binding())


def test_a_retry_inside_the_providers_window_is_caught() -> None:
    # The lifecycle keeps its own 2 s backoff and drops the provider's 60 s Retry-After.
    class _IgnoresTheProvider(InMemoryThrottledLifecycle):
        def retry_delay(self) -> timedelta:
            return REFERENCE_RETRY_DELAY

    with pytest.raises(AssertionError, match="inside the provider's window"):
        assert_failure_takes_its_declared_class(reference_throttled_failure_binding(_IgnoresTheProvider()))


def test_a_retry_one_second_short_of_the_providers_wait_is_caught() -> None:
    # The boundary the margin protects: due just before the declared wait, not at it.
    class _AlmostHonors(InMemoryThrottledLifecycle):
        def retry_delay(self) -> timedelta:
            return self.provider_wait - PROVIDER_WAIT_MARGIN

    with pytest.raises(AssertionError, match="inside the provider's window"):
        assert_failure_takes_its_declared_class(reference_throttled_failure_binding(_AlmostHonors()))


def test_an_advance_by_that_manufactures_an_execution_is_caught() -> None:
    class _ExecutesWhileWaiting(InMemoryThrottledLifecycle):
        def advance_by(self, operation_id: int, delta: timedelta) -> None:
            super().advance_by(operation_id, delta)
            self.rows[operation_id].executions += 1

    with pytest.raises(AssertionError, match="advance_by changed the failure-attempt count"):
        assert_failure_takes_its_declared_class(reference_throttled_failure_binding(_ExecutesWhileWaiting()))


def test_a_stale_delivery_cannot_bypass_the_provider_wait() -> None:
    class _RunsEarly(InMemoryThrottledLifecycle):
        def run_once(self, operation_id: int) -> None:
            self.rows[operation_id].due_at = self.clock
            super().run_once(operation_id)

    with pytest.raises(AssertionError, match="stale runner.*provider's window"):
        assert_failure_takes_its_declared_class(reference_throttled_failure_binding(_RunsEarly()))


@pytest.mark.parametrize(
    "update,message",
    [
        ({"advance_by": None}, "provider_wait and advance_by together"),
        ({"provider_wait": None}, "provider_wait and advance_by together"),
        ({"classification": FailureClass.TERMINAL}, "a terminal outcome never runs again"),
        ({"provider_wait": PROVIDER_WAIT_MARGIN}, "must exceed"),
    ],
)
def test_an_incoherent_provider_wait_binding_is_refused(update: dict, message: str) -> None:
    binding = reference_throttled_failure_binding()
    with pytest.raises(ValueError, match=message):
        ClassifiedFailure.model_validate(binding.model_dump() | update)


@pytest.mark.parametrize("charges_budget", [False, True])
@pytest.mark.parametrize("clock_resets_budget", [False, True])
def test_waiting_budget_proof_accepts_waits_and_rejects_charged_waits(charges_budget, clock_resets_budget):
    class WaitingLifecycle(InMemoryClassifyingLifecycle):
        def __init__(self):
            super().__init__(FailureClass.RETRYABLE)
            self.budget = 0

        def run_once(self, operation_id):
            before = self.rows[operation_id].executions
            super().run_once(operation_id)
            if charges_budget:
                self.budget += self.rows[operation_id].executions - before

    lifecycle = WaitingLifecycle()
    binding = reference_classified_failure_binding(lifecycle, classification=FailureClass.RETRYABLE)
    advance = binding.advance_to_due

    def move_clock(operation):
        advance(operation)
        if clock_resets_budget:
            lifecycle.budget = 0  # A bad clock binding must not conceal a charged wait.

    binding = binding.model_copy(
        update={"preserved_failure_budget": lambda _operation: lifecycle.budget, "advance_to_due": move_clock}
    )
    if charges_budget:
        with pytest.raises(AssertionError, match="provider waiting spent"):
            assert_failure_takes_its_declared_class(binding)
    else:
        assert_failure_takes_its_declared_class(binding)
