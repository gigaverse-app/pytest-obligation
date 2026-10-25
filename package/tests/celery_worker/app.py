"""The reference Celery application the worker self-tests run: a task that sends a message, its link, its errback."""

import os
from typing import Any

import redis
from celery import Celery

from tests.redis_databases import redis_url

#: A Redis server of its own for the broker-full history: that fault refuses writes on the whole server.
OWN_BROKER = os.environ.get("CELERY_OWN_BROKER_URL", "redis://localhost:6380/0")
BROKER = redis_url("celery broker")
BACKEND = redis_url("celery backend")
#: What the tasks did, readable from the test process and every worker process.
RECORDS = redis.Redis.from_url(redis_url("celery records"), decode_responses=True)

app = Celery("due_work_reference", broker=BROKER, backend=BACKEND)


def empty() -> None:
    """ARRANGE: an empty broker, result backend and record."""
    for url in (BROKER, BACKEND):
        redis.Redis.from_url(url).flushdb()
    RECORDS.flushdb()


app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1)


@app.task
def send_message(message: str) -> str:
    # EXTERNAL SEAM: the message leaves for the customer.
    RECORDS.rpush("sent", message)
    return message


@app.task
def announce(result: str) -> None:
    RECORDS.rpush("announced", f"sent {result!r}")


@app.task
def report_failure(request: Any, exc: BaseException, traceback: Any) -> None:
    RECORDS.rpush("announced", f"failed: {type(exc).__name__}")


@app.task
def announce_all(results: list[str]) -> None:
    """A chord's body: tell the customer every message in the header was sent."""
    RECORDS.rpush("announced", f"sent {len(results)} messages")


@app.task(acks_late=True, reject_on_worker_lost=True)
def send_message_once(message: str) -> str:
    """Requeued when its pool child is lost, and sent with a key, so a repeat leaves no second message."""
    if RECORDS.set(f"key:{message}", 1, nx=True):
        RECORDS.rpush("sent", message)
    return message
