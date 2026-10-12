"""
A root-owned batch lifecycle for the selection-completeness self-tests.

The email reaper's shape, reduced: a ``Batch`` is built READY, started RUNNING
by its first dispatcher, and finished; its ``BatchItem`` rows are READY until
the dispatcher works them. Recovery selects the READY items of live batches
and hands each batch to a step that only publishes the dispatcher, so the
property must follow the handoff to judge it. Selections, steps and the
dispatcher come in conforming and broken shapes:

* :func:`items_awaiting_dispatch` returns READY items of READY or RUNNING
  batches; :func:`items_of_running_batches` drops the READY-batch branch (the
  mutation the property exists to catch).
* :func:`run_batch` starts a batch only when it has work and leaves finished
  ones alone; :func:`run_batch_completing` also completes a batch whose items
  are all done, which a RUNNING batch with only done items owes and no
  selection returns; :func:`run_batch_ignoring_budget` works items past the
  attempt budget the selection stops at.

Never import this module in an adopter: binding it measures the reference.
"""

from collections.abc import Iterator

import django
import pytest
from celery import shared_task
from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.test.utils import isolate_apps

from pytest_obligation.integrations.django.tables import model_tables

with isolate_apps("pytest_obligation"):

    class Batch(models.Model):
        class Status(models.TextChoices):
            READY = "ready"
            RUNNING = "running"
            PARKED = "parked"
            DONE = "done"

        status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)

        class Meta:
            app_label = "pytest_obligation"

    class BatchItem(models.Model):
        class State(models.TextChoices):
            READY = "ready"
            CLAIMED = "claimed"
            DONE = "done"

        batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="items")
        state = models.CharField(max_length=16, choices=State.choices, default=State.READY)
        attempts = models.IntegerField(default=0)
        claimed_by = models.CharField(max_length=16, null=True, default=None)

        class Meta:
            app_label = "pytest_obligation"
            constraints = [
                # A claimed item names its owner; the database refuses one that does not.
                models.CheckConstraint(
                    name="batch_item_claimed_has_owner", condition=~Q(state="claimed") | Q(claimed_by__isnull=False)
                )
                if django.VERSION >= (5, 1)
                else models.CheckConstraint(  # pyrefly: ignore[missing-argument] — Django 4.2 uses check, not condition.
                    name="batch_item_claimed_has_owner",
                    check=~Q(state="claimed") | Q(claimed_by__isnull=False),  # pyrefly: ignore[unexpected-keyword]
                )
            ]


@pytest.fixture(name="batch_tables")
def batch_tables_fixture(transactional_db: None) -> Iterator[None]:
    """The reference tables, committed for the test and dropped after it."""
    with model_tables(Batch, BatchItem):
        yield


#: Attempts after which an item is left for an operator: the selection's budget branch.
MAX_ATTEMPTS = 3


def _workable() -> Q:
    """READY and within its attempt budget; the selection and the dispatcher share it."""
    return Q(state=BatchItem.State.READY, attempts__lt=MAX_ATTEMPTS)


def make_ready_item() -> BatchItem:
    """ARRANGE: a built batch's unclaimed item, already RUNNING (the respawn case the examples always write)."""
    batch = Batch.objects.create(status=Batch.Status.RUNNING)
    return BatchItem.objects.create(batch=batch)


def items_awaiting_dispatch() -> QuerySet[BatchItem]:
    """CONFORMING: READY items of every live batch, built or started."""
    return (
        BatchItem.objects.filter(_workable())
        .filter(batch__status__in=(Batch.Status.READY, Batch.Status.RUNNING))
        .order_by("batch_id", "pk")
    )


def items_of_running_batches() -> QuerySet[BatchItem]:
    """BROKEN: a built batch whose first dispatcher was lost is never started."""
    return BatchItem.objects.filter(_workable()).filter(batch__status=Batch.Status.RUNNING).order_by("batch_id", "pk")


def items_of_live_batches_with_parked() -> QuerySet[BatchItem]:
    """BROKEN the other way: selects PARKED batches, whose dispatcher leaves them alone every tick."""
    return (
        BatchItem.objects.filter(_workable())
        .filter(batch__status__in=(Batch.Status.READY, Batch.Status.RUNNING, Batch.Status.PARKED))
        .order_by("batch_id", "pk")
    )


def batch_of(item: BatchItem) -> int:
    return item.batch_id


def run_batch(batch_id: int) -> None:
    """The dispatcher: start a built batch that has work, then finish its READY items."""
    with transaction.atomic():
        if BatchItem.objects.filter(_workable(), batch_id=batch_id).exists():
            Batch.objects.filter(pk=batch_id, status=Batch.Status.READY).update(status=Batch.Status.RUNNING)
        BatchItem.objects.filter(_workable(), batch_id=batch_id, batch__status=Batch.Status.RUNNING).update(
            state=BatchItem.State.DONE, attempts=models.F("attempts") + 1
        )


def run_batch_completing(batch_id: int) -> None:
    """The dispatcher, plus the completion step: a RUNNING batch with nothing left to do is DONE."""
    run_batch(batch_id)
    # Only DONE items finish a batch: an item in any other state, known or not, still owes its work.
    unfinished = BatchItem.objects.filter(batch_id=OuterRef("pk")).exclude(state=BatchItem.State.DONE)
    Batch.objects.filter(~Exists(unfinished), pk=batch_id, status=Batch.Status.RUNNING).update(status=Batch.Status.DONE)


def run_batch_ignoring_budget(batch_id: int) -> None:
    """BROKEN: works an item however many attempts it has spent, while the selection stops at the budget."""
    ready = BatchItem.objects.filter(batch_id=batch_id, state=BatchItem.State.READY)
    if ready.exists():
        Batch.objects.filter(pk=batch_id, status=Batch.Status.READY).update(status=Batch.Status.RUNNING)
    ready.filter(batch__status=Batch.Status.RUNNING).update(
        state=BatchItem.State.DONE, attempts=models.F("attempts") + 1
    )


@shared_task(name="pytest_obligation.integrations.django.batch_references.dispatch_batch_task")
def dispatch_batch_task(batch_id: int) -> None:
    run_batch(batch_id)


@shared_task(name="pytest_obligation.integrations.django.batch_references.dispatch_completing_batch_task")
def dispatch_completing_batch_task(batch_id: int) -> None:
    run_batch_completing(batch_id)


def schedule_batch(batch_id: int) -> None:
    """The recovery step: it only publishes the dispatcher, after commit, for any batch it is given."""
    transaction.on_commit(lambda: dispatch_batch_task.delay(batch_id))


def schedule_completing_batch(batch_id: int) -> None:
    """The recovery step publishing the completing dispatcher."""
    transaction.on_commit(lambda: dispatch_completing_batch_task.delay(batch_id))
