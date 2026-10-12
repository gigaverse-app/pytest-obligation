"""Negative controls reject early, stalled, reversed and duplicated outcomes."""

import pytest

from pytest_obligation.completion import (
    BoundedCompletion,
    DeliveryReplay,
    assert_completes_within,
    assert_delivery_replay,
)


def timer(*, duration=3, reverse=False):
    state = {"time": 0}

    def advance(seconds):
        state["time"] += seconds

    return BoundedCompletion(
        observe=lambda: state["time"] >= duration,
        expected=True,
        advance=advance,
        recover=lambda: None,
        within_seconds=4,
        interval_seconds=0.5,
        not_before_seconds=3,
        remaining=lambda: int(state["time"]) if reverse else max(0, int(duration - state["time"])),
    )


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
    state = {"entries": 0, "callbacks": 0, "outcome": 0}

    def deliver():
        if fault == "skip" and state["entries"]:
            return
        state["entries"] += 1
        if not state["callbacks"] or fault == "repeat":
            state["callbacks"] += 1
            state["outcome"] = 2 if fault == "wrong outcome" else 1

    example = DeliveryReplay(
        deliver=deliver,
        entries=lambda: state["entries"],
        callback_entries=lambda: state["callbacks"],
        observe=lambda: state["outcome"],
        expected=1,
    )
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
        BoundedCompletion(
            observe=lambda: None,
            advance=lambda seconds: None,
            recover=lambda: None,
            within_seconds=1,
            interval_seconds=1,
        )
