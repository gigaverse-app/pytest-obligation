# 2. Test your hardest problems

[Previous: 1. Bind your library once](framework-1-bind.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

You almost certainly have tests for retries and for workers that die holding a
job. This chapter binds tinyq's versions of those to pytest-obligation's
standard proofs, then looks at what the generated tests check that a
hand-written test usually does not.

## A failing job stops after its last attempt

Make the task's dependency fail every time. tinyq should try the job
`max_attempts` times, then mark it `failed` and leave it alone. `BoundedRetry`
checks that against tinyq's real worker. Each field names a piece of tinyq, or
of the application whose task is failing:

| What the proof needs | What tinyq gives it |
| --- | --- |
| A job whose task always fails | the application's command, with its dependency set to fail |
| The jobs a worker would take now | `queue.due` |
| One worker pass | `queue.work_once` |
| Wait until the retry is due | move tinyq's clock by `retry_delay` |
| Has the job given up? | `queue.status(job) == "failed"` |
| How often the failing dependency was really called | a counter on the dependency's stand-in |

```python
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
```

The proof checks four things: the job is selected before every attempt; each
worker pass reaches the failing dependency exactly once; the job becomes
`failed` exactly at the last attempt; and one more pass changes nothing and
calls nothing. Counting at the dependency is the point: a queue that recorded
attempts without running them would pass a test that only reads the
`attempts` column, and fails this one.

## A worker that comes back late changes nothing

tinyq's version of the classic scenario:

```text
10:00:00  worker A takes job 7
10:00:05  A gets stuck (a long pause, a hung network call)
10:00:30  A's lease passes; the sweep puts job 7 back
10:00:31  worker B takes job 7, and finishes it
10:00:40  A wakes up, and tries to record that job 7 failed
```

tinyq gives every claim a fresh token and fences every owner update on it, so
A's update at 10:00:40 matches no row:

<!-- fmt:off -->
```python
    def claim(self) -> tuple[int, uuid.UUID] | None:
        """Take the oldest due job: mark it running, give it a fresh token, and start its lease."""
        with self._transaction():
            job_id = self._one(DUE, self.clock())
            if job_id is None:
                return None
            token, lease_until = uuid.uuid4(), self.clock() + self.lease_seconds
            sql = "UPDATE jobs SET status = 'running', token = ?, lease_until = ? WHERE id = ?"
            self._run(sql, str(token), lease_until, job_id)
        return job_id, token

    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        """Mark the job done, but only if the caller still owns it."""
        with self._transaction():
            return self._run(f"UPDATE jobs SET status = 'done' WHERE {OWNED}", job_id, str(token)) == 1
```
<!-- fmt:on -->

`OWNED` is `id = ? AND token = ? AND status = 'running'`, shared by every owner
update. `FencedOwnership` takes one of your methods per field:

| What the proof needs | tinyq's method |
| --- | --- |
| Create a job that can be taken | the application's own command |
| Take a job, returning its id and token | `claim` |
| Every update an owner can make | `complete`, `fail` |
| Extend a lease | `renew` |
| Make an owner "die": let its lease pass | move tinyq's clock past the lease |
| Run the sweep for one job | `reclaim_expired` |
| What the job looks like right now | `state` |

```python
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
```

## What the generated tests add

A typical hand-written test for this area checks one scenario: a stale worker
calls `complete`, and the call is refused. From the one binding above, the
harness generates twelve cases, and several close gaps a single scenario
leaves open:

- **Every owner update, not only the success path.** A stale `fail` matters as
  much as a stale `complete`: an unfenced `fail` sends a job back to `ready`
  while its new owner is still running it, so it runs twice at once. Each
  entry in `other_fenced_writes` gets the same refusal proof.
- **Refusal that changes nothing.** With `observe`, a refused update must leave
  the job identical, so a guard that reports failure after the write already
  happened is caught.
- **Acceptance as well as refusal.** The current owner's update and renewal
  must work and must change the job. Without this, an implementation that
  refuses everything, or does nothing, passes every refusal check.
- **Two claims racing**, sequentially and from two threads started at a barrier.
- **The sweep's boundaries**: it must leave a job alone while its lease runs,
  must take it back after, and the next claim must get a new token.

On tinyq, these found two things. Its first draft of recording a result, kept
in [`tinyq/draft.py`](../../examples/task_queue_tutorial/tinyq/draft.py),
checked which job to update but not who was updating it:

```python
class DraftQueue(Queue):
    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        with self._transaction():
            return self._run("UPDATE jobs SET status = 'done' WHERE id = ?", job_id) == 1
```

```text
tinyq job ownership: fenced_write, other_fenced_writes['fail'] carrying a superseded token was
accepted. A slow worker that wakes up after its claim was reaped would corrupt the new owner's state
```

And the two-thread race found that tinyq's worker threads, sharing one
database connection, interleaved their transactions. Without a lock in
`_transaction`, it failed on every one of 30 runs:

```text
AssertionError: tinyq job ownership: a racing claim raised instead of losing cleanly:
[OperationalError('cannot commit - no transaction is active')]. ...
```

## Faults your host can add

Killing the worker after each commit is the start. If your host can also
inject these, every handoff gets one more history per occurrence:

| Fault | Host capability | Example in the shipped integrations |
| --- | --- | --- |
| The reply to a commit is lost, after the write landed | `reply_breaker` | `redis_host` and `mongodb_host` lose replies to writes |
| An after-commit callback fails | `callback_breaker` | `django_host` fails each `on_commit` callback in turn |
| The broker refuses a publish | `publication_breaker` | `celery_publication_breaker` refuses each Celery publish |
| A signal receiver or hook raises | `receiver_breaker` | `django_receiver_breaker`, and RQ's job callbacks |

Each is a small context manager that counts occurrences and makes the chosen
one fail; the protocols are in [`host.py`](../src/pytest_obligation/host.py).
A lost reply is the one most often missing from hand-written suites, because
it needs a write that succeeds and a client that believes it failed.

[Next: 3. A suite that keeps finding more](framework-3-growing.md)
