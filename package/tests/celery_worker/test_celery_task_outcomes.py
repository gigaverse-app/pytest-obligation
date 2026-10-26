"""celery_outcomes: what Celery declares for each task configuration, without running a worker."""

import pytest
from celery import Celery

from pytest_obligation.integrations.celery_tasks import UNOBSERVED, celery_outcomes, records_state, runs_again
from pytest_obligation.integrations.task_queues import TaskOutcome

KEEPING = Celery("keeping_results", backend="cache+memory://")


@KEEPING.task
def default() -> None: ...


@KEEPING.task(acks_late=True, reject_on_worker_lost=True)
def requeued() -> None: ...


@KEEPING.task(acks_late=True)
def acknowledged_late() -> None: ...


@KEEPING.task(ignore_result=True)
def ignoring() -> None: ...


def rows(task: object, **options: bool) -> dict[str, TaskOutcome]:
    return celery_outcomes(task, initial_effect=0, expected_effect=1, **options)


def test_default_configuration_declares_a_lost_start_and_a_lost_store() -> None:
    assert rows(default) == {
        "died at task_prerun": TaskOutcome(status="FAILURE", effect=0),
        "died at mark_as_done": TaskOutcome(status="FAILURE", effect=1),
    }


@pytest.mark.parametrize("task", [default, acknowledged_late], ids=["default", "acks_late alone"])
def test_a_task_not_requeued_declares_the_same_rows_by_sigkill(task: object) -> None:
    declared = rows(task, sigkill=True)
    assert declared["died at task_prerun (SIGKILL)"] == declared["died at task_prerun"]
    assert declared["died at mark_as_done (SIGKILL)"] == declared["died at mark_as_done"]


def test_a_requeued_task_declares_no_death_its_second_run_is_its_own() -> None:
    assert runs_again(requeued)
    assert rows(requeued, sigkill=True) == {}


def test_a_refused_link_is_declared_for_every_configuration() -> None:
    assert rows(requeued, publishes=True) == {
        "the broker refused the task's link": TaskOutcome(status="FAILURE", effect=1)
    }


@pytest.fixture
def without_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    """A task of an application with no result backend; Celery's environment variable would give it one."""
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    forgetting = Celery("no_result_backend")

    @forgetting.task
    def forgotten() -> None: ...

    return forgotten


@pytest.mark.parametrize("configuration", ["ignore_result", "no result backend"])
def test_without_a_record_only_a_lost_start_differs(configuration: str, request: pytest.FixtureRequest) -> None:
    task = ignoring if configuration == "ignore_result" else request.getfixturevalue("without_backend")
    assert not records_state(task)
    # Lost after its body ran, the task looks exactly like a normal run: its effect happened and nothing is recorded.
    assert rows(task, publishes=True) == {"died at task_prerun": TaskOutcome(status=UNOBSERVED, effect=0)}
