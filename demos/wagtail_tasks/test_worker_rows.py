"""The real database worker must handle the persisted rows its polling query returns."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock
from uuid import UUID, uuid4

from django_tasks_db.compat import BaseTaskResult, TaskResultStatus, task_finished, task_started
from django_tasks_db.management.commands.db_worker import Worker
from django_tasks_db.models import DBTaskResult, DBTaskResultQuerySet
from wagtail.contrib.frontend_cache.tasks import purge_urls_from_cache_task

from pytest_obligation import Adoption, ScheduledSelection, scheduled_selection_suite
from pytest_obligation.integrations.django.owed_rows import EdgeFamily, OwedRows
from pytest_obligation.poison import PoisonSwitch


def worker() -> Worker:
    """The command's normal batch worker, polling every queue on the configured backend."""
    return Worker(
        queue_names=["*"],
        interval=0,
        batch=True,
        backend_name="default",
        startup_delay=False,
        max_tasks=None,
        worker_id="owed-row-contract",
        excluded_queue_names=[],
    )


def ready_selection() -> DBTaskResultQuerySet:
    """Observe the query at its claim boundary; returning no claim leaves every row untouched."""
    # ARRANGE: the persisted task rows belong to each generated history.
    # REAL PRODUCTION: Worker.run builds the backend/queue/due-time selection.
    # EXTERNAL SEAM: intercept get_locked at the claim boundary, before any mutation.
    # OBSERVE: the exact queryset offered to the database claim operation.
    observed: list[DBTaskResultQuerySet] = []

    def capture(queryset: DBTaskResultQuerySet) -> None:
        observed.append(queryset.all())

    # The selection-only proofs use Django's enclosing transaction; a real
    # worker's connection cleanup would close that artificially non-autocommit connection.
    # This stand-in is scoped only to query observation, never to execution or fault histories.
    with (
        mock.patch.object(DBTaskResultQuerySet, "get_locked", capture),
        mock.patch("django_tasks_db.management.commands.db_worker.close_old_connections"),
    ):
        worker().run()
    assert len(observed) == 1, "the batch worker must attempt one selection before reporting idle"
    return observed[0]


def owed_purge() -> DBTaskResult:
    """Enqueue through Wagtail, so the payload and task registration are production-owned."""
    task = purge_urls_from_cache_task.enqueue([f"https://example.test/owed/{uuid4()}/"])
    return DBTaskResult.objects.get(pk=task.id)


@contextmanager
def worker_rows() -> Iterator[OwedRows]:
    # ARRANGE: independent Wagtail purge jobs through the real task backend.
    # REAL PRODUCTION: Worker.run selects/claims; Worker.run_task performs each row's work.
    # EXTERNAL SEAM: task_started receiver raises only for the armed identity.
    # OBSERVE: successful task_finished signals, not tasks merely entered or selected.
    completed: list[UUID] = []
    switch = PoisonSwitch()

    def finished(sender: object, task_result: BaseTaskResult[..., object], **kwargs: Any) -> None:
        if task_result.status == TaskResultStatus.SUCCESSFUL:
            completed.append(UUID(task_result.id))

    def may_fail(sender: object, task_result: BaseTaskResult[..., object], **kwargs: Any) -> None:
        switch.check(UUID(task_result.id))

    task_finished.connect(finished, weak=False)
    task_started.connect(may_fail, weak=False)
    try:
        yield OwedRows(
            make_owed=owed_purge,
            execute=worker().run_task,
            deliver=lambda row: row,
            run_tick=lambda: worker().run(),
            dispatched_ids=lambda: list(completed),
            poison=lambda row: switch.poisoned(row.pk),
        )
    finally:
        task_started.disconnect(may_fail)
        task_finished.disconnect(finished)


READY_TASKS = ScheduledSelection(
    name="wagtail: database worker ready rows",
    adoption=Adoption.LEGACY,
    due_work=ready_selection,
    unscheduled_because="db_worker is a continuously polling process; this batch invocation uses its same query and loop.",
    owed_rows=worker_rows,
    state_fields=("status",),
    fixed_fields={
        "backend_name": "This worker is configured for the default backend; routing to other backends has a different owner."
    },
    excluded_states={
        "status:SUCCESSFUL": "The provider call completed; another execution would only replay the completed task.",
        "status:FAILED": "django-tasks-db records terminal task failure; explicit resubmission owns another attempt.",
    },
    owed_edges={"task": EdgeFamily(model=DBTaskResult)},
    gaps={
        "assert_selection_is_complete[status:RUNNING]": (
            "A task whose worker died remains RUNNING forever. The real task body can complete it, "
            "but ready() never selects it at any recovery horizon and the backend schedules no reclaim."
        ),
        "assert_selection_is_complete[status:@blank]": (
            "The database permits this exact status edge, but ready() skips it forever. "
            "A delivered worker attempts to reconstruct the task and records FAILED instead."
        ),
        "assert_selection_is_complete[status:@whitespace]": (
            "The database permits this exact status edge, but ready() skips it forever. "
            "A delivered worker attempts to reconstruct the task and records FAILED instead."
        ),
        "assert_selection_is_complete[status:@max_length]": (
            "The database permits this exact status edge, but ready() skips it forever. "
            "A delivered worker attempts to reconstruct the task and records FAILED instead."
        ),
        "assert_selection_is_complete[status:@unknown_choice]": (
            "The database permits this exact status edge, but ready() skips it forever. "
            "A delivered worker attempts to reconstruct the task and records FAILED instead."
        ),
        "assert_database_legal_owed_row_is_handled[task-queue_name-blank]": (
            "The all-queues worker claims a row with an empty queue name before InvalidTask escapes. "
            "The row leaves ready() without this light contract proving a terminal state or retry budget."
        ),
        "assert_database_legal_owed_row_is_handled[task-queue_name-whitespace]": (
            "A whitespace-only queue name is database-legal and selected by the all-queues worker. "
            "InvalidTask escapes after the claim; leaving ready() proves neither completion nor bounded failure."
        ),
        "assert_database_legal_owed_row_is_handled[task-queue_name-max_length]": (
            "An unconfigured queue name raises InvalidTask after the worker claims the row. "
            "Leaving ready() does not prove the obligation was handled or that a bounded retry ends it."
        ),
        "assert_inadmissible_owed_row_does_not_block_the_next[task-queue_name-blank]": (
            "The all-queues worker selects an empty queue name. Its error handler reconstructs the invalid "
            "task and raises InvalidTask, abandoning the healthy task behind it."
        ),
        "assert_inadmissible_owed_row_does_not_block_the_next[task-queue_name-whitespace]": (
            "The all-queues worker claims a whitespace queue name, then InvalidTask from error reporting "
            "aborts the tick before the healthy task behind it."
        ),
        "assert_inadmissible_owed_row_does_not_block_the_next[task-queue_name-max_length]": (
            "A database-legal but unconfigured 32-character queue name is selected by the all-queues worker. "
            "Error reporting raises InvalidTask and aborts before the healthy tail."
        ),
        "assert_one_poisoned_identity_does_not_stall_the_tick[dropped]": (
            "Worker.run_task catches the receiver failure and makes the task FAILED. The healthy tail completes, "
            "but ready() never selects the failed task again and no automatic retry restores it."
        ),
        "assert_a_soft_time_limit_ends_the_tick[dropped]": (
            "The worker catches the injected cooperative stop as BaseException, makes the interrupted task "
            "FAILED, and continues to the healthy tail. This checks exception handling, not its OS signal handler."
        ),
    },
)


@scheduled_selection_suite(READY_TASKS)
class TestDatabaseWorkerRows:
    pass
