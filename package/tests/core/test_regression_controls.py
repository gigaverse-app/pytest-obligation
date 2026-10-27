"""A detector must accept its baseline and reject a specific behavioral regression."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from pytest_obligation.regression_controls import assert_detects_regression


def test_a_regression_must_be_visible_and_the_control_must_restore_behavior() -> None:
    state = {"deliveries": 1}

    @contextmanager
    def duplicate_delivery() -> Iterator[None]:
        state["deliveries"] = 2
        try:
            yield
        finally:
            state["deliveries"] = 1

    def check() -> None:
        assert state["deliveries"] == 1, "duplicate delivery"

    assert_detects_regression(check, regression=duplicate_delivery, match="duplicate delivery")
    assert state == {"deliveries": 1}

    with pytest.raises(AssertionError, match="did not detect"):
        assert_detects_regression(lambda: None, regression=duplicate_delivery, match="duplicate delivery")
    assert state == {"deliveries": 1}


def test_a_broken_baseline_never_counts_as_detection() -> None:
    def broken() -> None:
        raise AssertionError("duplicate delivery")

    @contextmanager
    def never_entered() -> Iterator[None]:
        pytest.fail("must validate baseline before applying the regression")
        yield

    with pytest.raises(AssertionError, match="baseline"):
        assert_detects_regression(broken, regression=never_entered, match="duplicate delivery")


@pytest.mark.parametrize("phase", ["enter", "check", "exit"])
def test_unrelated_failures_never_count_as_detection(phase: str) -> None:
    active = False

    @contextmanager
    def regression() -> Iterator[None]:
        nonlocal active
        if phase == "enter":
            raise AssertionError("duplicate delivery")
        active = True
        try:
            yield
        finally:
            active = False
            if phase == "exit":
                raise AssertionError("duplicate delivery")

    def check() -> None:
        if active:
            raise AssertionError("connection unavailable" if phase == "check" else "duplicate delivery")

    with pytest.raises(AssertionError, match="connection unavailable" if phase == "check" else "duplicate delivery"):
        assert_detects_regression(check, regression=regression, match="duplicate delivery")
    assert not active
