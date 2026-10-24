"""Every isolation/stop verdict needs a conforming control and a specific counterfeit."""

import asyncio

import pytest

from pytest_obligation.host import Host, hosted
from pytest_obligation.poison import (
    PoisonDropped,
    PoisonedIdentity,
    PoisonStalled,
    PoisonSwitch,
    PoisonUnreported,
    StopRequestContinued,
    StopRequestDropped,
    StopRequested,
    StopRequestIsolated,
    StopRequestSwallowed,
    assert_a_stop_request_ends_the_tick,
    assert_poison_is_isolated,
    carries_poison,
    poison_gap,
    stop_gap,
)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("healthy", None),
        ("abort", PoisonStalled),
        ("drop", PoisonDropped),
        ("swallow", PoisonUnreported),
        ("never-fires", AssertionError),
        ("wrap", None),
    ],
)
def test_poison_oracle(mode: str, expected: type[Exception] | None) -> None:
    switch = PoisonSwitch()
    progressed: list[int] = []
    owed = {1, 2}

    def tick() -> None:
        failures = []
        for identity in (1, 2):
            try:
                if mode != "never-fires":
                    switch.check(identity)
            except PoisonedIdentity as error:
                if mode == "abort":
                    raise
                if mode == "drop":
                    owed.remove(identity)
                failures.append(error)
                continue
            progressed.append(identity)
        if failures and mode != "swallow":
            group = ExceptionGroup("identities", failures)
            if mode == "wrap":
                raise RuntimeError("recovery failed") from group
            raise group

    def prove() -> None:
        assert_poison_is_isolated(
            name="loop",
            poison=switch.poisoned(1),
            run_tick=tick,
            progressed=lambda: 2 in progressed,
            still_owed=lambda: 1 in owed,
        )

    if expected is None:
        prove()
    else:
        with pytest.raises(expected):
            prove()


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("healthy", None),
        ("drop", StopRequestDropped),
        ("swallow", StopRequestSwallowed),
        ("isolate", StopRequestIsolated),
        ("continue", StopRequestContinued),
        ("never-fires", AssertionError),
    ],
)
@pytest.mark.parametrize("stop_kind", [StopRequested, asyncio.CancelledError])
def test_stop_oracle(mode: str, expected: type[Exception] | None, stop_kind: type[BaseException]) -> None:
    switch = PoisonSwitch()
    progressed: list[int] = []
    owed = {1, 2}

    def tick() -> None:
        try:
            if mode != "never-fires":
                switch.check(1)
        except stop_kind as error:
            if mode == "drop":
                owed.remove(1)
            if mode == "swallow":
                return
            if mode == "isolate":
                progressed.append(2)
                raise BaseExceptionGroup("wrongly isolated", [error]) from None
            if mode == "continue":
                progressed.append(2)
            raise

    def prove() -> None:
        with hosted(Host(stop_exception=stop_kind)):
            assert_a_stop_request_ends_the_tick(
                name="loop",
                poison=switch.poisoned(1),
                run_tick=tick,
                progressed=lambda: 2 in progressed,
                still_owed=lambda: 1 in owed,
            )

    if expected is None:
        prove()
    else:
        with pytest.raises(expected):
            prove()


def test_host_stop_exception_and_context_restoration() -> None:
    class HostStop(Exception):
        pass

    switch = PoisonSwitch()
    with hosted(Host(stop_exception=HostStop)):
        assert_a_stop_request_ends_the_tick(
            name="host",
            poison=switch.poisoned(1),
            run_tick=lambda: switch.check(1),
            progressed=lambda: False,
            still_owed=lambda: True,
        )
        with switch.poisoned(1), pytest.raises(PoisonedIdentity):
            switch.check(1)


def test_cause_cycles_do_not_hide_poison_or_loop_forever() -> None:
    first, second = RuntimeError("first"), RuntimeError("second")
    first.__cause__, second.__cause__ = second, first
    assert not carries_poison(first)
    second.__context__ = PoisonedIdentity()
    assert carries_poison(first)


def test_gap_is_specific_and_rejects_multiple_failures() -> None:
    assert poison_gap({"proof[dropped]": "lost"}, "proof") == ("lost", PoisonDropped)
    assert stop_gap({"proof[dropped]": "lost"}, "proof") == ("lost", StopRequestDropped)
    with pytest.raises(AssertionError, match="declare one gap"):
        poison_gap({"proof[dropped]": "lost", "proof[stalled]": "blocked"}, "proof")


def test_rearming_a_switch_counts_only_this_scope_and_preserves_outer_scopes() -> None:
    switch = PoisonSwitch()
    with switch.poisoned(1) as outer:
        with pytest.raises(PoisonedIdentity):
            switch.check(1)
        with switch.poisoned(1) as inner:
            assert inner() == 0
            with pytest.raises(PoisonedIdentity):
                switch.check(1)
        assert inner() == 1
        with pytest.raises(PoisonedIdentity):
            switch.check(1)
    assert outer() == 3
    with switch.poisoned(1) as again:
        assert again() == 0
    switch.check(1)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_unrelated_process_interrupt_is_not_a_stop_verdict(interrupt):
    switch = PoisonSwitch()

    def tick():
        raise interrupt()

    with pytest.raises(interrupt):
        assert_a_stop_request_ends_the_tick(
            name="unrelated process interruption",
            poison=switch.poisoned(1),
            run_tick=tick,
            progressed=lambda: False,
            still_owed=lambda: True,
        )
