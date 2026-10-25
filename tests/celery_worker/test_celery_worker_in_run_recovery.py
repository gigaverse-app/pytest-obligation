"""
A task the worker recovers by itself, inside the run: requeued when its pool child is lost, and safe to repeat.

The worker's main process replaces the lost child and runs the requeued task again before the run ends, so a
restart afterwards finds nothing to do. The history observes each run as its fault left it, so that recovery
inside the run is what the verdict sees: every stage converges, and the contract passes with nothing declared.
"""

import sys
from pathlib import Path

import pytest
from celery.result import AsyncResult

from pytest_obligation import due_work_contract_suite
from pytest_obligation.integrations.celery_worker import worker_contract, worker_history
from tests.celery_worker import app as reference
from tests.celery_worker.app import empty

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Celery's prefork pool does not run on Windows; running_worker refuses it"
)

MESSAGE = "your order has shipped"


def send() -> str:
    # ARRANGE: an empty broker, result backend and record, then the task that is requeued and safe to repeat.
    empty()
    return reference.send_message_once.apply_async((MESSAGE,)).id


def what_happened(task_id: str) -> tuple[str, int]:
    # OBSERVE: the state Celery recorded, and how many messages left.
    return str(AsyncResult(task_id, app=reference.app).state), reference.RECORDS.llen("sent")


SENT_ONCE = worker_history(
    name="a worker runs a requeued task that is safe to repeat",
    app="tests.celery_worker.app:app",
    task=reference.send_message_once.name,
    send=send,
    observe=what_happened,
    initial=("PENDING", 0),
    expected=("SUCCESS", 1),
    settled=lambda task_id: AsyncResult(task_id, app=reference.app).ready(),
    failure_points=("the task's on_success hook raised",),
    env={"PYTHONPATH": str(Path(__file__).resolve().parents[2])},
)


@due_work_contract_suite(worker_contract(name="celery: a requeued task safe to repeat", process_handoffs=(SENT_ONCE,)))
class TestRecoveryInsideTheRun:
    """Every case is generated; the history converges at every stage, with nothing declared."""
