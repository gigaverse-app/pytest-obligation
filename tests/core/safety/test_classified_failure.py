"""The outcome-classification proof, exercised against lifecycle mutations in both directions."""

import pytest

from pytest_obligation.profiles.job_retry_limits import (
    ClassifiedFailure,
    FailureClass,
    assert_classified_failure_contract,
    assert_failure_takes_its_declared_class,
)
from pytest_obligation.references.in_memory import (
    InMemoryClassifyingLifecycle,
    reference_classified_failure_binding,
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
