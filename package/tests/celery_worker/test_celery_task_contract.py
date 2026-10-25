"""
task_contract on the reference application: what Celery declares for each task configuration, and what it does not.

Each suite is generated from one ``task_contract`` call, through a real ``celery worker`` with one prefork child:

* the default configuration, which declares Celery's rows: a task lost as it starts never runs, and one lost after
  its body ran is recorded FAILURE though its message left;
* a task that keeps no result, observed by its message alone, settled when the worker is idle;
* a task the application recovers with a sweep of what it still owes, which declares nothing: every failure must
  converge;
* the same task without its sweep bound, whose lost message fails the history, so a missing recovery is caught.
"""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from pytest_obligation import due_work_contract_suite
from pytest_obligation.crash_histories import HistoriesDiverged
from pytest_obligation.integrations.celery_tasks import UNOBSERVED, task_contract
from pytest_obligation.integrations.task_queues import TaskOutcome
from pytest_obligation.process_histories import assert_process_deaths_converge
from tests.celery_worker import app as reference
from tests.celery_worker.app import empty

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Celery's prefork pool does not run on Windows; running_worker refuses it"
)

APP = "tests.celery_worker.app:app"
ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}


def a_message() -> str:
    # ARRANGE: an empty broker, result backend and record, and a message no history has sent.
    empty()
    return f"your order {uuid4().hex[:8]} has shipped"


def messages_sent(_handle: object) -> int:
    # OBSERVE: how many messages left for the customer.
    return reference.RECORDS.llen("sent")


DEFAULT = task_contract(
    APP,
    reference.send_message,
    send=lambda: reference.send_message.delay(a_message()),
    effect=messages_sent,
    expected_effect=1,
    env=ENV,
)

FORGOTTEN = task_contract(
    APP,
    reference.send_and_forget,
    send=lambda: reference.send_and_forget.delay(a_message()),
    effect=messages_sent,
    expected_effect=1,
    env=ENV,
)

OWED = task_contract(
    APP,
    reference.deliver_owed,
    send=lambda: reference.owe(a_message()),
    effect=messages_sent,
    expected_effect=1,
    recovery=lambda _result: reference.sweep_owed(),
    recovered_by="the application's sweep of what it still owes",
    env=ENV,
)


@due_work_contract_suite(DEFAULT)
class TestDefaultConfiguration:
    """Celery's two rows are declared, a strict xfail pinned in the same run; every other stage converges."""


@due_work_contract_suite(FORGOTTEN)
class TestTaskWithoutResult:
    """
    Celery records nothing for this task, so only a delivery lost as it starts differs: its message never leaves.

    A run whose delivery was lost settles when the worker is idle, not when a result arrives, since none will.
    """


@due_work_contract_suite(OWED)
class TestApplicationRecovery:
    """The application's sweep recovers what the worker lost: every stage converges, with nothing declared."""


def test_celery_declares_only_what_differs_for_a_task_without_result() -> None:
    (history,) = FORGOTTEN.process_handoffs
    assert history.findings is not None
    assert history.findings.outcomes == {"died at task_prerun": TaskOutcome(status=UNOBSERVED, effect=0)}


def test_without_its_recovery_a_lost_delivery_fails_the_history() -> None:
    unrecovered = task_contract(
        APP,
        reference.deliver_owed,
        send=lambda: reference.owe(a_message()),
        effect=messages_sent,
        expected_effect=1,
        env=ENV,
        name="a worker runs deliver_owed with its sweep unbound",
    )
    (history,) = unrecovered.process_handoffs
    with pytest.raises(HistoriesDiverged, match="died at task_prerun"):
        assert_process_deaths_converge(history)
