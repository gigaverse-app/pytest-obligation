"""Real PostgreSQL failures at a per-identity poison seam.

A Python exception alone leaves an open transaction usable and cannot prove
savepoint isolation. Rejecting a statement first leaves that transaction aborted
until its owner rolls it back. In autocommit, only the failed statement rolls back.
"""

from collections.abc import Hashable

import pytest
from django.db import DataError, connection

from pytest_obligation.integrations.django.writes import require_postgresql
from pytest_obligation.poison import PoisonSwitch


def fail_like_a_database_error(refusals: PoisonSwitch, key: Hashable, message: str) -> None:
    """If armed, fail SQL before re-raising the switch's original poison or stop request.

    Do not open a savepoint here: the caller's production transaction must own
    recovery, otherwise this helper would conceal a missing isolation boundary.
    Unarmed identities neither query nor disturb the connection.
    """
    try:
        refusals.check(key, message)
    except Exception:
        require_postgresql(connection.alias, "database-error injection", "it probes transaction abortion")
        with connection.cursor() as cursor, pytest.raises(DataError):
            cursor.execute("SELECT 1 / 0")
        raise
