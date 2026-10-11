"""Poison isolation and cooperative stop oracles, shared by every recovery proof."""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from typing import Any, TypedDict, TypeVar

from pydantic import PrivateAttr

from pytest_obligation.host import current_host
from pytest_obligation.models import MutableHarnessModel


class PoisonedIdentity(Exception):
    """What a poisoned per-identity seam raises; the oracle looks for it in what the tick reported."""


class PoisonNotIsolated(AssertionError):
    """
    The isolation invariant itself failed, as opposed to its positive control.

    Raised as one of its three subclasses, one per requirement, so a declared
    legacy gap names the one failure it expects (``"<proof>[unreported]"``) and
    a regression to another still fails it. A binding whose poison never fires
    raises neither.
    """

    #: The suffix a gap on the poison proof uses for this failure.
    gap_kind = ""


class PoisonStalled(PoisonNotIsolated):
    """The identity behind the poisoned one did not progress: the loop stops at its first failure."""

    gap_kind = "stalled"


class PoisonDropped(PoisonNotIsolated):
    """The poisoned identity is no longer owed: the loop settled, retired or deleted what it could not serve."""

    gap_kind = "dropped"


class PoisonUnreported(PoisonNotIsolated):
    """The tick isolated the failure and reported nothing: it logs and moves on, so nothing alerts."""

    gap_kind = "unreported"


#: Gap suffix -> the failure a gap with it expects, in the order the oracle checks them.
POISON_FAILURES: dict[str, type[PoisonNotIsolated]] = {
    failure.gap_kind: failure for failure in (PoisonStalled, PoisonDropped, PoisonUnreported)
}


class StopRequested(Exception):
    """a cooperative stop request, raised by an armed :class:`PoisonSwitch` inside :func:`stop_requests`."""


class StopRequestNotHonoured(AssertionError):
    """
    A tick did not end on the soft time limit raised in one identity's step.

    Raised as one of its four subclasses, so a declared legacy gap names the
    one failure it expects (``"<proof>[swallowed]"``) and a regression to
    another still fails it. A binding whose seam never fired raises neither.
    """

    #: The suffix a gap on the stop-request proof uses for this failure.
    gap_kind = ""


class StopRequestDropped(StopRequestNotHonoured):
    """The interrupted identity is no longer owed: the stop request settled, retired or deleted it."""

    gap_kind = "dropped"


class StopRequestSwallowed(StopRequestNotHonoured):
    """The tick caught the soft limit and reported nothing of it, so Celery's hard kill ends the task instead."""

    gap_kind = "swallowed"


class StopRequestIsolated(StopRequestNotHonoured):
    """The tick isolated the soft limit as one identity's failure, ran on, and reported it with the rest."""

    gap_kind = "isolated"


class StopRequestContinued(StopRequestNotHonoured):
    """The soft limit ended the task, but only after the tick ran the identity behind the interrupted one."""

    gap_kind = "continued"


#: Gap suffix -> the failure a gap with it expects, in the order the oracle checks them.
STOP_FAILURES: dict[str, type[StopRequestNotHonoured]] = {
    failure.gap_kind: failure
    for failure in (StopRequestDropped, StopRequestSwallowed, StopRequestIsolated, StopRequestContinued)
}


FailureT = TypeVar("FailureT", bound=AssertionError)


def _declared_gap(
    gaps: Mapping[str, str], proof: str, failures: Mapping[str, type[FailureT]]
) -> tuple[str, type[FailureT]] | None:
    declared = [(gaps[f"{proof}[{kind}]"], failure) for kind, failure in failures.items() if f"{proof}[{kind}]" in gaps]
    assert len(declared) <= 1, f"{proof}: declare one gap, the failure the loop shows first, not {len(declared)}"
    return declared[0] if declared else None


def poison_gap(gaps: Mapping[str, str], proof: str) -> tuple[str, type[PoisonNotIsolated]] | None:
    """The gap declared on one poison proof, ``"<proof>[<kind>]"``, as (reason, the failure it expects)."""
    return _declared_gap(gaps, proof, POISON_FAILURES)


def poison_gap_names(proof: str) -> set[str]:
    return {f"{proof}[{kind}]" for kind in POISON_FAILURES}


def stop_gap(gaps: Mapping[str, str], proof: str) -> tuple[str, type[StopRequestNotHonoured]] | None:
    """The gap declared on one stop-request proof, ``"<proof>[<kind>]"``, as (reason, the failure it expects)."""
    return _declared_gap(gaps, proof, STOP_FAILURES)


def stop_gap_names(proof: str) -> set[str]:
    return {f"{proof}[{kind}]" for kind in STOP_FAILURES}


class PoisonedHistory(TypedDict):
    """One poisoned identity ahead of a healthy one, as both oracles take it: the seam and the two observations."""

    poison: AbstractContextManager[Callable[[], int]]
    progressed: Callable[[], bool]
    still_owed: Callable[[], bool]


#: Whether an armed switch raises Celery's soft limit instead of ``PoisonedIdentity``.
_STOP_REQUESTED: ContextVar[bool] = ContextVar("poison_switch_raises_a_stop_request", default=False)


@contextmanager
def stop_requests() -> Iterator[None]:
    """Inside this block an armed :class:`PoisonSwitch` raises :class:`StopRequested` instead."""
    token = _STOP_REQUESTED.set(True)
    try:
        yield
    finally:
        _STOP_REQUESTED.reset(token)


class PoisonSwitch(MutableHarnessModel):
    """
    One per-identity seam that raises for a poisoned identity and counts each time it did.

    The production seam's stand-in calls ``check(key)``; ``poisoned(key)`` arms
    it for one identity and yields ``fired()``.
    """

    _armed: set[Any] = PrivateAttr(default_factory=set)
    _fired: Counter[Any] = PrivateAttr(default_factory=Counter)

    def check(self, key: Any, message: str = "the per-identity seam refused this identity") -> None:
        if key in self._armed:
            self._fired[key] += 1
            if _STOP_REQUESTED.get():
                # The same seam, reached while the task's soft time limit fires.
                raise (current_host().stop_exception or StopRequested)(message)
            raise PoisonedIdentity(message)

    @contextmanager
    def poisoned(self, key: Any) -> Iterator[Callable[[], int]]:
        self._armed.add(key)
        try:
            yield lambda: self._fired[key]
        finally:
            self._armed.discard(key)


def carries_poison(error: BaseException | None) -> bool:
    """Whether ``error`` carries a ``PoisonedIdentity``: itself, inside an exception group, or in its cause chain."""
    seen: set[int] = set()
    pending = [error]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, PoisonedIdentity):
            return True
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        pending.extend((current.__cause__, current.__context__))
    return False


def assert_poison_is_isolated(
    *,
    name: str,
    poison: AbstractContextManager[Callable[[], int]],
    run_tick: Callable[[], object],
    progressed: Callable[[], bool],
    still_owed: Callable[[], bool],
) -> BaseException | None:
    """
    Run one tick with one identity poisoned, and require the four observations above.

    ``poison`` is armed for the identity that leads the tick's selection;
    ``progressed`` and ``still_owed`` observe the healthy and the poisoned
    identity after the tick. Returns what the tick raised, for checks a caller
    adds on top (a later phase ran, a paging phase deferred the identity).
    """
    escaped: BaseException | None = None
    with poison as fired:
        try:
            run_tick()
        except Exception as error:  # noqa: BLE001 - the report under test, judged below
            escaped = error
    # POSITIVE CONTROL: a poison the tick never met proves nothing about isolation.
    assert fired() >= 1, (
        f"{name}: the poison never fired, so this proves nothing about isolation. The binding "
        f"patched a seam the tick does not call for the poisoned identity; poison the per-identity "
        f"seam the production tick actually runs (raised: {escaped!r})"
    )
    # INVARIANT ENFORCEMENT: progress behind the poison, a loud report, and nothing dropped.
    if not progressed():
        raise PoisonStalled(
            f"{name}: the identity behind a poisoned one did not progress in the same tick (the tick "
            f"raised {escaped!r}). Selection is oldest first, so the poisoned identity leads every tick "
            f"and blocks everything behind it: isolate per-identity failures and report them after the loop"
        ) from escaped
    # Owed before reported: a loop that reports nothing must not hide a dropped row.
    if not still_owed():
        raise PoisonDropped(
            f"{name}: the poisoned identity is no longer owed after the tick. Isolation must leave a "
            f"failing identity selectable (or held with backoff), not drop, settle or retire it"
        ) from escaped
    if not carries_poison(escaped):
        raise PoisonUnreported(
            f"{name}: the tick isolated the poisoned identity but reported nothing (it raised {escaped!r}). "
            f"A loop that logs and moves on reports success, so the failure is invisible to the task, "
            f"Sentry and the alerts; report the failures the tick isolated"
        ) from escaped
    return escaped


def _ends_with(error: BaseException | None, kind: type[BaseException]) -> bool:
    """Whether ``error`` is ``kind`` or has it in its cause chain; a group's members do not count."""
    seen: set[int] = set()
    current = error
    while current is not None and id(current) not in seen:
        # A group is isolation, even when raised inside the stop exception handler.
        if isinstance(current, BaseExceptionGroup):
            return False
        if isinstance(current, kind):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _carries(error: BaseException | None, kind: type[BaseException]) -> bool:
    """Whether ``error`` carries ``kind`` anywhere: itself, a group member, or a cause chain."""
    seen: set[int] = set()
    pending = [error]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, kind):
            return True
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        pending.extend((current.__cause__, current.__context__))
    return False


def assert_a_stop_request_ends_the_tick(
    *,
    name: str,
    poison: AbstractContextManager[Callable[[], int]],
    run_tick: Callable[[], object],
    progressed: Callable[[], bool],
    still_owed: Callable[[], bool],
) -> BaseException | None:
    """
    Run one tick whose poisoned seam raises a cooperative stop request, and require the tick to end on it.

    The host supplies a stop exception so a task can stop before the hard
    kill. Inside a recovery loop it is not the identity's failure: the tick
    must stop at that identity, with the limit escaping to the task, and leave
    the identity owed. ``poison`` is armed for the identity that leads the
    selection, exactly as for :func:`assert_poison_is_isolated`; ``progressed``
    and ``still_owed`` observe the identity behind it and the interrupted one.
    Returns what the tick raised.
    """
    escaped: BaseException | None = None
    with stop_requests(), poison as fired:
        try:
            run_tick()
        except Exception as error:  # noqa: BLE001 - the stop request under test, judged below
            escaped = error
    # POSITIVE CONTROL: a seam the tick never reached proves nothing.
    assert fired() >= 1, (
        f"{name}: the stop request never fired, so this proves nothing. The binding arms a seam the tick does not "
        f"call for the poisoned identity (raised: {escaped!r})"
    )
    assert not _carries(escaped, PoisonedIdentity), (
        f"{name}: the armed seam raised PoisonedIdentity inside stop_requests(). Bind the per-identity seam through "
        f"PoisonSwitch.check, which raises the soft time limit here, instead of raising PoisonedIdentity itself"
    )
    # INVARIANT ENFORCEMENT: owed first, so a declared [swallowed] gap cannot hide a dropped identity.
    if not still_owed():
        raise StopRequestDropped(
            f"{name}: the identity whose step hit the soft time limit is no longer owed after the tick (it "
            f"raised {escaped!r}). An interrupted step must leave its identity for the next run"
        ) from escaped
    if not _ends_with(escaped, current_host().stop_exception or StopRequested):
        if _carries(escaped, current_host().stop_exception or StopRequested):
            raise StopRequestIsolated(
                f"{name}: the tick isolated a cooperative stop request as one identity's failure and ran on (it "
                f"raised {escaped!r}). The limit asks the task to stop before the hard kill: let it end the tick, as "
                f"recovery_tick's isolate() does (ends_the_tick)"
            ) from escaped
        raise StopRequestSwallowed(
            f"{name}: the tick caught a cooperative stop request and did not raise it (it raised {escaped!r}), so "
            f"the task runs on until the hard kill. Re-raise the host stop exception wherever the step catches "
            f"Exception, or run the step in recovery_tick's isolate()"
        ) from escaped
    if progressed():
        raise StopRequestContinued(
            f"{name}: the identity behind the interrupted one ran after a cooperative stop request. The limit must end "
            f"the tick at the identity it interrupted"
        ) from escaped
    return escaped
