"""
Root controls for the owed-row proofs of a polling selection.

A polling selection keeps the rows it serves, so its control reads work
instead of the row leaving, and its poison case runs a second tick. Each check
must fail on the defect it names and pass on the repair: a step that settles
the row (so the selection is not polling at all), one that does nothing, one
whose only effect is a provider call nobody counts, a tick that serves each
row once, a loop that backs off the whole tick after a failure, and a loop
that drops the poisoned row.
"""

from collections.abc import Callable
from typing import Any

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from pytest_obligation.host import current_host, hosted
from pytest_obligation.integrations.django.owed_references import PrimitiveOwner, owed_owners, poll
from pytest_obligation.integrations.django.owed_references import isolated_primitive as isolated_primitive
from pytest_obligation.integrations.django.owed_rows import (
    OwedRows,
    assert_a_polled_row_is_served_and_stays_selected,
    assert_a_soft_time_limit_ends_the_loop,
    assert_the_loop_isolates_a_poisoned_row,
)
from pytest_obligation.poison import PoisonDropped, PoisonStalled, PoisonSwitch, PoisonUnreported

Worker = Callable[[int], None]


@pytest.fixture(autouse=True)
def _host_for_controls():
    with hosted(
        current_host().model_copy(
            update={"production_packages": frozenset({"pytest_obligation"}), "stop_exception": SoftTimeLimitExceeded}
        )
    ):
        yield


def _owed() -> PrimitiveOwner:
    return PrimitiveOwner.objects.create(value="valid")


def _settling(owner_id: int) -> None:
    """DEFECTIVE as a polling declaration: settles the row, so the selection is not polling at all."""
    PrimitiveOwner.objects.filter(pk=owner_id).update(completed_at=timezone.now())


def _doing_nothing(_owner_id: int) -> None:
    """DEFECTIVE: reads nothing and writes nothing, so a polled row is never served."""


class _Provider:
    """A provider fake whose only observable effect is the calls it receives."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def refresh(self, owner_id: int) -> None:
        self.calls.append(owner_id)


class _PollingTick:
    """A one-page polling tick that records each identity it reaches before running the step."""

    def __init__(
        self,
        step: Worker,
        *,
        isolate: bool = True,
        silent: bool = False,
        retires_failures: bool = False,
        honours_stop: bool = True,
        once_per_identity: bool = False,
        backs_off_after_a_failure: bool = False,
        holds_back_failed_rows: bool = False,
    ):
        self.step = step
        self.isolate = isolate
        self.silent = silent
        self.retires_failures = retires_failures
        self.honours_stop = honours_stop
        self.once_per_identity = once_per_identity
        self.backs_off_after_a_failure = backs_off_after_a_failure
        self.holds_back_failed_rows = holds_back_failed_rows
        self.dispatched: list[int] = []
        self.served: set[int] = set()
        self.failed_last_tick: set[int] = set()

    def run(self) -> None:
        failed_last_tick, self.failed_last_tick = self.failed_last_tick, set()
        if self.backs_off_after_a_failure and failed_last_tick:
            return  # DEFECTIVE: one poisoned row pauses every polled row on alternate ticks
        failures: list[Exception] = []
        for owner_id in owed_owners().values_list("pk", flat=True)[:10]:
            if self.once_per_identity and owner_id in self.served:
                continue  # DEFECTIVE: a polled row is served once, not every tick
            if self.holds_back_failed_rows and owner_id in failed_last_tick:
                continue  # REPAIR-COMPATIBLE: a per-identity backoff holds back only the failing row
            self.dispatched.append(owner_id)
            if not self.isolate:
                self.step(owner_id)
                self.served.add(owner_id)
                continue
            try:
                self.step(owner_id)
            except Exception as error:
                if self.honours_stop and isinstance(error, SoftTimeLimitExceeded):
                    raise
                if self.retires_failures:
                    _settling(owner_id)
                self.failed_last_tick.add(owner_id)
                failures.append(error)
            else:
                self.served.add(owner_id)
        if failures and not self.silent:
            raise ExceptionGroup("isolated polling failures", failures)


def _polling_loop(worker: Worker = poll, **tick_options: Any) -> OwedRows:
    """A loop whose per-row step checks a switch first, as a production seam would."""
    refusals = PoisonSwitch()

    def step(owner_id: int) -> None:
        refusals.check(owner_id)
        worker(owner_id)

    tick = _PollingTick(step, **tick_options)
    return OwedRows(
        make_owed=_owed,
        execute=step,
        run_tick=tick.run,
        dispatched_ids=lambda: tick.dispatched,
        poison=lambda owner: refusals.poisoned(owner.pk),
    )


def _served(rows: OwedRows) -> None:
    assert_a_polled_row_is_served_and_stays_selected("self-test polling sweep", owed_owners, rows)


@pytest.mark.usefixtures("isolated_primitive")
class TestAPolledRowIsServedAndStaysSelected:
    """The polling control, in place of the leave-the-selection control."""

    def test_accepts_a_step_that_polls_the_row(self):
        _served(_polling_loop())

    def test_accepts_a_provider_only_effect_counted_by_effect_calls_for(self):
        provider = _Provider()
        rows = _polling_loop(provider.refresh).model_copy(
            update={"effect_calls_for": lambda owner: provider.calls.count(owner.pk)}
        )
        _served(rows)

    def test_rejects_a_provider_only_effect_nobody_counts(self):
        with pytest.raises(AssertionError, match="did nothing at all to a valid polled row.*effect_calls_for"):
            _served(_polling_loop(_Provider().refresh))

    def test_rejects_a_polling_declaration_on_a_step_that_settles_the_row(self):
        with pytest.raises(AssertionError, match="left the selection .* remove `polling=`"):
            _served(_polling_loop(_settling))

    def test_rejects_a_step_that_does_nothing(self):
        with pytest.raises(AssertionError, match="one delivery to the production step did nothing at all"):
            _served(_polling_loop(_doing_nothing))

    def test_rejects_a_step_that_fails_a_valid_row(self):
        def rejecting(owner_id: int) -> None:
            raise ValueError(f"cannot poll owner {owner_id}")

        with pytest.raises(AssertionError, match="failed on a valid polled row .*ValueError"):
            _served(_polling_loop(rejecting))

    def test_rejects_a_tick_that_serves_each_row_once(self):
        with pytest.raises(AssertionError, match="production tick 2 of 2 did not dispatch a valid polled row"):
            _served(_polling_loop(once_per_identity=True))

    def test_rejects_a_bound_still_owed(self):
        rows = _polling_loop().model_copy(update={"still_owed": lambda owner: owner.completed_at is None})
        with pytest.raises(AssertionError, match="a polling selection keeps the row it served"):
            _served(rows)


def _isolated(rows: OwedRows, *, polling: bool = True) -> None:
    assert_the_loop_isolates_a_poisoned_row("self-test polling sweep", owed_owners, rows, polling=polling)


@pytest.mark.usefixtures("isolated_primitive")
class TestAPollingLoopIsolatesAPoisonedRow:
    """Invariant 12 for a polling selection: the first tick's oracle, then a second tick."""

    def test_accepts_an_isolating_polling_loop(self):
        _isolated(_polling_loop())

    def test_accepts_a_loop_that_backs_off_only_the_poisoned_row(self):
        _isolated(_polling_loop(holds_back_failed_rows=True))

    def test_rejects_a_loop_that_backs_off_the_whole_tick_after_a_failure(self):
        with pytest.raises(PoisonStalled, match="on the tick after a poisoned one"):
            _isolated(_polling_loop(backs_off_after_a_failure=True))

    def test_the_whole_tick_backoff_is_only_visible_on_the_second_tick(self):
        # The same loop passes the one-tick oracle: the second tick is what finds it.
        _isolated(_polling_loop(backs_off_after_a_failure=True), polling=False)

    def test_rejects_a_loop_that_stops_at_the_poisoned_row(self):
        with pytest.raises(PoisonStalled, match="did not progress in the same tick"):
            _isolated(_polling_loop(isolate=False))

    def test_rejects_a_loop_that_isolates_and_reports_nothing(self):
        with pytest.raises(PoisonUnreported, match="reported nothing"):
            _isolated(_polling_loop(silent=True))

    def test_rejects_a_loop_that_retires_the_poisoned_row(self):
        with pytest.raises(PoisonDropped, match="no longer owed"):
            _isolated(_polling_loop(retires_failures=True))

    def test_rejects_a_bound_still_owed(self):
        rows = _polling_loop().model_copy(update={"still_owed": lambda owner: owner.completed_at is None})
        with pytest.raises(AssertionError, match="a polling selection keeps the row it served"):
            _isolated(rows)


@pytest.mark.usefixtures("isolated_primitive")
class TestASoftTimeLimitEndsAPollingLoop:
    """Invariant 12b is unchanged for a polling selection: one tick, the interrupted row still selected."""

    def test_accepts_a_loop_that_honours_stop(self):
        assert_a_soft_time_limit_ends_the_loop("self-test polling sweep", owed_owners, _polling_loop(), polling=True)

    def test_rejects_a_bound_still_owed(self):
        rows = _polling_loop().model_copy(update={"still_owed": lambda owner: owner.completed_at is None})
        with pytest.raises(AssertionError, match="a polling selection keeps the row it served"):
            assert_a_soft_time_limit_ends_the_loop("self-test polling sweep", owed_owners, rows, polling=True)
