"""Small PostgreSQL lifecycle used only by the port's positive and negative controls."""

from collections.abc import Iterator
from typing import ClassVar

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection, models
from django.db.models import QuerySet
from django.test.utils import isolate_apps

from pytest_obligation.host import hosted
from pytest_obligation.integrations.celery import celery_handoffs, celery_publications
from pytest_obligation.integrations.django import django_host

with isolate_apps("pytest_obligation"):

    class PrimitiveOwner(models.Model):
        value = models.CharField(max_length=40)
        completed_at = models.DateTimeField(null=True)
        claimed_at = models.DateTimeField(null=True)
        count = models.SmallIntegerField(default=0)
        objects: ClassVar[models.Manager["PrimitiveOwner"]]

        class Meta:
            app_label = "pytest_obligation"

    class PrimitiveWork(models.Model):
        owner = models.ForeignKey(PrimitiveOwner, on_delete=models.CASCADE)
        objects: ClassVar[models.Manager["PrimitiveWork"]]

        class Meta:
            app_label = "pytest_obligation"


def owed_owners() -> QuerySet[PrimitiveOwner]:
    return PrimitiveOwner.objects.filter(completed_at__isnull=True).order_by("pk")


@pytest.fixture
def isolated_primitive(transactional_db: None) -> Iterator[None]:
    with connection.schema_editor() as editor:
        editor.create_model(PrimitiveOwner)
        editor.create_model(PrimitiveWork)
    try:
        with hosted(
            django_host(
                {"tests.django.automatic_recovery.owed_reference"},
                publication_recorder=celery_publications,
                handoff_runner=celery_handoffs,
                stop_exception=SoftTimeLimitExceeded,
            )
        ):
            yield
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(PrimitiveWork)
            editor.delete_model(PrimitiveOwner)


def settle(owner_id: int) -> None:
    from django.utils import timezone

    PrimitiveOwner.objects.filter(pk=owner_id).update(completed_at=timezone.now())


class ReferenceLoop:
    """Production-shaped conformer: stop on cancellation; isolate and report ordinary failure."""

    def __init__(self) -> None:
        from pytest_obligation.poison import PoisonSwitch

        self.poison = PoisonSwitch()
        self.dispatched: list[int] = []

    def execute(self, identity: int) -> None:
        self.poison.check(identity)
        settle(identity)

    def tick(self) -> None:
        failures: list[Exception] = []
        for row in owed_owners():
            try:
                self.execute(row.pk)
            except SoftTimeLimitExceeded:
                raise
            except Exception as error:
                failures.append(error)
            else:
                self.dispatched.append(row.pk)
        if failures:
            raise ExceptionGroup("failed rows", failures)


def poll(owner_id: int) -> None:
    """One poll of an owner: stamps it and leaves it selected, as a sweep over long-lived active rows does."""
    from django.utils import timezone

    PrimitiveOwner.objects.filter(pk=owner_id).update(claimed_at=timezone.now())


class PollingReferenceLoop(ReferenceLoop):
    """Production-shaped polling conformer: every tick polls every owner again, isolating ordinary failures."""

    def execute(self, identity: int) -> None:
        self.poison.check(identity)
        poll(identity)
