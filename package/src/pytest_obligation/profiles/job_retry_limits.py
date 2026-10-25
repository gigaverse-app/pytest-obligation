"""
Reusable proof that retryable failure has a finite, stable lifecycle.

This is the ``BOUNDED_RETRY`` safety profile. Every adopter explicitly
assesses it in the flat domain contract, or a scoped :class:`~pytest_obligation.contract.SafetyContract`; effects
outside the full due-work domain contract can declare the same safety contract
directly. A claimant deliberately retries a classified transient failure and
declares a maximum number of executions, including the initial execution.

The proof does not prescribe a stored retry counter, backoff formula, or
terminal state name. It does require operation-specific evidence at the
injected failing dependency, because lifecycle state alone can advance without
the claimed operation ever running. It drives the real selector and runner,
lets the adopter advance only the waiting condition, and observes four shared
properties:

1. production selection finds the fresh operation and every pre-limit retry;
2. every runner invocation reaches the failing dependency exactly once;
3. the operation becomes terminal exactly at the declared execution bound and
   leaves ordinary due selection; and
4. invoking the runner once more cannot change terminal observable state or
   reach the failing dependency again.

An obligation with no execution bound binds :class:`PersistentRetry` instead,
and the same evidence proves the other half of the profile: a persistent
transient failure keeps the obligation owed. Every execution reaches the
failing dependency exactly once, the obligation never becomes terminal, it is
not due again until its wait elapses (no hot loop), and it is due again
afterwards (never lost).

Both halves drive one failure repeatedly. :class:`ClassifiedFailure` instead
names one provider outcome and the classification production must give it,
so an application can declare its whole outcome matrix. A terminal
classification must end the operation after one execution and never reach
the dependency again. A retryable one must leave it owed and due again after
its wait. Either can also declare the product-visible outcome the failure
must leave behind. A retryable outcome that carries the provider's own wait,
such as an HTTP ``Retry-After``, declares it as ``provider_wait``: the
operation must not be due again until that wait has elapsed, however short its
ordinary retry delay, because a retry inside the provider's window is refused
again and spends another execution.
"""

from collections.abc import Callable, Iterable
from datetime import timedelta
from enum import StrEnum
from typing import Any

from pytest_obligation.binding import (
    INVOCATION_AUTHORING_OPERATIONS,
    SELECTION_AUTHORING_OPERATIONS,
    assert_binding_reaches_production,
)
from pytest_obligation.models import HarnessModel


def _identity(value: Any) -> Any:
    return value


class RetryLifecycle(HarnessModel):
    """One production retry lifecycle under a persistent transient failure."""

    name: str

    #: Arrange one due operation whose dependency will fail transiently.
    make_failing: Callable[[], Any]

    #: The ordinary production selection that finds retryable work. The
    #: harness, not the adopter, decides whether the arranged operation is in
    #: it; accepting an ``is_due`` verdict would let test code restate or fake
    #: the production predicate.
    due_work: Callable[[], Iterable[Any]]

    #: Run the real production executor or scheduled runner once.
    run_once: Callable[[Any], Any]

    #: Advance only the retry wait condition (for example, age scheduled_at).
    #: It may be a no-op for designs whose retry is immediately due.
    advance_to_due: Callable[[Any], Any]

    #: Whether the domain has durably exhausted/abandoned the operation.
    is_terminal: Callable[[Any], bool]

    #: Operation-specific count recorded at the injected failing dependency
    #: boundary. This is deliberately not just a lifecycle counter: it is the
    #: positive control proving each claimed retry reached the failure whose
    #: retry behavior is under test.
    failure_attempt_count: Callable[[Any], int]

    #: Comparable state broad enough to expose a terminal replay, including
    #: provider-call records when an extra call would itself be harmful.
    observe: Callable[[Any], Any]

    #: Convert both the arranged operation and each selected item to the same
    #: stable identity. The default covers selectors that return the operation
    #: identity directly; model-based adopters commonly bind ``lambda row:
    #: row.pk`` and arrange a real row.
    identity_of: Callable[[Any], Any] = _identity


class BoundedRetry(RetryLifecycle):
    """A retry lifecycle whose production budget ends it at a declared number of executions."""

    #: Total failing executions allowed, including the initial execution.
    max_executions: int

    def model_post_init(self, _context: Any) -> None:
        if self.max_executions < 1:
            raise ValueError("BoundedRetry.max_executions must be at least one")


#: Executions the persistent-failure proof drives: enough to see the obligation
#: survive repeated failure and several waits, without claiming any bound.
PERSISTENT_EXECUTIONS = 6


class PersistentRetry(RetryLifecycle):
    """A retry lifecycle with no execution bound: the obligation is kept until it succeeds."""

    #: Whether a failed execution waits before it is due again (a positive retry
    #: delay). A selected waiting candidate must remain a no-op in the runner.
    waits: bool = True


def assert_retry_runner_is_production_bound(retry: RetryLifecycle) -> None:
    """The failing execution reaches production rather than a test state machine."""
    assert_binding_reaches_production(
        adopter=retry.name,
        field="run_once",
        binding=retry.run_once,
        forbidden=INVOCATION_AUTHORING_OPERATIONS,
        production_shape="the production retry runner",
    )


def assert_retry_selection_is_production_bound(retry: RetryLifecycle) -> None:
    """The due-work predicate forwards to production rather than test logic."""
    assert_binding_reaches_production(
        adopter=retry.name,
        field="due_work",
        binding=retry.due_work,
        forbidden=SELECTION_AUTHORING_OPERATIONS,
        production_shape="the production retry selection",
    )


def _is_due(retry: RetryLifecycle, operation: Any) -> bool:
    identity = retry.identity_of(operation)
    return any(retry.identity_of(selected) == identity for selected in retry.due_work())


def _assert_one_failure_attempt(
    retry: RetryLifecycle,
    operation: Any,
    *,
    before: int,
    execution: int,
) -> int:
    after = retry.failure_attempt_count(operation)
    new_attempts = after - before
    assert new_attempts == 1, (
        f"{retry.name}: execution {execution} ran the retry runner, but the "
        f"failing dependency recorded {new_attempts} new attempts "
        f"({before} -> {after}). Retry lifecycle state is not evidence that "
        f"the claimed failing operation actually ran exactly once"
    )
    return after


def _fresh_failing(retry: RetryLifecycle) -> tuple[Any, int]:
    operation = retry.make_failing()
    assert _is_due(retry, operation), (
        f"{retry.name}: make_failing() did not create due work, so the retry runner cannot be exercised"
    )
    assert not retry.is_terminal(operation), f"{retry.name}: make_failing() created already-terminal work"
    attempts = retry.failure_attempt_count(operation)
    assert attempts == 0, (
        f"{retry.name}: make_failing() created work with {attempts} recorded "
        f"failure attempt(s). The contract drives a fresh lifecycle from zero"
    )
    return operation, attempts


def _advance_after_failure(retry: RetryLifecycle, operation: Any, *, attempts: int, execution: int) -> None:
    retry.advance_to_due(operation)
    after_advance = retry.failure_attempt_count(operation)
    assert after_advance == attempts, (
        f"{retry.name}: advance_to_due changed the failure-attempt "
        f"count ({attempts} -> {after_advance}). Fault injection may "
        f"advance only the wait condition; it cannot manufacture an "
        f"execution the production runner never performed"
    )
    assert _is_due(retry, operation), (
        f"{retry.name}: retryable failure {execution} never became due again after its wait condition elapsed"
    )


def _drive_to_terminal(retry: BoundedRetry) -> Any:
    operation, attempts = _fresh_failing(retry)
    for execution in range(1, retry.max_executions + 1):
        retry.run_once(operation)
        attempts = _assert_one_failure_attempt(
            retry,
            operation,
            before=attempts,
            execution=execution,
        )
        if execution < retry.max_executions:
            assert not retry.is_terminal(operation), (
                f"{retry.name}: retryable failure became terminal after "
                f"{execution} execution(s), before the declared "
                f"{retry.max_executions}-execution bound"
            )
            _advance_after_failure(retry, operation, attempts=attempts, execution=execution)

    assert retry.is_terminal(operation), (
        f"{retry.name}: work is still non-terminal after the declared {retry.max_executions}-execution retry bound"
    )
    assert not _is_due(retry, operation), (
        f"{retry.name}: terminal retry-exhausted work remains in ordinary due selection and will execute forever"
    )
    return operation


def assert_retryable_failures_reach_terminal_at_the_bound(retry: BoundedRetry) -> None:
    """Transient failures remain recoverable, then exhaust at the exact bound."""
    _drive_to_terminal(retry)


def assert_terminal_retry_is_a_no_op(retry: BoundedRetry) -> None:
    """A stale duplicate runner cannot resurrect or re-execute exhausted work."""
    operation = _drive_to_terminal(retry)
    before = retry.observe(operation)
    attempts_before = retry.failure_attempt_count(operation)
    retry.run_once(operation)
    after = retry.observe(operation)
    assert after == before, (
        f"{retry.name}: terminal retry changed observable state "
        f"({before!r} -> {after!r}). A stale duplicate runner can re-execute "
        f"work after its retry budget is exhausted"
    )
    attempts_after = retry.failure_attempt_count(operation)
    assert attempts_after == attempts_before, (
        f"{retry.name}: terminal retry recorded another failure attempt "
        f"({attempts_before} -> {attempts_after}). A stale runner reached the "
        f"dependency after the retry budget was exhausted"
    )
    assert retry.is_terminal(operation) and not _is_due(retry, operation), (
        f"{retry.name}: invoking the runner resurrected terminal work"
    )


BOUNDED_RETRY_PROOFS: tuple[Callable[[BoundedRetry], None], ...] = (
    assert_retry_selection_is_production_bound,
    assert_retry_runner_is_production_bound,
    assert_retryable_failures_reach_terminal_at_the_bound,
    assert_terminal_retry_is_a_no_op,
)


def assert_bounded_retry_contract(retry: BoundedRetry) -> None:
    """Run the production-binding guard and bounded retry invariants."""
    for proof in BOUNDED_RETRY_PROOFS:
        proof(retry)


def assert_persistent_failure_stays_owed(retry: PersistentRetry) -> None:
    """With no execution bound, a persistent transient failure keeps the obligation owed and pacing itself."""
    operation, attempts = _fresh_failing(retry)
    for execution in range(1, PERSISTENT_EXECUTIONS + 1):
        retry.run_once(operation)
        attempts = _assert_one_failure_attempt(retry, operation, before=attempts, execution=execution)
        assert not retry.is_terminal(operation), (
            f"{retry.name}: a persistently failing obligation became terminal after {execution} "
            f"execution(s). With no execution bound it must stay owed until it succeeds"
        )
        if retry.waits and _is_due(retry, operation):
            # Candidate scans may enforce their wait inside the executor.
            # Run that path: selection alone is not evidence of a hot loop.
            waiting = retry.observe(operation)
            retry.run_once(operation)
            assert retry.failure_attempt_count(operation) == attempts, (
                f"{retry.name}: failure {execution} retried before its wait elapsed: a hot loop"
            )
            assert not retry.is_terminal(operation), f"{retry.name}: waiting retry became terminal"
            assert retry.observe(operation) == waiting, f"{retry.name}: waiting retry changed observable state"
        _advance_after_failure(retry, operation, attempts=attempts, execution=execution)


PERSISTENT_RETRY_PROOFS: tuple[Callable[[PersistentRetry], None], ...] = (
    assert_retry_selection_is_production_bound,
    assert_retry_runner_is_production_bound,
    assert_persistent_failure_stays_owed,
)


def assert_persistent_retry_contract(retry: PersistentRetry) -> None:
    """Run the production-binding guard and the persistent-failure invariant."""
    for proof in PERSISTENT_RETRY_PROOFS:
        proof(retry)


#: How far short of ``provider_wait`` the proof checks that the operation is still waiting.
PROVIDER_WAIT_MARGIN = timedelta(seconds=1)


class FailureClass(StrEnum):
    """How production must classify one definite failure."""

    #: Transient: the operation stays owed and is executed again after its wait.
    RETRYABLE = "retryable"
    #: Permanent: the operation ends now; executing it again cannot succeed.
    TERMINAL = "terminal"


class ClassifiedFailure(RetryLifecycle):
    """One named provider outcome, the classification production must give it, and what the product shows."""

    #: The classification this outcome must receive from production.
    classification: FailureClass

    #: Whether a retryable failure waits before it is due again; ignored for a terminal one.
    waits: bool = True

    #: OBSERVE: the product-visible consequence of the failure (a status mirror, a
    #: recorded reason). Bind it with ``expected_product_outcome``, or neither.
    product_outcome: Callable[[Any], Any] | None = None

    #: The reviewed product outcome this failure must leave, derived from the
    #: arranged operation, never read back from the run.
    expected_product_outcome: Callable[[Any], Any] | None = None

    #: The wait the provider declared with this retryable outcome (an HTTP
    #: ``Retry-After``, a quota reset). The operation must not be due again
    #: before it elapses. Bind it with ``advance_by``, or neither.
    provider_wait: timedelta | None = None

    #: FAULT INJECTION: let ``delta`` of the operation's retry wait elapse (age
    #: its due time by ``delta``, or move the test clock forward), and nothing
    #: else. Unlike ``advance_to_due`` it is partial, so the proof can stop
    #: just short of ``provider_wait``.
    advance_by: Callable[[Any, timedelta], Any] | None = None

    def model_post_init(self, _context: Any) -> None:
        if (self.product_outcome is None) != (self.expected_product_outcome is None):
            raise ValueError(
                "ClassifiedFailure binds product_outcome and expected_product_outcome together: "
                "an observation without its expected value proves nothing, and the reverse cannot run"
            )
        if (self.provider_wait is None) != (self.advance_by is None):
            raise ValueError(
                "ClassifiedFailure binds provider_wait and advance_by together: a declared wait needs a clock "
                "to stop short of it, and a clock with no declared wait has nothing to prove"
            )
        if self.provider_wait is not None:
            if self.classification is not FailureClass.RETRYABLE:
                raise ValueError("provider_wait describes a retry; a terminal outcome never runs again")
            if self.provider_wait <= PROVIDER_WAIT_MARGIN:
                raise ValueError(
                    f"provider_wait must exceed {PROVIDER_WAIT_MARGIN}: the proof checks the operation "
                    f"is still waiting that far short of it"
                )


def _assert_product_outcome(failure: ClassifiedFailure, operation: Any, *, after: str) -> None:
    if failure.product_outcome is None or failure.expected_product_outcome is None:
        return
    actual = failure.product_outcome(operation)
    expected = failure.expected_product_outcome(operation)
    assert actual == expected, (
        f"{failure.name}: {after}, the product shows {actual!r}, not the declared {expected!r}. "
        f"The {failure.classification.value} classification is invisible to the product"
    )


def assert_failure_takes_its_declared_class(failure: ClassifiedFailure) -> None:
    """One execution of the named outcome receives its declared classification, visibly and stably."""
    operation, attempts = _fresh_failing(failure)
    failure.run_once(operation)
    attempts = _assert_one_failure_attempt(failure, operation, before=attempts, execution=1)

    if failure.classification is FailureClass.RETRYABLE:
        assert not failure.is_terminal(operation), (
            f"{failure.name}: a failure declared retryable became terminal after one execution. "
            f"Production gave up on a transient failure that a later execution could complete"
        )
        _assert_product_outcome(failure, operation, after="after one failing execution")
        if failure.waits:
            assert not _is_due(failure, operation), (
                f"{failure.name}: the retryable failure left the operation due again immediately. "
                f"It would be retried in a hot loop instead of after its retry delay"
            )
        if failure.provider_wait is not None and failure.advance_by is not None:
            _assert_waits_out_the_provider(failure, operation, attempts=attempts)
        _advance_after_failure(failure, operation, attempts=attempts, execution=1)
        return

    assert failure.is_terminal(operation), (
        f"{failure.name}: a failure declared terminal was not terminal after one execution. "
        f"Production classified a permanent failure as retryable, so it will repeat a call that cannot succeed"
    )
    _assert_product_outcome(failure, operation, after="after one failing execution")
    assert not _is_due(failure, operation), (
        f"{failure.name}: the terminally failed operation remains in ordinary due selection and will execute again"
    )
    failure.advance_to_due(operation)
    assert failure.failure_attempt_count(operation) == attempts, (
        f"{failure.name}: advance_to_due changed the failure-attempt count. Fault injection may advance "
        f"only the wait condition; it cannot manufacture an execution"
    )
    assert not _is_due(failure, operation), (
        f"{failure.name}: the terminally failed operation became due again once its wait elapsed"
    )
    before = failure.observe(operation)
    failure.run_once(operation)
    after = failure.failure_attempt_count(operation)
    assert after == attempts, (
        f"{failure.name}: a stale runner reached the failing dependency again ({attempts} -> {after}) "
        f"after the failure was classified terminal"
    )
    assert failure.observe(operation) == before, (
        f"{failure.name}: invoking the runner again changed the terminally failed operation"
    )
    _assert_product_outcome(failure, operation, after="after a stale runner invocation")


def _assert_waits_out_the_provider(failure: ClassifiedFailure, operation: Any, *, attempts: int) -> None:
    assert failure.provider_wait is not None and failure.advance_by is not None
    short = failure.provider_wait - PROVIDER_WAIT_MARGIN
    failure.advance_by(operation, short)
    after_advance = failure.failure_attempt_count(operation)
    assert after_advance == attempts, (
        f"{failure.name}: advance_by changed the failure-attempt count ({attempts} -> {after_advance}). "
        f"Fault injection may advance only the wait condition; it cannot manufacture an execution"
    )
    assert not failure.is_terminal(operation), f"{failure.name}: the waiting operation became terminal as time passed"
    assert not _is_due(failure, operation), (
        f"{failure.name}: the operation was due again {short} after a refusal whose provider declared a "
        f"{failure.provider_wait} wait. The retry lands inside the provider's window, is refused again "
        f"and spends another execution: honor the provider's wait as a floor on the retry delay"
    )


CLASSIFIED_FAILURE_PROOFS: tuple[Callable[[ClassifiedFailure], None], ...] = (
    assert_retry_selection_is_production_bound,
    assert_retry_runner_is_production_bound,
    assert_failure_takes_its_declared_class,
)


def assert_classified_failure_contract(failure: ClassifiedFailure) -> None:
    """Run the production-binding guard and the classification invariant."""
    for proof in CLASSIFIED_FAILURE_PROOFS:
        proof(failure)
