"""Connection bounds do not leak between worker scopes or into the test thread."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection

from pytest_obligation.integrations.django.worker_connections import database_worker_connection


def test_repeated_worker_scopes_restore_their_original_options() -> None:
    def exercise() -> None:
        previous = connection.settings_dict.get("OPTIONS", {}).get("options")
        inside: list[str] = []
        for _ in range(2):
            with database_worker_connection(statement_timeout_ms=100, lock_timeout_ms=50):
                inside.append(connection.settings_dict["OPTIONS"]["options"])
        assert inside[0] == inside[1], "the second scope must not stack the first scope's bounds"
        assert inside[0].endswith("-c lock_timeout=50ms -c statement_timeout=100ms")
        assert connection.settings_dict.get("OPTIONS", {}).get("options") == previous

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(exercise).result(timeout=30)


def test_the_test_thread_is_refused_without_changing_its_settings() -> None:
    previous = dict(connection.settings_dict)
    with pytest.raises(AssertionError, match="worker thread"), database_worker_connection():
        pass
    assert connection.settings_dict == previous
