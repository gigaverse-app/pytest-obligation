"""Production-shaped query used by the dependency-index probe's SQL controls."""

from django.db.models import QuerySet

from pytest_obligation.integrations.django.lifecycle_references import LifecycleAttempt


def identity_selection() -> QuerySet[LifecycleAttempt]:
    return LifecycleAttempt.objects.filter(pk__gte=0)
