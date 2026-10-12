"""Product completion bounds and duplicate delivery, separate from raw effect replay.

These proofs drive an adopter's real delivery and recovery paths. Simulated time
bounds describe the supplied scheduler, not a production latency SLA.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

from pydantic import Field, FiniteFloat, model_validator

from pytest_obligation.binding import INVOCATION_AUTHORING_OPERATIONS, assert_binding_reaches_production
from pytest_obligation.models import HarnessModel

ObservationT = TypeVar("ObservationT")


class BoundedCompletion(HarnessModel, Generic[ObservationT]):
    observe: Callable[[], ObservationT]
    expected: ObservationT
    advance: Callable[[float], object]
    recover: Callable[[], object]
    within_seconds: FiniteFloat = Field(gt=0)
    interval_seconds: FiniteFloat = Field(gt=0)
    not_before_seconds: FiniteFloat = Field(default=0, ge=0)
    remaining: Callable[[], int] | None = None

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.not_before_seconds > self.within_seconds or self.interval_seconds > self.within_seconds:
            raise ValueError("completion bounds are inconsistent")
        if self.within_seconds / self.interval_seconds > 10000:
            raise ValueError("completion proof exceeds 10000 clock steps")
        return self


def assert_completes_within(example: BoundedCompletion) -> None:
    """Require the declared terminal outcome, without early or reversed progress."""
    assert_binding_reaches_production(
        adopter="bounded completion",
        field="recover",
        binding=example.recover,
        forbidden=INVOCATION_AUTHORING_OPERATIONS,
        production_shape="the actual recovery entry point",
    )
    assert example.observe() != example.expected, "completion example already has its terminal outcome"
    previous = example.remaining() if example.remaining is not None else None
    elapsed = 0.0
    steps = 0
    while True:
        example.recover()
        if example.remaining is not None:
            current = example.remaining()
            assert previous is not None and 0 <= current <= previous, "completion progress reversed or became negative"
            previous = current
        if example.observe() == example.expected:
            assert elapsed >= example.not_before_seconds, "terminal outcome arrived before the declared minimum wait"
            return
        assert elapsed < example.within_seconds, "declared terminal outcome was not reached within the time bound"
        steps += 1
        target = min(steps * example.interval_seconds, example.within_seconds)
        example.advance(target - elapsed)
        elapsed = target


class DeliveryReplay(HarnessModel, Generic[ObservationT]):
    """Replay the same production delivery; it may fence out its callback.

    Count entries at the real delivery boundary, not calls to the test's wrapper.
    This is deliberately separate from ReplaySafeEffect, which must enter the raw
    external effect twice. Its name in generated reports preserves that scope.
    """

    deliver: Callable[[], object]
    entries: Callable[[], int]
    observe: Callable[[], ObservationT]
    expected: ObservationT
    callback_entries: Callable[[], int]


def assert_delivery_replay(example: DeliveryReplay) -> None:
    assert_binding_reaches_production(
        adopter="delivery replay",
        field="deliver",
        binding=example.deliver,
        forbidden=INVOCATION_AUTHORING_OPERATIONS,
        production_shape="the actual delivery entry point",
    )
    initial = example.observe()
    assert initial != example.expected, "delivery replay example already has its terminal outcome"
    entries, callbacks = example.entries(), example.callback_entries()
    for index in (1, 2):
        example.deliver()
        assert example.entries() == entries + index, "replay did not enter the production delivery boundary"
        assert example.callback_entries() == callbacks + 1, "duplicate delivery repeated or skipped its callback"
        assert example.observe() == example.expected, "delivery missed the declared product outcome"
