import pytest
from django.db import connection

from pytest_obligation.integrations.django import lifecycle_references as ref
from pytest_obligation.integrations.django.selection import IndexedSelectionDependencies
from tests_support.sample_production.selection import identity_selection

pytestmark = pytest.mark.django_db(transaction=True)


def test_dependency_probe_requires_the_named_scan_and_detects_a_lost_index() -> None:
    table = ref.LifecycleAttempt._meta.db_table
    probe = IndexedSelectionDependencies(selection=identity_selection, tables=(table,))
    with ref.lifecycle_attempt_table():
        probe()
        with pytest.raises(AssertionError):
            probe.model_copy(update={"tables": ("missing_dependency",)})()
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{table}_pkey" CASCADE')
        with pytest.raises(AssertionError, match="index|scan"):
            probe()
