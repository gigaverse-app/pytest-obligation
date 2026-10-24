"""Reference SQL treats metadata names as identifiers, including quoted names."""

import pytest
from django.db import connection

from pytest_obligation.integrations.django import lifecycle_references as ref
from pytest_obligation.integrations.django.selection import DjangoSelectionInspector


@pytest.mark.django_db(transaction=True)
def test_reference_lifecycle_and_statistics_quote_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    function = 'reference "quoted" function'
    table = ref.LifecycleAttempt._meta.db_table
    monkeypatch.setattr(ref, "FAIL_ATTEMPT_FUNCTION", function)

    with ref.lifecycle_attempt_table():
        attempt = ref.LifecycleAttempt.objects.create(status=ref.Status.RUNNING)
        ref.fail_attempt_through_a_function_then_hand_off(attempt.pk)
        attempt.refresh_from_db()
        assert attempt.status == ref.Status.RETRYABLE_FAILED
        assert ref.LifecycleAttempt.objects.filter(retry_of=attempt).exists()
        costs = DjangoSelectionInspector().read_costs(ref.LifecycleAttempt.objects.all())
        assert costs.selection.visited > 0

    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_proc WHERE proname = %s)", [function])
        assert cursor.fetchone()[0] is False
    assert table not in connection.introspection.table_names()
