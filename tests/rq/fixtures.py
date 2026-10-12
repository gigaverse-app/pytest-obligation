from collections.abc import Iterator

import pytest

from pytest_obligation import configure
from pytest_obligation.integrations.redis import redis_host
from pytest_obligation.integrations.rq import rq_callback_breaker
from tests.rq.connection import CONNECTION

configure(redis_host(CONNECTION, {"rq"}, receiver_breaker=rq_callback_breaker))


@pytest.fixture
def empty_redis() -> Iterator[None]:
    CONNECTION.flushdb()
    yield
    CONNECTION.flushdb()
