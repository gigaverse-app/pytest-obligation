"""Negative controls reject early, stalled, reversed and duplicated outcomes."""

import pytest

from pytest_obligation.completion import (
    BoundedCompletion,
    assert_completes_within,
    assert_delivery_replay,
)
from pytest_obligation.references.completion import delivery_example, timer


def test_completion_accepts_declared_outcome_at_bound():
    assert_completes_within(timer(duration=4))


@pytest.mark.parametrize(
    "kwargs, message",
    [({"duration": 1}, "minimum wait"), ({"duration": 10}, "time bound"), ({"reverse": True}, "reversed")],
)
def test_completion_controls(kwargs, message):
    with pytest.raises(AssertionError, match=message):
        assert_completes_within(timer(**kwargs))


@pytest.mark.parametrize("fault", [None, "skip", "repeat", "wrong outcome"])
def test_delivery_controls(fault):
    example = delivery_example(fault)
    if fault is None:
        assert_delivery_replay(example)
    else:
        with pytest.raises(AssertionError):
            assert_delivery_replay(example)


def completed_in_time():
    # ARRANGE: deterministic clock specimen for the harness's own tests.
    # REAL PRODUCTION: the shared completion oracle is the subject under test.
    # EXTERNAL SEAM: no framework or provider is installed in this specimen.
    # OBSERVE: a declared terminal result at the independently configured deadline.
    return timer()


def test_generated_completion_runs_and_requires_expected_outcome():
    from pydantic import ValidationError

    from pytest_obligation.contract import NotApplicable, ObligationContract, Profile, contract_cases

    contract = ObligationContract(
        name="bounded specimen",
        profiles={p: NotApplicable("No framework in this core specimen") for p in Profile},
        completions={"terminal": completed_in_time},
    )
    case = next(row.values[0] for row in contract_cases(contract) if row.id.startswith("completion-"))
    case.run()
    with pytest.raises(ValidationError):
        BoundedCompletion.model_validate(
            dict(
                observe=lambda: None,
                advance=lambda seconds: None,
                recover=lambda: None,
                within_seconds=1,
                interval_seconds=1,
            )
        )


def test_decorated_partial_keeps_binding_annotations():
    from functools import partial, wraps

    from pytest_obligation.binding import callable_code

    @wraps(partial(completed_in_time))
    def bound():
        return completed_in_time()

    assert callable_code(bound) is completed_in_time.__code__


def test_test_authored_recovery_and_delivery_are_rejected():
    with pytest.raises(AssertionError, match="production"):
        assert_completes_within(timer().model_copy(update={"recover": lambda: None}))
    with pytest.raises(AssertionError, match="production"):
        assert_delivery_replay(delivery_example(None).model_copy(update={"deliver": lambda: None}))


def test_fractional_clock_step_reaches_exact_declared_bound():
    assert_completes_within(timer(duration=3).model_copy(update={"interval_seconds": 0.1, "within_seconds": 3}))


def test_decorated_partial_cannot_hide_ignored_runtime_identity():
    from functools import partial, wraps

    from pytest_obligation.binding import assert_test_binding_consumes_its_first_parameter

    def ignores(label, identity):
        return label

    @wraps(partial(ignores, "fixed label"))
    def wrapper(identity):
        return ignores("fixed label", identity)

    with pytest.raises(AssertionError, match="identity"):
        assert_test_binding_consumes_its_first_parameter(
            adopter="partial control", field="execute", binding=wrapper, parameter_shape="the runtime identity"
        )
