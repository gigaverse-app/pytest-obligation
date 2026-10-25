# 1. Bind your library once

[Overview](tutorial-framework-authors.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Start with tinyq's first promise: **a job survives its worker dying.** It is
also the easiest one to bind, and the binding you write here is reused by
every later chapter.

## The test, in plain words

Take one job and run one worker pass on it, many times over. The first time,
let it finish normally and note the outcome: the job is `done`, and its task's
effect happened once. Then repeat it, killing the worker at a different point
each time: right after each moment tinyq saves something, and right after each
call the task makes to an outside system. After each death, run what a real
deployment would run (time passes, the sweep returns the job, workers pick it
up) and look again. Every version must end like the normal one.

pytest-obligation calls each of these runs a **history**, and a step tested
this way a [handoff](vocabulary.md#handoff). It needs three things from you:
where your library commits, how it recovers, and the step itself.

## Where your library commits

To kill a worker "right after tinyq saves something", the harness must know
when tinyq commits. It never guesses; a **host** tells it. Your library is the
right place to answer that once, so that your users never have to. tinyq sends
every SQL statement through `_execute` and every commit through
`_transaction`, so [`tinyq/testing.py`](../../examples/task_queue_tutorial/tinyq/testing.py)
watches those two:

```python
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
```

| Name | Comes from | What it does |
| --- | --- | --- |
| `CommitWorker` | pytest-obligation | Counts commits. Asked to die after commit *k*, it raises `WorkerDied` there and refuses every later statement, because a dead process runs nothing more. |
| `tinyq_worker_killer` | tinyq | Installs a `CommitWorker` on tinyq's two methods while one history runs |
| `Host` | pytest-obligation | What only your library knows. `production_packages` names the code under test. |

The integrations that ship with pytest-obligation do the same at their own
level: `redis_host` watches the Redis client's commands, and `django_host`
watches the database connection's commit.

## How your library recovers

After a death, the harness runs what a deployment would run. For tinyq: wait
out the lease, run the sweep, run the workers.

```python
def recover(queue: Queue, *, rounds: int = 3) -> None:
    """What a deployment runs: the expired-lease sweep and the workers, after enough time for leases and retries."""
    for _round in range(rounds):
        _clock(queue).advance(queue.lease_seconds + queue.retry_delay + 1)
        queue.reclaim_expired()
        queue.run_until_idle()
```

tinyq's clock is injectable, so in tests "wait 30 seconds" is a call to
`advance`, and every history runs in milliseconds.

## The step itself

`worker_history`, from pytest-obligation's task-queue helpers, turns one worker
pass into a handoff. It enqueues a job, runs `work_once`, and observes two
things: the status tinyq recorded, and what the task actually did.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

`CallableDelivery` tells the harness how the job reaches a worker and how
production recovers. tinyq's queue is a table its workers poll, so there is no
message that could be lost on the way, and the delivery declares none. (These
lines are part of `task_contract`, which chapter 5 assembles.)

## What the harness ran

For a job whose task sends one welcome email, these are the histories, and
what each ended with:

| History | What happened | Status, emails |
| --- | --- | --- |
| normal operation | Nothing failed | `done`, 1 |
| worker died after commit 1 | Died right after taking the job; the sweep gave it back and another pass ran it | `done`, 1 |
| worker died after commit 2 | Died right after recording `done`; nothing left to do | `done`, 1 |
| worker died after external call 1 | Died right after the email left, before recording `done`; the job ran again | `done`, 1 with a task that sends a deduplication key, **2** with one that does not |

The promise holds: every history ends `done`. The last row is its price: the
task ran twice. That is not tinyq's to fix. It is the property of the user's
task that chapter 5 hands back to users as a test of their own.

Notice what you did not write: the list of points to kill the worker at. The
harness counted tinyq's commits itself. Add a commit to `work_once` and the
next run has one more history.

[Next: 2. Test your hardest problems](framework-2-hard-problems.md)
