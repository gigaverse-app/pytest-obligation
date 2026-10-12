"""Poison reaches PostgreSQL; only the production owner's rollback repairs it."""

from contextlib import nullcontext

import pytest
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext

from pytest_obligation.host import current_host
from pytest_obligation.integrations.django.database_faults import fail_like_a_database_error
from pytest_obligation.poison import PoisonedIdentity, PoisonSwitch, StopRequested, stop_requests

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("stop", [False, True])
@pytest.mark.parametrize("atomic", [False, True])
def test_armed_fault_preserves_exception_and_requires_the_callers_rollback(stop: bool, atomic: bool) -> None:
    switch = PoisonSwitch()
    error = (current_host().stop_exception or StopRequested) if stop else PoisonedIdentity
    with transaction.atomic() if atomic else nullcontext():
        with switch.poisoned("bad") as fired, stop_requests() if stop else nullcontext():
            with pytest.raises(error, match="original failure"):
                fail_like_a_database_error(switch, "bad", "original failure")
            assert fired() == 1
            with pytest.raises(DatabaseError) if atomic else nullcontext():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    assert cursor.fetchone() == (1,)
    # The caller's transaction boundary must restore service for the next identity.
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


def test_unarmed_identity_does_not_query_or_poison_the_connection() -> None:
    switch = PoisonSwitch()
    with switch.poisoned("bad") as fired, transaction.atomic(), CaptureQueriesContext(connection) as queries:
        fail_like_a_database_error(switch, "healthy", "must not fail")
        assert fired() == 0
        assert not queries
