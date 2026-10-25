# Prove your task library's guarantees, and give your users tests

[All tutorials](tutorials.md) · [Vocabulary](vocabulary.md)

You maintain a task queue (a Celery, RQ or Django Tasks backend) or a durable
work library (something like procrastinate, DBOS or Due). Your README makes
promises:

- a job still runs if its worker dies;
- a worker that was presumed dead cannot overwrite the result of the worker
  that replaced it;
- a failing job is retried a fixed number of times, then stops;
- enqueueing commits together with the application's own writes.

Your unit tests check each function once, in one process, with nothing failing.
The promises live *between* those functions: in the gap between a claim and a
settlement, in two workers racing for the same row, in a worker that dies after
a task's effect but before its record. Unit tests rarely reach there, and the
bugs that live there are found by users in production.

They are not hypothetical. Pointed at real libraries,
[pytest-obligation found](../../demos/README.md):

| Library | Finding |
| --- | --- |
| procrastinate | `finish_job` does not check which worker is finishing, so a worker presumed dead can finish a job another worker has since taken |
| RQ | a lost reply from Redis, or a raising `on_success` callback, runs a finished job again |
| django-tasks-db | a `task_finished` receiver that raises rewrites a task that ran as FAILED; a task whose worker died stays RUNNING forever |
| DBOS | a death after a step's notification is sent, before DBOS records the step, sends the notification twice |

This tutorial has two halves:

1. **Prove your own guarantees.** Bind your library to pytest-obligation's
   standard proofs for ownership, retries and crashes, and let it find what
   your unit tests cannot.
2. **Give your users tests.** Ship a small testing module, so an application
   built on your library gets the same generated suite for *its own* tasks in a
   few lines, and learns when its task is not safe to run twice.

The library you will test is `tinyq`, a deliberately small task queue on SQLite
in [`examples/task_queue_tutorial`](../../examples/task_queue_tutorial). It is
about 150 lines, so you can read all of it. To run everything in this tutorial:

```bash
git clone https://github.com/gigaverse-app/pytest-obligation.git
cd pytest-obligation
uv sync --all-packages --locked
cd examples/task_queue_tutorial
uv run --project ../.. --no-sync pytest
```

It should end with `75 passed, 1 xfailed`. If you have not used
pytest-obligation before, [the multi-system tutorial](tutorial-many-systems.md)
introduces crash histories on an application first; this one reuses those
ideas and adds the proofs a library needs.

## How to read the code

| Kind | How to recognise it | What the tutorial does with it |
| --- | --- | --- |
| **Python and pytest** | `sqlite3`, `uuid`, `unittest.mock.patch` | Assumes you know it |
| **The library under test** | `tinyq` and `tinyq.testing` | Shows it in full; this is what you replace with your library |
| **An application on the library** | `welcome`, `reference_jobs` | Shown in full; this is what your users write |
| **pytest-obligation** | Imported from `pytest_obligation` | Explained before its first use, with a short comment in the code and a table after the block |

Bindings carry four labelled comments, `ARRANGE`, `REAL PRODUCTION`,
`EXTERNAL SEAM` and `OBSERVE`, which say what is test setup, what is the code
under test, what is a stand-in, and what proves the work happened.
pytest-obligation refuses to build a contract whose profile bindings lack them.

## The library

A job is a row. A worker **claims** the oldest due row: it marks it `running`
and stamps it with a fresh random **token** and a **lease** (a deadline). It
runs the task, then **settles** the row as `done` or failed, but only if the
row still carries its token:

```python
    def claim(self) -> tuple[int, uuid.UUID] | None:
        """Take the oldest due job: mark it running, with a fresh token and a lease."""
        token, now = uuid.uuid4(), self.clock()
        with self._transaction():
            row = self._execute(
                "UPDATE tinyq_jobs SET status = 'running', token = ?, lease_until = ? WHERE id = ("
                "SELECT id FROM tinyq_jobs WHERE status = 'ready' AND run_after <= ? ORDER BY id LIMIT 1) RETURNING id",
                (str(token), now + self.lease_seconds, now),
            ).fetchone()
        return None if row is None else (int(row[0]), token)

    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        """Settle a job as done, only if `token` still owns it."""
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET status = 'done', token = NULL, lease_until = NULL "
                "WHERE id = ? AND token = ? AND status = 'running'",
                (job_id, str(token)),
            ).rowcount
        return changed == 1
```

The rest of [`tinyq/__init__.py`](../../examples/task_queue_tutorial/tinyq/__init__.py):

| Method | What it does |
| --- | --- |
| `enqueue(task, *args, max_attempts=3)` | Inserts a job inside the caller's transaction, so it commits or rolls back with the application's writes |
| `due()` | The jobs a worker may claim now |
| `fail(job_id, token, error)` | Counts a failed attempt if `token` still owns the job: back to `ready` after `retry_delay`, or `failed` after the last attempt |
| `renew(job_id, token)` | Extends a long job's lease if `token` still owns it |
| `reclaim_expired()` | The sweep: jobs whose lease expired (their worker presumed dead) go back to `ready` |
| `work_once()` | One worker pass: claim, run the task, `complete` or `fail` |
| `_execute()`, `_transaction()` | Every SQL statement and every commit tinyq makes goes through these two |

The token is what makes a presumed-dead worker harmless. If worker A's lease
expires, the sweep returns the job, and worker B claims it with a new token,
then A waking up and calling `complete` with its old token changes nothing.
That technique is called [fencing](vocabulary.md#claim-lease-and-fencing-token).

## 1. Tell the harness where your commits are

Many of the proofs kill a worker right after one of its commits. pytest-obligation
never guesses where commits are; a **host** tells it. Your library is the right
place to answer that question once, so your users never have to. tinyq routes
all its SQL through `_execute` and all its commits through `_transaction`, and
[`tinyq/testing.py`](../../examples/task_queue_tutorial/tinyq/testing.py) hooks
both:

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
| `CommitWorker` | pytest-obligation | Counts commits. When asked to die after commit *k*, `committed()` raises `WorkerDied` there; afterwards `refuse_if_dead()` raises on every statement, because a dead process runs nothing more. |
| `tinyq_worker_killer` | Your library | The **worker killer** the host protocol asks for: given *k*, count tinyq's commits and die after the *k*-th. |
| `Host` | pytest-obligation | What only your framework knows. `production_packages` names the code under test; adding `"tinyq"` lets bindings that live inside your library count as production. |

Real integrations do the same at a lower level: `redis_host` hooks the Redis
client's commands, `django_host` hooks the database connection's commit, and
Due's `work_table_host` wraps `django_host` and adds its own publication
recorder.

## 2. Prove ownership, and find the unfenced settlement

Profile B, **bounded ownership**, asks: who owns a job right now, and what
happens when that owner dies? It is the part hand-written queues most often
get wrong, because every failure needs two workers to observe. The
`FencedOwnership` binding hands the proofs your real ownership operations:

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

| Field | What the proofs do with it |
| --- | --- |
| `make_claimable` | Create one claimable job, through the application's command |
| `claim` | Your claim; must return `(job id, token)`, or `None` when nothing is due |
| `fenced_write`, `other_fenced_writes` | **Every** write an owner can make. Each is proven to succeed under the current token and to be refused under a superseded one. |
| `renew_lease` | Your heartbeat, proven fenced the same way |
| `expire_lease` | Simulate the owner's death. tinyq's clock is injectable, so the binding just moves it past the lease. |
| `reclaim_stalled` | Your sweep, for one job: what it did, or `None` for nothing |
| `observe` | Optional, and worth giving: with it, an accepted write must change the job and a refused one must leave it untouched, not just return the right boolean |

From this one binding the harness generates twelve cases. Two check that the
binding really calls tinyq. Nine check behaviour: a claim is exclusive (twice
in sequence, and with two threads racing), reclaiming issues a new token, the
current token's writes and renewals are accepted, a stale token's writes and
renewals are refused, a live lease blocks the sweep, and an expired one permits
it. The last checks that giving a job back leaves its retry budget unspent; it
passes trivially here, because tinyq has no separate "give back" operation and
the binding does not declare one.

tinyq's first draft of settlement checked *which* job to settle but not *who*
was settling it. It is kept in
[`tinyq/draft.py`](../../examples/task_queue_tutorial/tinyq/draft.py):

```python
class DraftQueue(Queue):
    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET status = 'done', token = NULL, lease_until = NULL WHERE id = ?", (job_id,)
            ).rowcount
        return changed == 1
```

Against the draft, the stale-token proof fails:

```text
tinyq job ownership: fenced_write, other_fenced_writes['fail'] carrying a superseded token was
accepted. A slow worker that wakes up after its claim was reaped would corrupt the new owner's state
```

That is the procrastinate `finish_job` finding from the table above, in your
own library, caught before release. The fix is the `AND token = ?` you saw in
`complete`. [`tests/test_draft_finding.py`](../../examples/task_queue_tutorial/tests/test_draft_finding.py)
keeps the draft's finding as a test that passes only while the harness still
detects it.

## 3. The race a single-threaded test cannot see

After the token fix, one generated case still failed, and only sometimes:

```text
AssertionError: tinyq job ownership: a racing claim raised instead of losing cleanly:
[OperationalError('cannot commit - no transaction is active')]. Losing a claim race is an ordinary
outcome and must return None, not error. ...
```

`assert_claim_is_exclusive_across_connections` starts two threads at a barrier
and has both claim at once. tinyq let several worker threads share one SQLite
connection, and two transactions on one connection interleaved: one thread
committed the other's transaction, and the second commit found nothing to
commit. A worker would have crashed mid-claim. In 20 runs it failed once. That
is the nature of a race: it is rare, and it is real.

The fix was one line, a lock in `_transaction`:

```python
    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock, self.db:
            yield
```

Run the race proof on every CI build. One green run says little about a race;
many green runs over months are the evidence.

## 4. Prove the retry budget

Profile J, **job retry limits**, asks: does a failing job stop after its
budget, and stay stopped? `BoundedRetry` binds your selection and your worker
to a job whose dependency always fails:

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

The proofs check four things: your selection finds the job before every
attempt; every worker pass reaches the failing dependency exactly once (so an
attempt that never ran cannot count); the job becomes terminal exactly at
`max_executions`; and one more worker pass changes nothing and calls nothing.
`failure_attempt_count` is the positive control: it counts calls at the failing
dependency itself, so the proof cannot pass on bookkeeping alone.

## 5. The worker under crashes

The last piece is the worker itself as a [handoff](vocabulary.md#handoff): it
commits a claim, runs the task's effect, and commits a settlement.
`worker_history`, from pytest-obligation's task-queue helpers, turns one worker
pass into a crash history: enqueue a job, run `work_once`, and observe both what
tinyq recorded and what the task did.

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

`recover(queue)` is what a deployment runs after a crash: time passes beyond
the lease, the sweep returns expired jobs, and workers run until idle. tinyq's
queue is a table its workers poll, so there is no message to lose; the delivery
declares no `lose`, and the harness skips the lost-message history. For one job
whose task makes one external call, the harness runs:

| History | What happened |
| --- | --- |
| normal operation | Claim, task, `complete` |
| worker died after commit 1 | Died holding the claim; the sweep returned the job after its lease and another pass ran it |
| worker died after commit 2 | Died after settling; nothing left to do |
| worker died after external call 1 | Died after the task's effect, before settling; the sweep returned the job and **the task ran again** |

That last row is the important one, and it is not tinyq's to fix. Any queue
that survives worker death runs some tasks twice. Whether that is harmless
depends on the task, which is exactly why your users need these tests too.

## 6. Package it for your users

Everything so far was about tinyq. Here is the part that helps everyone who
builds on it: a function that returns a complete contract for one of the
user's tasks. The user supplies what only they know; tinyq supplies the rest.

```python
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
    ...  # builds the contract from the ownership, bounded_retry and worker_history bindings above
```

The body declares tinyq's answer for each of the ten profiles:

```python
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
```

| Profile | tinyq's answer | Why |
| --- | --- | --- |
| A automatic recovery | `Decline` | Workers poll the table; reclaiming a dead worker's job is B's job |
| B bounded ownership | `Claim` | Proven by the `ownership` binding |
| C crash ambiguity | `Decline` | tinyq is at-least-once by design |
| D durable retention | `NotApplicable` | tinyq deletes nothing |
| E, F | `NotApplicable` (via `settled_by_one_worker`, `the_obligation_is_the`) | One worker settles each job; the job row *is* the obligation |
| G, I | `Decline` (via `application_gate`, `application_admission`) | Readiness gates and atomic admission belong to the application's own commands, not the queue |
| H harmless replay | `Decline` (via `replay_safety_is_the_functions`) | Whether a rerun is safe is a property of each task, which the crash history tests |
| J job retry limits | `Claim` | Proven by the `bounded_retry` binding |

The helpers `settled_by_one_worker`, `the_obligation_is_the`,
`application_gate`, `application_admission` and `replay_safety_is_the_functions`
come from `pytest_obligation.integrations.task_queues`. They are the reasons
RQ's and django-tasks-db's contracts already give, so every task queue answers
those questions in the same words.

One design choice deserves a sentence: `adoption=Adoption.LEGACY if gaps else
Adoption.NEW_FEATURE`. A user can record a finding they cannot fix yet (a
strict expected failure) only by passing `handoff_gaps`; otherwise every case
must pass.

## 7. What your users write

The [`welcome`](../../examples/task_queue_tutorial/welcome/__init__.py) app signs
a user up and emails them in the background:

```python
@queue.task
def send_welcome_email(email: str) -> None:
    """The first version: every run sends another email."""
    mailer.send(email, key=None)


@queue.task
def send_welcome_email_once(email: str) -> None:
    """The fixed version: the provider drops a repeat of the same key."""
    mailer.send(email, key=f"welcome:{email}")


def sign_up(email: str, *, task: Callable[[str], None] = send_welcome_email) -> int:
    """Create the user and owe their welcome email in one transaction; return the email job's id."""
    with db:
        db.execute("INSERT INTO users(email) VALUES (?)", (email,))
        return queue.enqueue(task, email)
```

Its whole test setup is one host in `conftest.py`:

```python
# One host for the session: the application's packages, plus tinyq's own commit counting.
configure(tinyq_host({"reference_jobs", "welcome"}))
```

and one call to `task_contract`, from
[`tests/test_welcome_email.py`](../../examples/task_queue_tutorial/tests/test_welcome_email.py):

```python
def welcome_contract(
    name: str, task: Callable[[str], None], *, gaps: dict[str, str] | None = None
) -> ObligationContract:
    return task_contract(
        welcome.queue,
        name=name,
        # REAL PRODUCTION: the app's sign-up command, which enqueues the task in its own transaction.
        enqueue=lambda: sign_up_someone(task),
        # OBSERVE: how many welcome emails this user received; one successful run sends exactly one.
        effect=lambda job_id: MAILER.delivered.count(addresses[job_id]),
        expected=1,
        enqueue_failing=a_failing_welcome,
        failures=lambda _job_id: MAILER.failed_calls,
        max_attempts=3,
        # EXTERNAL SEAM: the email provider; the worker also dies right after each send.
        external_calls=(ExternalCall(FakeMailer, "send"),),
        fixtures=("fresh_welcome",),
        handoff_gaps=gaps,
    )


@due_work_contract_suite(welcome_contract("welcome email", welcome.send_welcome_email_once))
class TestWelcomeEmail:
    pass
```

`MAILER` is the test's email-provider stand-in, from `tests/email_provider.py`.
`sign_up_someone` signs up a new address for each history and remembers it, so
each history observes only its own user. That detail matters: an early version
of this file signed up the same address every time, and the harness refused
it, because normal operation observed one email the first time and two the
second. The check that normal operation repeats exactly is one of the
[positive controls](vocabulary.md#positive-control) that keep a green result
honest.

For those few lines, the user gets 25 generated cases, including every
ownership and retry proof run against *their* task, and the crash history of a
worker running *their* task. For the keyed version, all pass. For the first
version, the crash history finds what tinyq's documentation could only warn
about:

| History | Welcome emails received |
| --- | --- |
| normal operation | 1 |
| worker died after commit 1 | 1 |
| worker died after commit 2 | 1 |
| worker died after external call 1 | **2** |

The app records it as a strict expected failure until it is fixed:

```python
@due_work_contract_suite(
    welcome_contract(
        "first welcome email",
        welcome.send_welcome_email,
        gaps={"a worker runs the task": "a worker that dies after sending, before tinyq records it, sends it twice"},
    )
)
class TestFirstWelcomeEmail:
    pass
```

The day someone fixes `send_welcome_email`, that case passes, the strict
expected failure turns red, and the entry has to be deleted in the same change.

## 8. Keep your own suite honest

tinyq's own test,
[`tests/test_tinyq_guarantees.py`](../../examples/task_queue_tutorial/tests/test_tinyq_guarantees.py),
calls the same `task_contract` with a reference job that is safe to repeat. That
is deliberate: the contract your users rely on is the one your CI runs, so it
cannot drift from what you prove. RQ's own test suite does the same with
`rq.worker_contract`.

Keep the reference job replay-safe. Then any divergence in your suite is
tinyq's, not the task's.

## 9. Make sure every task is covered

A generated suite only covers the tasks someone wrote a contract for.
pytest-obligation can scan an application for the places it hands work off and
fail CI when one has no contract (`pytest-obligation check`, and
`--due-work-verify` to require that each declared contract actually ran). Be
aware of one limit: the scan recognises a fixed set of frameworks (Django's
`on_commit`, Celery, RQ, procrastinate, DBOS, Dramatiq and Django Tasks). For a
new library, your users can declare your enqueue function as a `bridge` in
their configuration, so each call to it counts as a handoff, and you can
contribute a site kind for your library upstream.

A library can also check enrollment itself. Due, for example, lists every
registered unit of work and fails unless each has exactly one collected suite
(`assert_complete_enrollment`). If your library keeps a registry, as tinyq's
`queue.tasks` is, the same check is a few lines.

## 10. Real integrations to copy

| To see | Read |
| --- | --- |
| A task-queue contract like `task_contract`, for a real queue | `pytest_obligation.integrations.rq.worker_contract`, `django_tasks.worker_contract`, `celery_worker.worker_contract` |
| A host built on a client library | `pytest_obligation.integrations.redis.redis_host` |
| A framework with no in-process worker to kill | `pytest_obligation.integrations.dbos` and [process histories](how-it-works.md#crash-histories): the harness kills a real child process at named points |
| A heavier user-facing layer, where the library derives the bindings from each registered unit of work | Due's [conformance guide](https://github.com/gigaverse-app/due/blob/main/package/docs/conformance.md): `effect_contract_suite`, `ProviderSeam` and `seam_examples` |
| How to probe someone else's framework and report what you find | The [upstream playbook](../../docs/upstream-playbook.md) |

## What you learned

| Name | Kind | Meaning |
| --- | --- | --- |
| `Host`, worker killer, `CommitWorker` | pytest-obligation | Tell the harness where your library commits; ship it so users never write one |
| `FencedOwnership` | pytest-obligation | Profile B: exclusive claims, rotating tokens, fenced writes and renewals, lease expiry |
| `assert_claim_is_exclusive_across_connections` | pytest-obligation | Two workers racing for one job, on two threads |
| `BoundedRetry` | pytest-obligation | Profile J: a failing job stops at its budget and stays stopped |
| `worker_history`, `TaskOutcome` | pytest-obligation | One worker pass as a crash history: what the queue recorded and what the task did |
| `settled_by_one_worker` and the other `task_queues` reasons | pytest-obligation | Standard answers a task queue gives for profiles it does not own |
| `task_contract` | Your library | The contract you ship: users supply enqueue, effect and expected outcome |
| `handoff_gaps`, `Adoption.LEGACY` | pytest-obligation | A user's finding, recorded as a strict expected failure until fixed |
