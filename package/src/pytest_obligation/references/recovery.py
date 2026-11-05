"""Delivery ordering shared by the framework-free and database reference histories."""

from collections.abc import Callable


def recovery_round(deliver: Callable[[], None], tick: Callable[[], int]) -> None:
    """Deliver queued work, recover missed work, then deliver newly published work."""
    deliver()
    tick()
    deliver()
