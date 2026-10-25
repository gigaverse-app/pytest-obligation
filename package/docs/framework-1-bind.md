# 1. Bind your library once

[Overview](tutorial-framework-authors.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Start with the promise every task queue makes: **a job survives its worker
dying.** The binding for it is the foundation everything else reuses, and it
answers three questions only your library can answer.

## The test, in plain words

Take one job and run one worker pass on it, many times over. The first time,
let it finish and note the outcome: RQ records the job `finished`, and the
welcome email went out once. Then repeat it, killing the worker at a different
point each time: right after each write RQ makes to Redis, and right after the
job's own call to the email provider. After each death, run what a real
deployment runs (time passes, workers start, RQ's maintenance finds the dead
worker's job and gives it back) and look again. Every version must end like
the normal one.

pytest-obligation calls each run a **history**, and a step tested this way a
[handoff](vocabulary.md#handoff).

## Question 1: when does your library write?

To kill a worker "right after RQ writes to Redis", the harness must know when
that happens. It never guesses; a **host** tells it. For RQ, the integration
supplies `redis_host`, and an application configures it in one line of its
`conftest.py`:

```python
# The host: Redis writes are the commits a worker can die after, and their replies can be lost.
configure(redis_host(welcome_rq.connection, {"welcome_rq"}))
```

| Name | Comes from | What it does |
| --- | --- | --- |
| `redis_host(client, packages)` | pytest-obligation's Redis integration | Watches every command on the client's connections. Each write (a command Redis flags as a write, a pipeline holding one, a script) counts as a commit the harness can kill the worker after. It can also lose the *reply* to a write after the write has landed. |
| `configure(...)` | pytest-obligation | Installs the host for the test session |
| `{"welcome_rq"}` | The application | Its production package: the harness checks that bindings call this code rather than a copy of it |

For your library, this is a context manager that counts your library's own
commits and can kill the worker after the chosen one. If your library writes
through one client or one connection, hook that; pytest-obligation's
`CommitWorker` does the counting.

## Question 2: what does one worker pass look like?

The integration's `worker_pass` runs RQ's real worker, in process, for one
burst over the given queues:

<!-- fmt:off -->
```python
    def run(*_handle: object) -> None:
        from rq import Queue, SimpleWorker
        from rq.utils import now

        worker = (worker_class or SimpleWorker)(
            [Queue(name, connection=connection) for name in queues], connection=connection
        )
        if not starting:
            worker.last_cleaned_at = now()
        try:
            with keeping_signal_handlers():
                worker.work(burst=True, max_jobs=max_jobs, logging_level="WARNING")
        finally:
            thread = worker.pubsub_thread
            if thread is not None and thread.is_alive():
                thread.stop()
                thread.join(timeout=1)
```
<!-- fmt:on -->

Nothing here imitates RQ: it is RQ's `SimpleWorker`, doing what it does in
production. That matters, because a test that drives a copy of the worker
keeps passing after the real worker changes.

## Question 3: how does your library recover?

After a death, the harness runs what a deployment would run. In RQ, a newly
started worker's maintenance cleans up the registry of started jobs, and a job
whose worker stopped sending heartbeats is given back if it has retries left.
The integration's `maintenance_passes` runs three such workers, an hour apart
on a frozen clock, so every lease has expired by the time they look. A frozen
clock is part of what `redis_host` supplies.

## The handoff

The integration puts these together with `worker_history`, from
pytest-obligation's task-queue helpers. It enqueues one of the application's
jobs, runs `worker_pass` as the step, and observes two things: the status RQ
recorded, and what the job actually did. The application supplies the last
two (chapter 5 shows how).

## What the harness ran

For the welcome job, the harness counted **25 writes to Redis** in one worker
pass, plus one call to the email provider. From that it built 52 histories:

| Histories | What happened | Status, emails |
| --- | --- | --- |
| normal operation | Nothing failed | `finished`, 1 |
| worker died after commit 1 to 25 | One history per Redis write; recovery found the job and finished it | `finished`, 1 in every history |
| worker died after external call 1 | Died right after the email left, before RQ recorded the job finished | `finished`, 1 |
| the reply to commit 1 to 25 was lost | The write landed, but the worker was told it failed | `finished`, 1 in every history |

Every history ends `finished` with exactly one email, because the welcome job
sends with a deduplication key, so a rerun is harmless. Chapter 5 shows the
same 52 histories for a version of the job without the key.

Notice what nobody wrote: the list of 25 points to kill the worker at. The
host counted RQ's writes itself. If an RQ release adds a write to its worker,
the next run has one more history, and no test changes.

[Next: 2. Test your hardest problems](framework-2-hard-problems.md)
