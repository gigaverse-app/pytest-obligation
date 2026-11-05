"""Delivery ordering shared by the framework-free and database reference histories."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext


def recover_handoffs(
    deliver: Callable[[], None],
    tick: Callable[[], int],
    round_scope: Callable[[int], AbstractContextManager[object]] | None = None,
) -> None:
    """Three rounds to select, deliver and advance a successor, within the adapter's clock."""
    for round_number in range(1, 4):
        with nullcontext() if round_scope is None else round_scope(round_number):
            deliver()
            tick()
            deliver()
