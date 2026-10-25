"""tinyq's testing layer: what tinyq ships so its users get generated failure tests for their own tasks.

A user supplies three things about one of their tasks: how to enqueue it, how to
see its effect, and what that effect must be. Everything tinyq knows about itself
comes from here: where its commits are, how its worker recovers, what it
guarantees, and what it deliberately leaves to each task.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import partial
from typing import Any
from unittest.mock import patch

from pytest_obligation import (
    Adoption,
    BoundedRetry,
    CallableDelivery,
    Claim,
    Decline,
    ExternalCall,
    FencedOwnership,
    Host,
    NotApplicable,
    ObligationContract,
    Profile,
)
from pytest_obligation.integrations.task_queues import (
    TaskOutcome,
    application_admission,
    application_gate,
    replay_safety_is_the_functions,
    settled_by_one_worker,
    the_obligation_is_the,
    worker_history,
)
from pytest_obligation.worker_death import CommitWorker
from tinyq import Queue

# The worker the harness is currently counting, while a history's transition runs.
_current: CommitWorker | None = None
_execute, _transaction = Queue._execute, Queue._transaction


def _counted_execute(queue: Queue, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    if _current is not None:
        _current.refuse_if_dead()
    return _execute(queue, sql, parameters)


@contextmanager
def _counted_transaction(queue: Queue) -> Iterator[None]:
    if _current is not None:
        _current.refuse_if_dead()
    with _transaction(queue):
        yield
    if _current is not None:
        _current.committed()


@contextmanager
def tinyq_worker_killer(kill_after: int | None) -> Iterator[CommitWorker]:
    """Count every commit tinyq makes, and kill the worker right after commit `kill_after` (None: only count)."""
    global _current
    _current = CommitWorker(kill_after)
    with patch.object(Queue, "_execute", _counted_execute), patch.object(Queue, "_transaction", _counted_transaction):
        try:
            yield _current
        finally:
            _current = None


def tinyq_host(production_packages: set[str]) -> Host:
    """The host a tinyq user configures once in conftest.py: their packages, plus tinyq itself."""
    return Host(production_packages=frozenset({"tinyq", *production_packages}), worker_killer=tinyq_worker_killer)


class ManualClock:
    """A clock tests move by hand, so leases expire and retries come due without waiting."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _clock(queue: Queue) -> ManualClock:
    assert isinstance(queue.clock, ManualClock), "give the queue a tinyq.testing.ManualClock in your test settings"
    return queue.clock


def empty(queue: Queue) -> None:
    """Delete every job, so each generated case starts from an empty queue."""
    with queue.db:
        queue.db.execute("DELETE FROM tinyq_jobs")


def recover(queue: Queue, *, rounds: int = 3) -> None:
    """What a deployment runs: the expired-lease sweep and the workers, after enough time for leases and retries."""
    for _round in range(rounds):
        _clock(queue).advance(queue.lease_seconds + queue.retry_delay + 1)
        queue.reclaim_expired()
        queue.run_until_idle()


def ownership(queue: Queue, *, enqueue: Callable[[], int]) -> FencedOwnership:
    # ARRANGE: jobs enqueued through the application's own command (enqueue).
    # REAL PRODUCTION: tinyq's claim, complete, fail, renew and reclaim_expired.
    # EXTERNAL SEAM: none; moving the queue's clock past the lease stands for the owner's death.
    # OBSERVE: the job's status, attempts and lease deadline (Queue.state).
    return FencedOwnership(
        name="tinyq job ownership",
        make_claimable=enqueue,
        claim=queue.claim,
        fenced_write=queue.complete,
        other_fenced_writes={"fail": lambda job_id, token: queue.fail(job_id, token, RuntimeError("stale owner"))},
        renew_lease=queue.renew,
        expire_lease=lambda _job_id: _clock(queue).advance(queue.lease_seconds + 1),
        reclaim_stalled=lambda job_id: job_id if job_id in queue.reclaim_expired() else None,
        observe=queue.state,
    )


def bounded_retry(
    queue: Queue, *, enqueue_failing: Callable[[], int], failures: Callable[[int], int], max_attempts: int
) -> BoundedRetry:
    # ARRANGE: a job whose task fails every time (enqueue_failing).
    # REAL PRODUCTION: tinyq's due selection and one worker pass, as a deployment runs them.
    # EXTERNAL SEAM: the failing dependency, whose calls the application counts (failures).
    # OBSERVE: the job's status, attempts and lease deadline (Queue.state).
    return BoundedRetry(
        name="tinyq retries",
        max_executions=max_attempts,
        make_failing=enqueue_failing,
        due_work=queue.due,
        run_once=lambda _job_id: queue.work_once(),
        advance_to_due=lambda _job_id: _clock(queue).advance(queue.retry_delay),
        is_terminal=lambda job_id: queue.status(job_id) == "failed",
        failure_attempt_count=failures,
        observe=queue.state,
    )


def task_contract(
    queue: Queue,
    *,
    name: str,
    enqueue: Callable[[], int],
    effect: Callable[[int], Any],
    expected: Any,
    enqueue_failing: Callable[[], int],
    failures: Callable[[int], int],
    max_attempts: int,
    external_calls: Sequence[ExternalCall] = (),
    handoff_gaps: dict[str, str] | None = None,
    fixtures: tuple[str, ...] = (),
) -> ObligationContract:
    """
    tinyq's contract with its worker, bound to one of the user's tasks.

    `enqueue` runs the user's command that enqueues the task and returns the job
    id; `effect` observes what the task did; `expected` is that effect after
    one successful run. tinyq claims and proves its own ownership (B) and retry
    budget (J), and gives every other profile tinyq's answer. The worker's crash
    history runs the user's real task under every fault, so a task that is not
    safe to repeat shows up as a divergence.
    """
    gaps = handoff_gaps or {}
    return ObligationContract(
        name=name,
        adoption=Adoption.LEGACY if gaps else Adoption.NEW_FEATURE,
        profiles={
            Profile.A: Decline(
                "workers poll the job table, so no message can be lost; reclaiming a dead worker's job is B"
            ),
            Profile.B: Claim(),
            Profile.C: Decline("tinyq runs a job at least once; a task must tolerate running again after a reclaim"),
            Profile.D: NotApplicable("tinyq never deletes jobs"),
            Profile.E: settled_by_one_worker("job"),
            Profile.F: the_obligation_is_the("job"),
            Profile.G: application_gate("tinyq"),
            Profile.H: replay_safety_is_the_functions("job", "tinyq", runs_again="after its worker died"),
            Profile.I: application_admission("tinyq"),
            Profile.J: Claim(),
        },
        ownership=partial(ownership, queue, enqueue=enqueue),
        retry=partial(
            bounded_retry, queue, enqueue_failing=enqueue_failing, failures=failures, max_attempts=max_attempts
        ),
        handoffs=(
            worker_history(
                name="a worker runs the task",
                enqueue=enqueue,
                effect=effect,
                expected=TaskOutcome(status="done", effect=expected),
                status_of=queue.status,
                run_worker=lambda _job_id: queue.work_once(),
                external_calls=external_calls,
            ),
        ),
        handoff_delivery=CallableDelivery(name=f"{name}: tinyq worker", recover=partial(recover, queue)),
        handoff_gaps=gaps,
        fixtures=fixtures,
    )


__all__ = [
    "ManualClock",
    "bounded_retry",
    "empty",
    "ownership",
    "recover",
    "task_contract",
    "tinyq_host",
    "tinyq_worker_killer",
]
