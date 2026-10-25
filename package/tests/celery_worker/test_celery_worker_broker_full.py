"""
The broker-full fault needs a Redis broker it can restore, and restores it however its run ends.

The restoring test changes the shared test Redis's ``maxmemory`` to a harmless
value, never to one that refuses writes: other suites use that server at the
same time.
"""

import pytest
import redis

from pytest_obligation.integrations.celery_worker import BROKER_FULL, broker_restored, worker_history
from tests.redis_databases import redis_url


@pytest.mark.parametrize("broker_url", [None, "amqp://guest@localhost//"], ids=["none", "amqp"])
def test_a_full_broker_needs_a_redis_broker_url(broker_url: str | None) -> None:
    with pytest.raises(AssertionError, match="needs broker_url= naming a Redis broker"):
        worker_history(
            name="refused",
            app="any:app",
            task="any.task",
            send=lambda: "task id",
            observe=lambda _task_id: "done",
            initial="pending",
            expected="done",
            settled=lambda _task_id: True,
            failure_points=(BROKER_FULL,),
            broker_url=broker_url,
        )


def test_the_broker_is_restored_however_the_run_ends() -> None:
    url = redis_url("rq")
    server = redis.Redis.from_url(url, decode_responses=True)
    before = server.config_get("maxmemory")["maxmemory"]
    with pytest.raises(RuntimeError, match="the run failed"), broker_restored(url):
        server.config_set("maxmemory", 512 * 1024 * 1024)
        raise RuntimeError("the run failed")
    assert server.config_get("maxmemory")["maxmemory"] == before
