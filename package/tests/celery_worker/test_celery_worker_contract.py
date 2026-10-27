"""
The Celery worker integration, run against Celery itself on the reference task.

The worker is a real ``celery worker`` with one prefork child, as a child
process. What Celery does not hold is one gap, a strict xfail, pinned history by
history in ``FINDINGS`` within the same run, so a change in Celery turns this
suite red until the table is updated.
"""

import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import celery
import pytest
import redis
from celery import chord
from celery.app.task import Task
from celery.result import AsyncResult
from packaging.version import Version

from pytest_obligation import Claim, Findings, Profile, ReplaySafeEffect, due_work_contract_suite
from pytest_obligation.host import Host, hosted
from pytest_obligation.integrations.celery_worker import (
    BROKER_FULL,
    DEATH_POINTS,
    FAILURE_POINTS,
    SIGKILL_DEATH_POINTS,
    worker_contract,
    worker_history,
)
from pytest_obligation.process_histories import ProcessHistory
from tests.celery_worker import app as reference
from tests.celery_worker.app import empty

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Celery's prefork pool does not run on Windows (billiard spawns the pool child, which inherits neither "
    "the fault nor usable pool semaphores); running_worker refuses it",
)

MESSAGE = "your order has shipped"
SENT = f"sent {MESSAGE!r}"


def send() -> str:
    empty()
    return reference.send_message.apply_async(
        (MESSAGE,), link=reference.announce.s(), link_error=reference.report_failure.s()
    ).id


def send_on_own_broker() -> str:
    # The same task, published to a broker on a Redis server of its own, which BROKER_FULL fills.
    empty()
    assert reference.OWN_BROKER, "broker-full tests require a separate disposable CELERY_OWN_BROKER_URL"
    redis.Redis.from_url(reference.OWN_BROKER).flushdb()
    with reference.app.connection_for_write(reference.OWN_BROKER) as connection:
        return reference.send_message.apply_async(
            (MESSAGE,),
            link=reference.announce.s(),
            link_error=reference.report_failure.s(),
            producer=reference.app.amqp.Producer(connection),
        ).id


def send_chord() -> str:
    # Two messages, and a body that announces them once both are sent; the body's error callback reports a failure.
    empty()
    header = [reference.send_message.s(f"order {n} has shipped").on_error(reference.report_failure.s()) for n in (1, 2)]
    return chord(header)(reference.announce_all.s().on_error(reference.report_failure.s())).id


def what_happened(task_id: str) -> tuple[str, int, tuple[str, ...]]:
    # decode_responses=True makes every reply a str; redis-py's annotations do not follow it.
    announced = cast("list[str]", reference.RECORDS.lrange("announced", 0, -1))
    return (
        str(AsyncResult(task_id, app=reference.app).state),
        reference.RECORDS.llen("sent"),
        # Sorted: the link and the error callback run in different processes, in either order.
        tuple(sorted(announced)),
    )


#: Celery #10752 and #10759 stopped a task whose SUCCESS was stored from running its error callback. Both
#: merged after 5.7.0rc1, so a released Celery has them from the next release on. (A build of Celery's main
#: between those merges and that release still reports 5.7.0rc1; this suite runs the locked release.)
#: Retire this gate and the rows passed to before_the_10724_fixes once uv.lock's Celery is newer than 5.7.0rc1.
SUCCESS_STORED_STAYS_SUCCESS = Version(celery.__version__) > Version("5.7.0rc1")


def before_the_10724_fixes(rows: dict[str, Any]) -> dict[str, Any]:
    """Rows that diverge only on a Celery without #10752 and #10759 (https://github.com/celery/celery/issues/10724)."""
    return {} if SUCCESS_STORED_STAYS_SUCCESS else rows


def reference_history(
    name: str,
    send: Callable[[], str],
    findings: Findings,
    *,
    death_points: Sequence[str] = DEATH_POINTS,
    failure_points: Sequence[str] = FAILURE_POINTS,
    broker_url: str | None = None,
) -> ProcessHistory[str, Any]:
    """Work the reference worker runs, observed the same way: the result's state, messages sent, announcements."""
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    if broker_url is not None:
        # Celery takes CELERY_BROKER_URL from the environment over the application's own broker setting.
        env["CELERY_BROKER_URL"] = broker_url
    return worker_history(
        name=name,
        app="tests.celery_worker.app:app",
        task=reference.send_message.name,
        send=send,
        observe=what_happened,
        initial=("PENDING", 0, ()),
        expected=findings.delivered,
        settled=lambda task_id: AsyncResult(task_id, app=reference.app).ready(),
        death_points=death_points,
        failure_points=failure_points,
        findings=findings,
        env=env,
        broker_url=broker_url,
    )


# What each failure leaves after the worker starts again; every history not listed reaches normal operation.
FINDINGS = Findings(
    ("SUCCESS", 1, (SENT,)),
    {
        "died at task_prerun": ("FAILURE", 0, ("failed: WorkerLostError",)),
        # https://github.com/celery/celery/issues/10954
        "died at mark_as_done": ("FAILURE", 1, ("failed: WorkerLostError", SENT)),
        # The kernel's SIGKILL reaches the parent through billiard's signal path, and leaves the same.
        "died at task_prerun (SIGKILL)": ("FAILURE", 0, ("failed: WorkerLostError",)),
        "died at mark_as_done (SIGKILL)": ("FAILURE", 1, ("failed: WorkerLostError", SENT)),
        # https://github.com/celery/celery/issues/10725
        "the broker refused the task's link": ("FAILURE", 1, ("failed: OperationalError",)),
    }
    | before_the_10724_fixes(
        {
            "died at task_postrun": ("SUCCESS", 1, ("failed: WorkerLostError", SENT)),
            "died at task_postrun (SIGKILL)": ("SUCCESS", 1, ("failed: WorkerLostError", SENT)),
            "the task's on_success hook raised": ("SUCCESS", 1, ("failed: ReceiverFailed", SENT)),
        }
    ),
)

# Redis itself refuses the link's publish, and kombu raises the OperationalError the injected refusal does.
FULL_BROKER_FINDINGS = Findings(
    ("SUCCESS", 1, (SENT,)),
    {
        # https://github.com/celery/celery/issues/10725
        BROKER_FULL: ("FAILURE", 1, ("failed: OperationalError",)),
    },
)

# The chord's state is its body's; its faults hit the first execution of a header task, and the refused
# publish is the last header's publish of the body.
CHORD_FINDINGS = Findings(
    ("SUCCESS", 2, ("sent 2 messages",)),
    {
        "died at task_prerun": ("FAILURE", 1, ("failed: ChordError", "failed: WorkerLostError")),
        # https://github.com/celery/celery/issues/10954
        "died at mark_as_done": ("FAILURE", 2, ("failed: ChordError", "failed: WorkerLostError")),
        # https://github.com/celery/celery/issues/10725#issuecomment-6318108091
        "the broker refused the task's link": ("FAILURE", 2, ("failed: ChordError",)),
    }
    # Before the fixes, a header lost after its stored SUCCESS is counted twice, once as a failure.
    | before_the_10724_fixes(
        {
            "died at task_postrun": ("FAILURE", 2, ("failed: ChordError", "failed: WorkerLostError")),
            "the task's on_success hook raised": ("FAILURE", 2, ("failed: ChordError", "failed: ReceiverFailed")),
        }
    ),
)

SEND_MESSAGE = reference_history(
    "the reference worker runs send_message", send, FINDINGS, death_points=DEATH_POINTS + SIGKILL_DEATH_POINTS
)
FULL_BROKER = reference_history(
    "the reference worker runs send_message on a broker of its own",
    send_on_own_broker,
    FULL_BROKER_FINDINGS,
    death_points=(),
    failure_points=(BROKER_FULL,),
    broker_url=reference.OWN_BROKER,
)
CHORD = reference_history("the reference worker runs a chord of two send_message tasks", send_chord, CHORD_FINDINGS)


@contextmanager
def message_replay() -> Iterator[ReplaySafeEffect]:
    # ARRANGE: a fresh customer message and a cleared external delivery ledger.
    # REAL PRODUCTION: Celery's Task.apply tracer runs the real task body for both deliveries.
    # EXTERNAL SEAM: the task's Redis-backed recipient ledger, also used by the real process histories.
    # OBSERVE: exact delivered-message count, independent of Celery's result status.
    reference.RECORDS.flushdb()
    with hosted(Host(production_packages=frozenset({"celery"}))):
        yield ReplaySafeEffect(
            name="Celery message task",
            expected=1,
            prepare=lambda: MESSAGE,
            execute=lambda message: Task.apply(reference.send_message, (message,), throw=True).get(propagate=True),
            observe=lambda message: reference.RECORDS.lrange("sent", 0, -1).count(message),
            execution_count_for=lambda message: reference.RECORDS.lrange("sent", 0, -1).count(message),
        )


CONTRACT = worker_contract(
    name="celery reference worker",
    process_handoffs=(SEND_MESSAGE, FULL_BROKER, CHORD),
    handoff_gaps={
        SEND_MESSAGE.name: "a failure after the link is published, or a refused link, still runs the failure path",
        FULL_BROKER.name: "a broker that refuses the link's publish records FAILURE and acknowledges the message",
        CHORD.name: "a header lost after its effect, or a refused body publish, fails the chord for good",
    },
)


CONTRACT = CONTRACT.model_copy(
    update={
        "profiles": {
            **CONTRACT.profiles,
            Profile.H: Claim(
                gaps={"assert_replay_converges": "The reference task sends a second customer message on blind replay."}
            ),
        },
        "replay": message_replay,
    }
)


@due_work_contract_suite(CONTRACT)
class TestCeleryWorkerContract:
    """Generated from CONTRACT: the process case checks FINDINGS and the verdict in one run."""
