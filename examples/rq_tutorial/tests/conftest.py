from collections.abc import Iterator

import pytest
import welcome_rq
from email_provider import MAILER

from pytest_obligation import configure
from pytest_obligation.integrations.redis import redis_host

# The host: Redis writes are the commits a worker can die after, and their replies can be lost.
configure(redis_host(welcome_rq.connection, {"welcome_rq"}))
# The welcome app talks to the test's email stand-in instead of a real provider.
welcome_rq.mailer = MAILER


@pytest.fixture
def empty_redis() -> Iterator[None]:
    """Every generated case starts from an empty Redis database and an empty mailbox."""
    welcome_rq.connection.flushdb()
    MAILER.__init__()
    yield
    welcome_rq.connection.flushdb()
