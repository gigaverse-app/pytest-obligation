"""
Root controls for the native owed-row admissibility invariants.

Each invariant must fail on the defect it names and pass on the repair, using a
test-owned selection, worker and tick over a real table: a worker that raises
on a blank value, one that hands off to a task that raises (or only retries,
through Celery's autoretry), one that returns without doing anything, and a
tick that stops at its first failing identity. The binding checks get the same
treatment: a recorder that reads the table, a tick that walks another order,
and an edge family declared on the wrong model.
"""

import functools
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from pytest_obligation.host import current_host, hosted
from pytest_obligation.integrations.django.edge_values import CandidateEdge
from pytest_obligation.integrations.django.lifecycle_states import Lifecycle
from pytest_obligation.integrations.django.owed_references import PrimitiveOwner, PrimitiveWork, owed_owners
from pytest_obligation.integrations.django.owed_references import isolated_primitive as isolated_primitive
from pytest_obligation.integrations.django.owed_rows import (
    NOTHING_ENDS_A_FAILURE,
    OWED_ROW_PROOFS,
    EdgeFamily,
    FailureEnds,
    OwedRowNotHandled,
    OwedRows,
    assert_a_soft_time_limit_ends_the_loop,
    assert_database_legal_owed_row_is_handled,
    assert_inadmissible_owed_row_does_not_block_the_next,
    assert_owed_row_bindings_are_production_bound,
    assert_the_loop_isolates_a_poisoned_row,
    assert_the_tick_dispatches_owed_rows_in_selection_order,
    assert_valid_owed_row_leaves_the_selection,
    failure_ends_of_sweep,
)
from pytest_obligation.poison import (
    PoisonDropped,
    PoisonedIdentity,
    PoisonNotIsolated,
    PoisonStalled,
    PoisonSwitch,
    PoisonUnreported,
    StopRequestContinued,
    StopRequestDropped,
    StopRequestIsolated,
    StopRequestSwallowed,
    stop_requests,
)
from pytest_obligation.profiles.automatic_recovery import DueWorkSweep, declared_recovery_delay


@pytest.fixture(autouse=True)
def _host_for_controls():
    with hosted(
        current_host().model_copy(
            update={
                "production_packages": frozenset({"pytest_obligation"}),
                "stop_exception": SoftTimeLimitExceeded,
            }
        )
    ):
        yield


BLANK = CandidateEdge(field="value", kind="blank", value="")
LONGEST = CandidateEdge(field="value", kind="max_length", value="x" * 40)
Worker = Callable[[int], None]


def _owed() -> PrimitiveOwner:
    return PrimitiveOwner.objects.create(value="valid")


def _settle(owner: PrimitiveOwner) -> None:
    PrimitiveOwner.objects.filter(pk=owner.pk).update(completed_at=timezone.now())


#: The terminal state of these owners' lifecycle: what a worker that gives up on a row writes.
RETIRED = "retired"


def _retire(owner_id: int) -> None:
    PrimitiveOwner.objects.filter(pk=owner_id).update(value=RETIRED, completed_at=timezone.now())


def _hand_off(owner_id: int) -> None:
    """Settles the row here and claims it for another owner, as email unpark hands a campaign to the reaper."""
    PrimitiveOwner.objects.filter(pk=owner_id).update(completed_at=timezone.now(), claimed_at=timezone.now())


def _rejecting_blank(owner_id: int) -> None:
    """DEFECTIVE: the work built from a blank value fails validation, as source_key='' did."""
    owner = PrimitiveOwner.objects.get(pk=owner_id)
    if owner.value == "":
        raise ValueError("source_key may not be blank")
    _settle(owner)


def _ignoring_blank(owner_id: int) -> None:
    """DEFECTIVE: declines the blank row without recording anything, so it is selected forever."""
    owner = PrimitiveOwner.objects.get(pk=owner_id)
    if owner.value != "":
        _settle(owner)


@shared_task(name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.finalize_owner_task")
def finalize_owner_task(owner_id: int) -> None:
    """The follow-up a confirming worker hands off to; it is where the row is read."""
    _rejecting_blank(owner_id)


def _handing_off(owner_id: int) -> None:
    """DEFECTIVE through its handoff: confirms, then publishes the finalizer that raises on blank."""
    finalize_owner_task.delay(owner_id)


@shared_task(
    name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.finalize_owner_quietly_task"
)
def finalize_owner_quietly_task(owner_id: int) -> None:
    """A follow-up that returns early on a blank value: its publisher looks busy every tick."""
    _ignoring_blank(owner_id)


def _handing_off_to_an_idle_task(owner_id: int) -> None:
    """DEFECTIVE through its handoff: the only effect is a publication whose task idles on the row."""
    finalize_owner_quietly_task.delay(owner_id)


@shared_task(
    name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.finalize_owner_with_retries_task",
    autoretry_for=(ValueError,),
    retry_backoff=False,
    retry_kwargs={"countdown": 60},
)
def finalize_owner_with_retries_task(owner_id: int) -> None:
    """The recording finalizers' shape: every raise becomes a Celery retry instead of a failure."""
    _rejecting_blank(owner_id)


def _handing_off_to_a_retrying_task(owner_id: int) -> None:
    """DEFECTIVE through its handoff: the finalizer raises on blank, and its autoretry repeats the raise."""
    finalize_owner_with_retries_task.delay(owner_id)


def _handing_off_after_commit(owner_id: int) -> None:
    """DEFECTIVE through a handoff published after commit (AGENTS L4): the finalizer raises on blank."""
    with transaction.atomic():
        transaction.on_commit(lambda: finalize_owner_task.delay(owner_id))


def _handing_off_with_a_countdown(owner_id: int) -> None:
    """DEFECTIVE through a delayed handoff: a countdown does not make another task's failure a retry."""
    finalize_owner_task.apply_async((owner_id,), countdown=5)


def _stamping_then_rejecting_blank(owner_id: int) -> None:
    """DEFECTIVE: records an attempt on a column the selection ignores, then raises on blank."""
    PrimitiveOwner.objects.filter(pk=owner_id).update(claimed_at=timezone.now())
    _rejecting_blank(owner_id)


def _retiring_blank(owner_id: int) -> None:
    """REPAIR: a row that cannot be served is settled visibly instead of retried forever."""
    _settle(PrimitiveOwner.objects.get(pk=owner_id))


class _Tick:
    """A one-page recovery tick that records each identity it reaches before running the worker."""

    def __init__(
        self,
        selection: Callable[[], QuerySet[PrimitiveOwner]],
        worker: Worker,
        *,
        isolate: bool,
        newest_first: bool = False,
        silent: bool = False,
        retires_failures: bool = False,
        honours_stop: bool = False,
        finishes_the_page_on_a_stop: bool = False,
    ):
        self.selection = selection
        self.worker = worker
        self.isolate = isolate
        self.newest_first = newest_first
        self.silent = silent
        self.retires_failures = retires_failures
        self.honours_stop = honours_stop
        self.finishes_the_page_on_a_stop = finishes_the_page_on_a_stop
        self.dispatched: list[int] = []

    def run(self) -> None:
        failures: list[Exception] = []
        page = list(self.selection().values_list("pk", flat=True)[:10])
        if self.finishes_the_page_on_a_stop:
            stop: SoftTimeLimitExceeded | None = None
            for owner_id in page:
                self.dispatched.append(owner_id)
                try:
                    self.worker(owner_id)
                except SoftTimeLimitExceeded as error:
                    stop = stop or error
            if stop is not None:
                raise stop
            return
        for owner_id in reversed(page) if self.newest_first else page:
            self.dispatched.append(owner_id)
            if not self.isolate:
                self.worker(owner_id)
                continue
            try:
                self.worker(owner_id)
            except Exception as error:
                if self.honours_stop and isinstance(error, SoftTimeLimitExceeded):
                    raise
                if self.retires_failures:
                    _hand_off(owner_id)
                failures.append(error)
        if failures and (not self.silent):
            raise ExceptionGroup("isolated recovery failures", failures)


def _handled(
    worker: Worker,
    edge: CandidateEdge,
    selection: Callable[[], QuerySet[PrimitiveOwner]] = owed_owners,
    *,
    dispatched_ids: Callable[[], list[int]] | None = None,
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE,
) -> None:
    assert_database_legal_owed_row_is_handled(
        name="self-test sweep",
        edge=edge,
        make_owed=_owed,
        selection=selection,
        identity_of=lambda owner: owner.pk,
        execute=worker,
        run_tick=_Tick(selection, worker, isolate=True).run,
        dispatched_ids=dispatched_ids,
        ends=ends,
    )


def _handled_inside_a_test_transaction(
    worker: Worker, edge: CandidateEdge, *, ends: FailureEnds = NOTHING_ENDS_A_FAILURE
) -> None:
    """As a contract that is not `transactional` runs: inside a transaction that never commits."""
    with transaction.atomic():
        _handled(worker, edge, ends=ends)
        transaction.set_rollback(True)


def _not_blocking(tick: _Tick, edge: CandidateEdge) -> None:
    assert_inadmissible_owed_row_does_not_block_the_next(
        name="self-test sweep",
        edge=edge,
        make_owed=_owed,
        selection=tick.selection,
        identity_of=lambda owner: owner.pk,
        run_tick=tick.run,
        dispatched_ids=lambda: tick.dispatched,
    )


@shared_task(name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.later_owner_task")
def later_owner_task(owner_id: int) -> None:
    """DEFECTIVE: "not ready, try later" on a row that never becomes ready: it re-publishes itself, every tick."""
    later_owner_task.apply_async((owner_id,), countdown=60)


@shared_task(name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.touch_owner_task")
def touch_owner_task(owner_id: int) -> None:
    """A fan-out item that writes the row without moving it."""
    PrimitiveOwner.objects.filter(pk=owner_id).update(value=F("value"))


def _fanning_out(owner_id: int) -> None:
    """Twenty handoffs that each write something, then the finalizer that raises on blank."""
    for _ in range(20):
        touch_owner_task.delay(owner_id)
    finalize_owner_task.delay(owner_id)


@shared_task(name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.staged_owner_task")
def staged_owner_task(owner_id: int, phase: str = "claim") -> None:
    """DEFECTIVE in its second phase: stamps a claim, re-publishes itself to finalize, and the finalize raises on blank."""
    if phase == "claim":
        PrimitiveOwner.objects.filter(pk=owner_id).update(claimed_at=timezone.now())
        staged_owner_task.apply_async((owner_id,), {"phase": "finalize"}, countdown=5)
        return
    _rejecting_blank(owner_id)


def _registering_a_no_op_commit_callback(owner_id: int) -> None:
    """DEFECTIVE: its only effect is a commit callback that does nothing, so the row is never served."""
    transaction.on_commit(lambda: None)


@shared_task(
    name="pytest_obligation.tests.profiles.automatic_recovery.test_owed_row_admissibility.notify_owner_after_commit_task"
)
def notify_owner_after_commit_task(owner_id: int, retire: bool = False) -> None:
    """A follow-up whose post-commit notification raises; with ``retire`` it retires the row first."""
    if retire:
        _retire(owner_id)

    def notify() -> None:
        raise RuntimeError("notification fake missing")

    transaction.on_commit(notify)


def _handing_off_to_a_raising_notification(owner_id: int) -> None:
    """DEFECTIVE through its handoff: the handed-off task's commit callback raises on a row it left selected."""
    notify_owner_after_commit_task.delay(owner_id)


def _handing_off_to_a_retiring_task_with_a_raising_notification(owner_id: int) -> None:
    """HANDLED: the handed-off task retires the row; only its later notification raises."""
    notify_owner_after_commit_task.delay(owner_id, retire=True)


def _excluding_blank() -> QuerySet[PrimitiveOwner]:
    return owed_owners().exclude(value="")


def _unclaimed() -> QuerySet[PrimitiveOwner]:
    """A selection that skips a claimed row, as a lease does until it expires."""
    return owed_owners().filter(claimed_at__isnull=True)


def _retiring_then_rejecting_blank(owner_id: int) -> None:
    """Retires the row, then fails a notification about a blank one: the raise comes after the end."""
    blank = PrimitiveOwner.objects.get(pk=owner_id).value == ""
    _retire(owner_id)
    if blank:
        raise ValueError("the notification about a retired blank row failed")


def _deleting_then_rejecting_blank(owner_id: int) -> None:
    """Deletes the row, then raises on blank: nothing can select it again."""
    blank = PrimitiveOwner.objects.get(pk=owner_id).value == ""
    PrimitiveOwner.objects.filter(pk=owner_id).delete()
    if blank:
        raise ValueError("cleanup after deleting a blank row failed")


def _retired_examples(*, age: timedelta) -> list[PrimitiveOwner]:
    return [PrimitiveOwner.objects.create(value=RETIRED, completed_at=timezone.now() - age)]


def _terminal_ends() -> FailureEnds:
    """What a profile-A contract over these owners projects: the state of its terminal examples, ``value``."""
    sweep = DueWorkSweep(
        name="self-test sweep",
        due_work=owed_owners,
        run_tick=lambda: 0,
        make_owed=lambda *, age: _owed(),
        make_terminal=_retired_examples,
        recovery_delay=timedelta(0),
        page_size=None,
        lifecycle=Lifecycle(state_fields=("value",), execute=_retiring_blank),
    )
    return failure_ends_of_sweep(sweep, retries_bounded=False)


#: A contract that claims profile J: its generated history ends a persistently failing row at the budget.
RETRIES_BOUNDED = FailureEnds(retries_bounded=True)


@pytest.mark.usefixtures("isolated_primitive")
class TestDatabaseLegalOwedRowIsHandled:
    def test_rejects_a_worker_that_raises_on_a_row_it_leaves_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .* raised ValueError"):
            _handled(_rejecting_blank, BLANK)

    def test_accepts_an_edge_value_the_same_worker_handles(self):
        _handled(_rejecting_blank, LONGEST)

    def test_rejects_a_handoff_that_raises_on_a_row_left_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised ValueError"):
            _handled(_handing_off, BLANK)

    def test_accepts_the_same_handoff_for_a_value_it_handles(self):
        _handled(_handing_off, LONGEST)

    def test_rejects_a_handoff_whose_task_only_retries_on_a_row_left_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised Retry"):
            _handled(_handing_off_to_a_retrying_task, BLANK)

    def test_accepts_the_retrying_handoff_for_a_value_it_handles(self):
        _handled(_handing_off_to_a_retrying_task, LONGEST)

    def test_rejects_a_handoff_whose_task_idles_on_a_row_left_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*handoffs did nothing at all"):
            _handled(_handing_off_to_an_idle_task, BLANK)

    def test_accepts_the_idle_handoff_for_a_value_its_task_handles(self):
        _handled(_handing_off_to_an_idle_task, LONGEST)

    def test_rejects_a_worker_that_silently_leaves_the_row_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .* did nothing at all"):
            _handled(_ignoring_blank, BLANK)

    def test_accepts_a_worker_that_retires_the_row(self):
        _handled(_retiring_blank, BLANK)

    def test_accepts_a_selection_that_excludes_the_row(self):
        _handled(_rejecting_blank, BLANK, selection=_excluding_blank)

    def test_rejects_a_handoff_published_after_commit_inside_a_test_transaction(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised ValueError"):
            _handled_inside_a_test_transaction(_handing_off_after_commit, BLANK)

    def test_accepts_the_same_after_commit_handoff_for_a_value_it_handles(self):
        _handled_inside_a_test_transaction(_handing_off_after_commit, LONGEST)

    def test_rejects_a_delayed_handoff_that_raises(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised ValueError"):
            _handled(_handing_off_with_a_countdown, BLANK)

    def test_accepts_the_delayed_handoff_for_a_value_it_handles(self):
        _handled(_handing_off_with_a_countdown, LONGEST)

    def test_rejects_a_raise_after_stamping_a_column_the_selection_ignores(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .* raised ValueError"):
            _handled(_stamping_then_rejecting_blank, BLANK)

    def test_rejects_a_skip_that_a_reached_recorder_logs(self):
        reached: list[int] = []

        def logging_skip(owner_id: int) -> None:
            reached.append(owner_id)
            _ignoring_blank(owner_id)

        with pytest.raises(OwedRowNotHandled, match="value-blank .* did nothing at all"):
            _handled(logging_skip, BLANK, dispatched_ids=lambda: reached)

    def test_rejects_a_worker_that_only_schedules_a_retry(self):
        with pytest.raises(OwedRowNotHandled, match="raised Retry"):
            _handled(later_owner_task, BLANK)

    def test_rejects_a_worker_whose_only_effect_is_a_no_op_commit_callback(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .* did nothing at all"):
            _handled(_registering_a_no_op_commit_callback, BLANK)

    def test_rejects_a_raise_in_the_phase_a_task_re_publishes_itself_into(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised ValueError"):
            _handled(staged_owner_task, BLANK)

    def test_accepts_the_staged_task_for_a_value_its_finalize_handles(self):
        _handled(staged_owner_task, LONGEST)

    def test_rejects_a_handed_off_task_whose_commit_callback_raises_on_a_row_left_selected(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .*raised RuntimeError"):
            _handled_inside_a_test_transaction(_handing_off_to_a_raising_notification, BLANK)

    def test_accepts_a_handed_off_task_that_retires_the_row_before_its_notification_raises(self):
        _handled_inside_a_test_transaction(
            _handing_off_to_a_retiring_task_with_a_raising_notification, BLANK, ends=_terminal_ends()
        )

    def test_rejects_a_handoff_chain_longer_than_it_judges(self):
        with pytest.raises(OwedRowNotHandled, match="still publishing after 20 deliveries"):
            _handled(_fanning_out, BLANK)


@pytest.mark.usefixtures("isolated_primitive")
class TestARaiseThatLeavesTheSelectionNeedsAnEnd:
    """A raise after the chain moved the row out of the selection repeats later, unless something ends it."""

    def test_rejects_a_raise_after_a_claim_hides_the_row(self):
        # The email engine's shape: the claim takes the row out of the selection, the raise follows,
        # and the expired lease hands the same row to the same raise.
        with pytest.raises(
            OwedRowNotHandled, match=r"value-blank .* after moving it out of the selection.*declares none"
        ):
            _handled(_stamping_then_rejecting_blank, BLANK, selection=_unclaimed)

    def test_accepts_the_claiming_worker_for_a_value_it_handles(self):
        _handled(_stamping_then_rejecting_blank, LONGEST, selection=_unclaimed)

    def test_rejects_the_raise_when_the_row_is_in_no_terminal_state_of_the_sweep(self):
        with pytest.raises(OwedRowNotHandled, match="in no terminal state of the sweep"):
            _handled(_stamping_then_rejecting_blank, BLANK, selection=_unclaimed, ends=_terminal_ends())

    def test_accepts_the_raise_when_profile_j_bounds_the_retry(self):
        _handled(_stamping_then_rejecting_blank, BLANK, selection=_unclaimed, ends=RETRIES_BOUNDED)

    def test_accepts_a_raise_after_the_row_ends_in_a_terminal_state(self):
        _handled(_retiring_then_rejecting_blank, BLANK, ends=_terminal_ends())

    def test_rejects_the_same_raise_where_the_contract_declares_no_terminal_state(self):
        # A light contract has no terminal declaration: the end must be a fix or a declared gap.
        with pytest.raises(OwedRowNotHandled, match="declares none"):
            _handled(_retiring_then_rejecting_blank, BLANK)

    def test_accepts_a_raise_after_the_row_is_deleted(self):
        _handled(_deleting_then_rejecting_blank, BLANK, ends=_terminal_ends())


@pytest.mark.usefixtures("isolated_primitive")
class TestInadmissibleOwedRowDoesNotBlockTheNext:
    def test_rejects_a_tick_that_stops_at_its_first_failure(self):
        with pytest.raises(OwedRowNotHandled, match="value-blank .* first in selection order stopped the tick"):
            _not_blocking(_Tick(owed_owners, _rejecting_blank, isolate=False), BLANK)

    def test_accepts_an_isolating_tick_that_fails_loudly_after_the_page(self):
        _not_blocking(_Tick(owed_owners, _rejecting_blank, isolate=True), BLANK)

    def test_accepts_the_aborting_tick_when_the_selection_excludes_the_row(self):
        _not_blocking(_Tick(_excluding_blank, _rejecting_blank, isolate=False), BLANK)


def _never_serving(_owner_id: int) -> None:
    """DEFECTIVE as a binding: reads nothing and writes nothing, so a valid row stays selected."""


def _always_rejecting(owner_id: int) -> None:
    """DEFECTIVE as a binding: fails even a valid row, so every edge case would measure the binding."""
    raise ValueError(f"cannot serve owner {owner_id}")


def _loop(worker: Worker) -> OwedRows:
    tick = _Tick(owed_owners, worker, isolate=True)
    return OwedRows(make_owed=_owed, execute=worker, run_tick=tick.run, dispatched_ids=lambda: tick.dispatched)


@pytest.mark.usefixtures("isolated_primitive")
class TestValidOwedRowLeavesTheSelection:
    """The light contract's positive control, which every "did nothing at all" verdict leans on."""

    def test_accepts_a_step_that_serves_the_row(self):
        assert_valid_owed_row_leaves_the_selection("self-test sweep", owed_owners, _loop(_retiring_blank))

    def test_accepts_a_step_that_serves_the_row_through_its_handoff(self):
        assert_valid_owed_row_leaves_the_selection("self-test sweep", owed_owners, _loop(_handing_off))

    def test_rejects_a_step_that_leaves_a_valid_row_selected(self):
        with pytest.raises(AssertionError, match="still selected after the production step"):
            assert_valid_owed_row_leaves_the_selection("self-test sweep", owed_owners, _loop(_never_serving))

    def test_rejects_a_step_that_fails_a_valid_row(self):
        with pytest.raises(AssertionError, match="a valid owed row failed .*ValueError"):
            assert_valid_owed_row_leaves_the_selection("self-test sweep", owed_owners, _loop(_always_rejecting))


@pytest.mark.usefixtures("isolated_primitive")
def test_an_edge_family_declared_on_another_model_is_rejected():
    proof = OWED_ROW_PROOFS["assert_database_legal_owed_row_is_handled"]
    with pytest.raises(AssertionError, match="are PrimitiveWork fields, but they would be written into PrimitiveOwner"):
        proof(
            "self-test sweep",
            owed_owners,
            EdgeFamily(model=PrimitiveWork),
            BLANK,
            _loop(_retiring_blank),
            NOTHING_ENDS_A_FAILURE,
        )


def test_the_binding_guard_rejects_a_step_written_in_the_test():
    with pytest.raises(AssertionError, match="owed_rows.execute"):
        assert_owed_row_bindings_are_production_bound("self-test sweep", _loop(_retiring_blank))


def _owed_to_the_next_owner(owner: PrimitiveOwner) -> bool:
    return PrimitiveOwner.objects.filter(pk=owner.pk, claimed_at__isnull=False).exists()


def _anything_owed_to_the_next_owner(owner: PrimitiveOwner) -> bool:
    return PrimitiveOwner.objects.filter(claimed_at__isnull=False).exists()


def _settled(owner: PrimitiveOwner) -> bool:
    """A query written in the test: what a ``still_owed`` binding must not be."""
    return PrimitiveOwner.objects.filter(pk=owner.pk, completed_at__isnull=False).exists()


def _anything_owed_to_the_reaper(owner: PrimitiveOwner) -> bool:
    """A still_owed that calls production but ignores the row it is handed."""
    return current_host() is not None


def test_the_binding_guard_rejects_a_still_owed_that_ignores_its_row():
    rows = _loop(_retiring_blank).model_copy(
        update={
            "execute": declared_recovery_delay,
            "run_tick": current_host,
            "still_owed": _anything_owed_to_the_reaper,
        }
    )
    with pytest.raises(AssertionError, match="owed_rows.still_owed never reads its 'owner' parameter"):
        assert_owed_row_bindings_are_production_bound("self-test sweep", rows)


class _AnythingOwed:
    """A callable instance whose ``__call__`` ignores the row: ``self`` is not the row."""

    def __call__(self, owner: PrimitiveOwner) -> bool:
        return current_host() is not None


def _ignoring_the_row_after_a_filled_argument(scale: int, owner: PrimitiveOwner) -> bool:
    return current_host() is not None


@pytest.mark.parametrize(
    "still_owed",
    [
        pytest.param(lambda *rows: current_host() is not None, id="varargs"),
        pytest.param(functools.partial(_ignoring_the_row_after_a_filled_argument, 1), id="partial"),
        pytest.param(_AnythingOwed(), id="callable-instance"),
    ],
)
def test_the_binding_guard_rejects_each_shape_of_a_still_owed_that_ignores_its_row(still_owed):
    rows = _loop(_retiring_blank).model_copy(
        update={"execute": declared_recovery_delay, "run_tick": current_host, "still_owed": still_owed}
    )
    with pytest.raises(AssertionError, match="owed_rows.still_owed never reads its"):
        assert_owed_row_bindings_are_production_bound("self-test sweep", rows)


def test_the_binding_guard_rejects_a_still_owed_written_in_the_test():
    rows = _loop(_retiring_blank).model_copy(
        update={"execute": declared_recovery_delay, "run_tick": current_host, "still_owed": _settled}
    )
    with pytest.raises(AssertionError, match="owed_rows.still_owed"):
        assert_owed_row_bindings_are_production_bound("self-test sweep", rows)


def _poisonable_loop(
    *,
    isolate: bool,
    fires: bool = True,
    newest_first: bool = False,
    silent: bool = False,
    retires: bool = False,
    honours_stop: bool = False,
    finishes_the_page_on_a_stop: bool = False,
) -> OwedRows:
    """A loop whose per-row step checks a switch first, as a production seam would."""
    refusals = PoisonSwitch()

    def step(owner_id: int) -> None:
        if fires:
            refusals.check(owner_id)
        _retiring_blank(owner_id)

    tick = _Tick(
        owed_owners,
        step,
        isolate=isolate,
        newest_first=newest_first,
        silent=silent,
        retires_failures=retires,
        honours_stop=honours_stop,
        finishes_the_page_on_a_stop=finishes_the_page_on_a_stop,
    )
    return OwedRows(
        make_owed=_owed,
        execute=step,
        run_tick=tick.run,
        dispatched_ids=lambda: tick.dispatched,
        poison=lambda owner: refusals.poisoned(owner.pk),
    )


def _rows_in_the_table() -> list[int]:
    """DEFECTIVE as a recorder: reads the table, so it reports rows no tick dispatched."""
    return list(PrimitiveOwner.objects.order_by("pk").values_list("pk", flat=True))


@pytest.mark.usefixtures("isolated_primitive")
class TestTheTickDispatchesOwedRowsInSelectionOrder:
    """The light contract's recorder control, which the liveness and poison cases lean on."""

    def test_accepts_a_recorder_of_an_in_order_tick(self):
        assert_the_tick_dispatches_owed_rows_in_selection_order(
            "self-test sweep", owed_owners, _poisonable_loop(isolate=False)
        )

    def test_rejects_a_recorder_that_reads_the_table(self):
        rows = _poisonable_loop(isolate=False).model_copy(update={"dispatched_ids": _rows_in_the_table})
        with pytest.raises(AssertionError, match="before any tick ran"):
            assert_the_tick_dispatches_owed_rows_in_selection_order("self-test sweep", owed_owners, rows)

    def test_rejects_a_tick_that_walks_another_order(self):
        with pytest.raises(AssertionError, match="the selection orders them"):
            assert_the_tick_dispatches_owed_rows_in_selection_order(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=False, newest_first=True)
            )


@pytest.mark.usefixtures("isolated_primitive")
class TestTheLoopIsolatesAPoisonedRow:
    """Invariant 12 on the light contract, through the same oracle as profile A's."""

    def test_rejects_a_loop_that_stops_at_the_poisoned_row(self):
        with pytest.raises(PoisonStalled, match="did not progress"):
            assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, _poisonable_loop(isolate=False))

    def test_rejects_a_loop_that_isolates_and_reports_nothing(self):
        with pytest.raises(PoisonUnreported, match="reported nothing"):
            assert_the_loop_isolates_a_poisoned_row(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, silent=True)
            )

    def test_rejects_a_loop_that_retires_the_poisoned_row(self):
        with pytest.raises(PoisonDropped, match="no longer owed"):
            assert_the_loop_isolates_a_poisoned_row(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, retires=True)
            )

    def test_rejects_a_still_owed_that_returns_a_truthy_object(self):
        rows = _poisonable_loop(isolate=True, retires=True).model_copy(update={"still_owed": lambda owner: owner})
        with pytest.raises(AssertionError, match="still_owed returned PrimitiveOwner, not a bool"):
            assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, rows)

    def test_a_dropped_row_is_found_even_when_the_loop_reports_nothing(self):
        with pytest.raises(PoisonDropped):
            assert_the_loop_isolates_a_poisoned_row(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, silent=True, retires=True)
            )

    def test_only_what_this_tick_recorded_counts_as_progress(self):
        rows = _poisonable_loop(isolate=False)
        healthy_earlier = rows.make_owed
        recorded: list[int] = []

        def make_owed() -> PrimitiveOwner:
            owner = healthy_earlier()
            recorded.append(owner.pk)
            return owner

        rows = rows.model_copy(update={"make_owed": make_owed, "dispatched_ids": lambda: [*recorded]})
        with pytest.raises(PoisonStalled):
            assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, rows)

    def test_reads_a_bound_still_owed_instead_of_the_selection(self):
        rows = _poisonable_loop(isolate=True, retires=True).model_copy(update={"still_owed": _owed_to_the_next_owner})
        assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, rows)

    @pytest.mark.parametrize("still_owed", [_anything_owed_to_the_next_owner, _settled])
    def test_rejects_a_still_owed_that_reports_a_served_row_as_owed(self, still_owed):
        rows = _poisonable_loop(isolate=True, retires=True).model_copy(update={"still_owed": still_owed})
        with pytest.raises(AssertionError, match="served to completion as still owed") as raised:
            assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, rows)
        assert not isinstance(raised.value, PoisonNotIsolated)

    def test_accepts_an_isolating_loop(self):
        assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, _poisonable_loop(isolate=True))

    def test_rejects_a_poison_that_never_fired(self):
        with pytest.raises(AssertionError, match="the poison never fired"):
            assert_the_loop_isolates_a_poisoned_row(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, fires=False)
            )

    def test_requires_a_poison_binding(self):
        rows = _poisonable_loop(isolate=True).model_copy(update={"poison": None})
        with pytest.raises(AssertionError, match="no `poison=` on the owed-row binding"):
            assert_the_loop_isolates_a_poisoned_row("self-test sweep", owed_owners, rows)


@pytest.mark.usefixtures("isolated_primitive")
class TestASoftTimeLimitEndsTheLoop:
    """Invariant 12b on the light contract: the poison seam raising Celery's soft limit must end the tick there."""

    def test_accepts_a_loop_that_honours_stop(self):
        assert_a_soft_time_limit_ends_the_loop(
            "self-test sweep", owed_owners, _poisonable_loop(isolate=True, honours_stop=True)
        )

    def test_the_same_loop_isolates_an_ordinary_failure(self):
        assert_the_loop_isolates_a_poisoned_row(
            "self-test sweep", owed_owners, _poisonable_loop(isolate=True, honours_stop=True)
        )

    def test_accepts_a_loop_that_lets_every_exception_escape(self):
        assert_a_soft_time_limit_ends_the_loop("self-test sweep", owed_owners, _poisonable_loop(isolate=False))

    def test_rejects_a_loop_that_isolates_the_limit_as_one_rows_failure(self):
        with pytest.raises(StopRequestIsolated, match="isolated a cooperative stop request"):
            assert_a_soft_time_limit_ends_the_loop("self-test sweep", owed_owners, _poisonable_loop(isolate=True))

    def test_rejects_a_loop_that_swallows_the_limit(self):
        with pytest.raises(StopRequestSwallowed, match="caught a cooperative stop request"):
            assert_a_soft_time_limit_ends_the_loop(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, silent=True)
            )

    def test_rejects_a_loop_that_retires_the_interrupted_row(self):
        with pytest.raises(StopRequestDropped, match="no longer owed"):
            assert_a_soft_time_limit_ends_the_loop(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, silent=True, retires=True)
            )

    def test_rejects_a_loop_that_finishes_the_page_before_stopping(self):
        with pytest.raises(StopRequestContinued, match="ran after a cooperative stop request"):
            assert_a_soft_time_limit_ends_the_loop(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=False, finishes_the_page_on_a_stop=True)
            )

    def test_rejects_a_seam_that_never_fired(self):
        with pytest.raises(AssertionError, match="the stop request never fired"):
            assert_a_soft_time_limit_ends_the_loop(
                "self-test sweep", owed_owners, _poisonable_loop(isolate=True, honours_stop=True, fires=False)
            )

    def test_rejects_a_seam_that_raises_poisoned_identity_itself(self):
        armed: set[int] = set()
        fired: Counter[int] = Counter()

        def step(owner_id: int) -> None:
            if owner_id in armed:
                fired[owner_id] += 1
                raise PoisonedIdentity("a seam that raises by itself")
            _retiring_blank(owner_id)

        @contextmanager
        def poison(owner: PrimitiveOwner) -> Iterator[Callable[[], int]]:
            armed.add(owner.pk)
            try:
                yield (lambda: fired[owner.pk])
            finally:
                armed.discard(owner.pk)

        tick = _Tick(owed_owners, step, isolate=True, honours_stop=True)
        rows = OwedRows(
            make_owed=_owed, execute=step, run_tick=tick.run, dispatched_ids=lambda: tick.dispatched, poison=poison
        )
        with pytest.raises(AssertionError, match="raised PoisonedIdentity inside stop_requests"):
            assert_a_soft_time_limit_ends_the_loop("self-test sweep", owed_owners, rows)

    def test_requires_a_poison_binding(self):
        rows = _poisonable_loop(isolate=True, honours_stop=True).model_copy(update={"poison": None})
        with pytest.raises(AssertionError, match="no `poison=` on the owed-row binding"):
            assert_a_soft_time_limit_ends_the_loop("self-test sweep", owed_owners, rows)


def test_an_armed_switch_raises_the_soft_limit_only_inside_stop_requests():
    switch = PoisonSwitch()
    with switch.poisoned("armed") as fired:
        switch.check("unarmed")
        with pytest.raises(PoisonedIdentity):
            switch.check("armed")
        with stop_requests(), pytest.raises(SoftTimeLimitExceeded) as raised:
            switch.check("armed", "the seam's own message")
        assert isinstance(raised.value, SoftTimeLimitExceeded), "production code catches Celery's own type"
        assert raised.value.args == ("the seam's own message",)
        with pytest.raises(PoisonedIdentity):
            switch.check("armed")
        assert fired() == 3
