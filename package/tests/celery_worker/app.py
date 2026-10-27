"""The reference Celery application the worker self-tests run: a task that sends a message, its link, its errback."""

import os
from typing import Any

import redis
from celery import Celery
from celery.result import AsyncResult

from tests.redis_databases import redis_url

#: A Redis server of its own for the broker-full history: that fault refuses writes on the whole server.
OWN_BROKER = os.environ.get("CELERY_OWN_BROKER_URL")
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


@app.task(ignore_result=True)
def send_and_forget(message: str) -> None:
    """Keeps no result, so a lost delivery leaves nothing Celery recorded, only what the message did."""
    RECORDS.rpush("sent", message)


@app.task
def deliver_owed(message: str) -> None:
    """Sends a message the application owes, then settles what it owes."""
    # EXTERNAL SEAM: the message leaves for the customer.
    RECORDS.rpush("sent", message)
    RECORDS.srem("owed", message)


def owe(message: str) -> AsyncResult:
    """REAL PRODUCTION: the application records what it owes, then sends the task that pays it."""
    RECORDS.sadd("owed", message)
    return deliver_owed.delay(message)


def sweep_owed() -> None:
    """REAL PRODUCTION: the application's recovery sweep sends again whatever it still owes."""
    for message in RECORDS.smembers("owed"):
        deliver_owed.delay(message)


#: Where send_to_outbox writes; the worker's setup moves it, as a test double would replace a provider.
OUTBOX = ["production outbox"]


@app.task
def send_to_outbox(message: str) -> None:
    RECORDS.rpush(OUTBOX[0], message)


def use_test_outbox() -> None:
    """ARRANGE, in the worker: send_to_outbox writes to the test outbox instead."""
    OUTBOX[0] = "test outbox"
