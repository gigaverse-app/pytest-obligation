"""Independent PostgreSQL transaction scopes for database visibility proofs.

These helpers create no models and import no application registry. The caller
owns its normal connection; each scope closes only its independent connection.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, connections


@contextmanager
def transaction_in_progress() -> Iterator[None]:
    """
    Hold an xid older than everything the body writes.

    Snapshot xmin is server-wide, so this keeps the body's dead row versions
    recently dead: an index built over them gets ``pg_index.indcheckxmin`` and
    the planner ignores it. Locally nothing else holds one, so plan-sensitive
    tests that only fail in CI reproduce with this.
    """
    other = connections.create_connection(connection.alias)
    try:
        other.set_autocommit(False)
        with other.cursor() as cursor:
            cursor.execute("SELECT txid_current()")
        yield
    finally:
        other.close()
