"""Runtime-neutral recovery coverage and bounded fault histories.

Runtimes supply executable inventories and clock controls. Adopters supply
product examples; they do not implement the proof or copy a recovery selector.
"""

from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from types import MethodType
from typing import Any
from unittest.mock import patch

from pytest_obligation.models import HarnessModel, ObligationContractDesignError
from pytest_obligation.poison import PoisonDropped, PoisonStalled, PoisonSwitch, assert_poison_is_reported


def same_callback(actual: Callable[..., Any], declared: Callable[..., Any]) -> bool:
    """Bound methods must share both implementation and receiver, never just equality or names."""
    return actual is declared or (
        isinstance(actual, MethodType)
        and isinstance(declared, MethodType)
        and actual.__func__ is declared.__func__
        and actual.__self__ is declared.__self__
    )


def validate_recovery_bindings(
    required: Mapping[str, Callable[..., Any]], declared: Mapping[str, Callable[..., Any]]
) -> None:
    """Match declarations to an independently obtained executable inventory, without running fixtures."""
    missing, stale = required.keys() - declared.keys(), declared.keys() - required.keys()
    if missing or stale:
        raise ObligationContractDesignError(
            f"recovery_steps must cover exactly the custom executable callbacks; "
            f"missing={sorted(missing)}, stale={sorted(stale)}. Supply a product example for each actual step."
        )
    # INVARIANT: a declaration cannot borrow another implementation's evidence.
    for name, actual in required.items():
        if not same_callback(actual, declared[name]):
            raise ObligationContractDesignError(f"recovery_steps[{name}] is bound to a different production callback")


class RecoveryExample(HarnessModel):
    """Independent product candidates, arranged in selection order, and observations of what remains owed.

    A structured runtime can supply ``poison`` automatically at its per-item
    action. Arbitrary loops must bind the real per-identity fault seam.
    ``progressed`` is only needed when dispatch progresses work that stays owed.
    """

    make_pending: Callable[[], Hashable]
    pending: Callable[[Any], bool]
    poison: Callable[[Sequence[Any]], AbstractContextManager[Callable[[], int]]] | None = None
    progressed: Callable[[Any], bool] | None = None


class PoisonCounts(HarnessModel):
    """Per-candidate fault observations; one firing cannot stand in for an entire page."""

    counters: tuple[Callable[[], int], ...]

    def __call__(self) -> int:
        return sum(counter() for counter in self.counters)


@contextmanager
def poison_many(
    poison: Callable[[Any], AbstractContextManager[Callable[[], int]]], identities: Sequence[Any]
) -> Iterator[PoisonCounts]:
    """Compose existing single-identity seams; counters survive context exit."""
    with ExitStack() as stack:
        counts = [stack.enter_context(poison(identity)) for identity in identities]
        yield PoisonCounts(counters=tuple(counts))


@contextmanager
def poison_call(
    target: object, attribute: str, identity_of: Callable[..., Any], identities: Sequence[Any]
) -> Iterator[PoisonCounts]:
    """Refuse selected identities at a real call boundary; delegate all others unchanged."""
    original = getattr(target, attribute)
    switch = PoisonSwitch()
    with poison_many(switch.poisoned, identities) as fired:

        def invoke(*args: Any, **kwargs: Any) -> Any:
            switch.check(identity_of(*args, **kwargs), f"{attribute} recovery fault")
            return original(*args, **kwargs)

        with patch.object(target, attribute, invoke):
            yield fired


def assert_recovery_history(
    *,
    name: str,
    example: RecoveryExample,
    run_tick: Callable[[], Any],
    page_size: int,
    poison: bool,
    resume: Callable[[], None],
    assert_held: Callable[[Sequence[Any]], None] | None = None,
) -> None:
    """A full failing page cannot starve healthy work or turn backoff into abandonment.

    Two ticks must reach the next page. Each tick that encounters a fault must
    report it, and each failed candidate must stay owed. After ``resume`` makes
    retries eligible, at most one tick per arranged candidate must make progress.
    The same arrangement without faults is the positive control. No database,
    scheduler, sleep, retry-table implementation or application transition lives here.
    """
    assert page_size > 0, f"{name}: recovery page size must be positive"
    candidates = [example.make_pending() for _ in range(page_size + 1)]
    assert len(set(candidates)) == len(candidates), f"{name}: recovery examples must create independent candidates"
    assert all(example.pending(identity) for identity in candidates), f"{name}: every arranged candidate must owe work"
    bad, healthy = candidates[:-1], candidates[-1]
    progressed: set[Hashable] = set()

    def observe() -> None:
        for identity in candidates:
            advanced = example.progressed(identity) if example.progressed is not None else not example.pending(identity)
            if advanced:
                progressed.add(identity)

    if not poison:
        for _ in range(2):
            run_tick()
            observe()
        assert set(candidates) <= progressed, f"{name}: healthy recovery control did not progress"
        return

    assert example.poison is not None, f"{name}: bind the real per-identity poison seam"
    counts = [0] * len(bad)
    for tick_index in range(2):
        with example.poison(bad) as fired:
            assert isinstance(fired, PoisonCounts) and len(fired.counters) == len(bad), (
                f"{name}: use poison_many or poison_call to observe each candidate's fault"
            )
            escaped: Exception | None = None
            try:
                run_tick()
            except Exception as error:  # noqa: BLE001 - this is the production report under test
                escaped = error
        # Faults belong to production execution, not product observation. Some
        # native observations inspect the real selector with deliveries held.
        # Their calls must neither trip the fault nor count as proof it fired.
        counts = [total + counter() for total, counter in zip(counts, fired.counters, strict=True)]
        # Check every tick: an earlier loud report cannot hide a later silent failure.
        if fired() > 0:
            assert_poison_is_reported(name, escaped)
        elif escaped is not None:
            raise escaped
        if tick_index == 0:
            assert fired() > 0, f"{name}: the poison never fired; bind the real per-identity action"
        observe()
        if not all(example.pending(identity) for identity in bad):
            raise PoisonDropped(f"{name}: failed recovery work is no longer owed")
    if healthy not in progressed:
        raise PoisonStalled(f"{name}: healthy work behind a poisoned page did not progress within two ticks")
    assert all(count > 0 for count in counts), f"{name}: the poison never fired for every page candidate"
    if assert_held is not None:
        assert_held(bad)
        with example.poison(bad) as fired:
            run_tick()
            assert fired() == 0, f"{name}: deferred candidates were retried before their hold ended"
    resume()
    for _ in candidates:
        run_tick()
        observe()
        if set(bad) <= progressed:
            break
    assert set(bad) <= progressed, f"{name}: deferred recovery work was abandoned"
