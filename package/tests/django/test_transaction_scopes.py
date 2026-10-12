"""A real independent old xid stays live through the body and closes on every exit."""

from contextlib import nullcontext

import pytest
from django.db import connection, connections
from django.db.backends.base.base import BaseDatabaseWrapper

from pytest_obligation.integrations.django.transactions import transaction_in_progress

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("failed", [False, True])
def test_old_transaction_is_independent_and_always_closed(monkeypatch: pytest.MonkeyPatch, failed: bool) -> None:
    opened: list[BaseDatabaseWrapper] = []
    create = connections.create_connection

    def observe_connection(alias: str) -> BaseDatabaseWrapper:
        actual = create(alias)
        opened.append(actual)
        return actual

    monkeypatch.setattr(connections, "create_connection", observe_connection)
    with pytest.raises(RuntimeError, match="body interrupted") if failed else nullcontext():
        with transaction_in_progress():
            assert connection.get_autocommit()
            assert len(opened) == 1 and not opened[0].get_autocommit()
            with opened[0].cursor() as other:
                other.execute("SELECT pg_backend_pid()")
                pid = other.fetchone()[0]
            with connection.cursor() as observer:
                observer.execute("SELECT backend_xid IS NOT NULL FROM pg_stat_activity WHERE pid = %s", [pid])
                assert observer.fetchone() == (True,)
            if failed:
                raise RuntimeError("body interrupted")
    assert opened[0].connection is None
    with connection.cursor() as observer:
        observer.execute("SELECT 1")
        assert observer.fetchone() == (1,)
