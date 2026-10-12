"""Small PostgreSQL lifecycle used only by the port's positive and negative controls."""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection, models
from django.db.models import QuerySet
from django.test.utils import isolate_apps

from pytest_obligation.host import hosted
from pytest_obligation.integrations.celery import celery_handoffs, celery_publications
from pytest_obligation.integrations.django import django_host
from pytest_obligation.models import HarnessModel

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
        self.dispatched: list[Any] = []

    def owed(self) -> list[Any]:
        """The identities one tick owes work to, in the order it serves them."""
        return [row.pk for row in owed_owners()]

    def execute(self, identity: int) -> None:
        self.poison.check(identity)
        settle(identity)

    def tick(self) -> None:
        failures: list[Exception] = []
        for identity in self.owed():
            try:
                self.execute(identity)
            except SoftTimeLimitExceeded:
                raise
            except Exception as error:
                failures.append(error)
            else:
                self.dispatched.append(identity)
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


class ProviderResource(HarnessModel):
    """One resource an external provider lists; nothing in the database names it."""

    name: str


class ResourceProvider:
    """An in-memory provider fake: the resources it lists, by name, in creation order."""

    def __init__(self) -> None:
        self.resources: dict[str, ProviderResource] = {}

    def create(self) -> ProviderResource:
        resource = ProviderResource(name=f"resource-{len(self.resources) + 1:04d}")
        self.resources[resource.name] = resource
        return resource

    def list(self) -> list[ProviderResource]:
        return list(self.resources.values())

    def delete(self, name: str) -> None:
        del self.resources[name]


def orphaned_resources(provider: ResourceProvider) -> list[ProviderResource]:
    """The provider's resources no owner row knows by name: the orphans a reconciler deletes."""
    known = set(PrimitiveOwner.objects.values_list("value", flat=True))
    return [resource for resource in provider.list() if resource.name not in known]


class OrphanReconciler(ReferenceLoop):
    """Production-shaped external-identity conformer: deletes each orphan, isolating ordinary failures."""

    def __init__(self, provider: ResourceProvider) -> None:
        super().__init__()
        self.provider = provider

    def orphans(self) -> list[ProviderResource]:
        """The listing seam: what this reconciler's provider reports as orphaned now."""
        return orphaned_resources(self.provider)

    def owed(self) -> list[Any]:
        return [resource.name for resource in self.orphans()]

    def execute(self, identity: Any) -> None:
        self.poison.check(identity)
        self.provider.delete(identity)
