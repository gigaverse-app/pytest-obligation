# 2. Test your hardest problems

[Previous: 1. Bind your library once](framework-1-bind.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Two problems every task queue has to get right, and every maintainer has tests
for: a failing job must stop after its retries, and a worker that is presumed
dead but comes back must not be able to undo its replacement's work. This
chapter binds RQ's own machinery for both to pytest-obligation's standard
proofs, then looks at what the generated tests add to a hand-written suite.

## A failing job stops after its last retry

The integration's `bounded_retry` points pytest-obligation's `BoundedRetry`
proof at RQ's `Retry`:

<!-- fmt:off -->
```python
    return BoundedRetry(
        name=f"rq {queue} Retry(max={max_retries})",
        max_executions=max_retries + 1,
        make_failing=enqueue_failing,
        due_work=rq_queue.get_job_ids,
        run_once=run_one,
        advance_to_due=lambda _job_id: None,
        is_terminal=lambda job_id: status_of(job_id) == "failed",
        failure_attempt_count=failures,
        observe=observe,
    )
```
<!-- fmt:on -->

| Field | Bound to |
| --- | --- |
| `make_failing` | The application's command, enqueuing a job whose dependency is down |
| `due_work` | The job ids waiting in RQ's queue |
| `run_once` | One real worker pass that takes one job |
| `advance_to_due` | Nothing: these retries have no interval |
| `is_terminal` | RQ records the job `failed` |
| `failure_attempt_count` | How often the job really reached its failing dependency, counted by the application's stand-in |

The proof checks four things: the job is waiting before every attempt; each
worker pass reaches the failing dependency exactly once; the job is `failed`
exactly after `max_retries + 1` runs; and one more pass changes nothing and
calls nothing. Counting at the dependency is what makes this stronger than
reading RQ's bookkeeping: an attempt that was recorded but never ran fails it.

## A late worker cannot undo its replacement

The scenario, in RQ's terms:

```text
10:00:00  worker A takes job 7 and starts it
10:00:05  A stops sending heartbeats (a long pause, a hung call)
10:00:40  another worker's maintenance cleans up job 7 and gives it back
10:00:41  worker B takes job 7, and finishes it
10:00:50  A wakes up, and records its own result for job 7
```

pytest-obligation's `FencedOwnership` proof needs a handful of operations, and
the integration's `ownership` binds each to the RQ code that does it:

| What the proof needs | RQ's code |
| --- | --- |
| Take a job, returning it and a token for this attempt | dequeue and prepare an execution, the way a worker does; the token stands for the execution |
| Every result an owner can record | `handle_job_success`, `handle_job_failure` |
| Renew the lease | `maintain_heartbeats` |
| Make the owner "die" | push its heartbeat into the past |
| Give back a dead owner's job | `StartedJobRegistry.cleanup`, which every worker's maintenance runs |
| What the job looks like right now | its status, and its executions with their lease deadlines |

<!-- fmt:off -->
```python
    return FencedOwnership(
        name=f"rq {queue} jobs",
        make_claimable=enqueue,
        claim=claim,
        fenced_write=finish,
        other_fenced_writes={"fail": fail},
        renew_lease=heartbeat,
        expire_lease=expire,
        reclaim_stalled=reclaim,
        observe=observe,
    )
```
<!-- fmt:on -->

Each of `claim`, `finish`, `fail` and the rest is a few lines that call RQ's
worker methods directly; see `ownership` in
[`integrations/rq.py`](../src/pytest_obligation/integrations/rq.py).

## What the generated tests add

A hand-written test for this area usually checks one scenario. From the one
binding above, the harness generates twelve cases:

- **Every result an owner can record**, not only success. A stale *failure*
  matters as much: it can send a job back to the queue while its new owner is
  still running it.
- **Refusal that changes nothing.** A refused write must leave the job exactly
  as it was, so a guard that reports failure after writing is caught.
- **Acceptance too.** The current owner's writes and heartbeats must work and
  must change the job; otherwise an implementation that refuses everything
  would pass every refusal check.
- **Two claims racing**, in sequence and from two threads started together.
- **The cleanup's boundaries**: it leaves a job alone while its lease runs,
  takes it back after, and the next owner is a new attempt.

On RQ 2.12, the version the repository pins, eleven of the twelve pass. The
twelfth describes a choice in RQ's design: RQ identifies a running job by its
id, not by which execution holds it, so at 10:00:50 worker A's result is
recorded. For an RQ maintainer, that is what the proofs are for: the property
is now stated, tested, and visible, and it can be kept on purpose or changed.
Chapter 4 shows how the module you ship declares such properties once, so
every application's contract already expects them.

## Faults your host adds

Killing the worker after each commit is one fault family. A host can supply
more, and each gives every handoff one more history per occurrence:

| Fault | Host capability | In the shipped integrations |
| --- | --- | --- |
| The reply to a write is lost, after the write landed | `reply_breaker` | `redis_host` and `mongodb_host`: the 25 lost-reply histories in chapter 1 |
| A job callback or signal receiver raises | `receiver_breaker` | `rq_callback_breaker` fails RQ's `on_success` and `on_failure` callbacks in turn; `django_receiver_breaker` does the same for signals |
| An after-commit callback fails | `callback_breaker` | `django_host`, for each `on_commit` callback |
| The broker refuses a publish | `publication_breaker` | `celery_publication_breaker`, for each Celery publish |

Each is a small context manager that counts occurrences and makes the chosen
one fail; the protocols are in [`host.py`](../src/pytest_obligation/host.py).
A lost reply is the one most often missing from hand-written suites, because
it needs a write that succeeded and a client that believes it failed.

[Next: 3. A suite that keeps finding more](framework-3-growing.md)
