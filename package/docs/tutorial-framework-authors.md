# Prove your task library's guarantees, and give your users tests

[All tutorials](tutorials.md) · [Vocabulary](vocabulary.md)

You maintain a library that runs code in the background: a task queue, a job
scheduler, a workflow engine. Here is a moment your users will meet sooner or
later.

A user signs up. Your library is meant to send their welcome email in the
background. A worker picks up the job and starts sending, and at that moment a
deploy restarts the worker.

What should happen next? Most libraries promise three things, even if the
README puts them differently:

1. **The email still goes out.** A job is not lost because its worker died.
2. **A broken dependency is retried, then given up on.** If the email provider
   is down, the job is tried a few times and then marked failed, visibly. It
   does not retry forever, and it does not vanish.
3. **A worker that comes back late cannot undo the work of its replacement.**
   If the "dead" worker was only stuck and wakes up later, whatever it tries to
   record about the job is ignored.

These promises are hard to test with ordinary unit tests, which call each
function once, in one process, with nothing failing. The promises are about
what happens *between* functions: a worker dying halfway through a job, two
workers overlapping. pytest-obligation tests exactly that. It kills workers at
every point where your library saves something, makes dependencies fail on
purpose, and races two workers against each other, then checks the outcome.

There is a fourth thing only a library can do for its users. Promise 1 has a
price: a job whose worker died gets run again, so some tasks run twice. Whether
that is harmless depends on the task (writing a file twice is fine, sending an
email twice is not), and only your users know their tasks. You can hand them
tests that find out.

So this tutorial has two halves:

- **Prove your own promises**, against your library's real code.
- **Give your users tests** for their own tasks, ready-made, in a few lines.

The library you will test is `tinyq`, a deliberately small task queue in
[`examples/task_queue_tutorial`](../../examples/task_queue_tutorial). To run
everything in this tutorial:

```bash
git clone https://github.com/gigaverse-app/pytest-obligation.git
cd pytest-obligation
uv sync --all-packages --locked
cd examples/task_queue_tutorial
uv run --project ../.. --no-sync pytest
```

It should end with `75 passed, 1 xfailed`. If you have never used
pytest-obligation, [the multi-system tutorial](tutorial-many-systems.md) is the
gentler start; this one builds on the same ideas.

**How to read the code.** Names imported from `pytest_obligation` are the
library being taught; each is explained before it is used, with a short table
after the block. `tinyq` and `tinyq.testing` are the library under test, the
part you would replace with your own. `welcome` is an application built on
tinyq, the part your users write. Bindings carry four labelled comments,
`ARRANGE`, `REAL PRODUCTION`, `EXTERNAL SEAM` and `OBSERVE`, which say what is
test setup, what is the code under test, what stands in for an outside system,
and what proves the work happened.

## 1. Meet tinyq

tinyq keeps jobs as rows in one database table, `jobs`. Everything about a job
is in its `status`:

```text
             enqueue
                |
                v
   +-------> ready ---- a worker takes it ----> running ---- task succeeds ----> done
   |                                              |
   +--- task failed, attempts left ---------------+
   +--- worker's time ran out (presumed dead) ----+
                                                  +---- task failed, no attempts left ----> failed
```

A worker runs this loop, `work_once`, over and over:

<!-- fmt:off -->
```python
    def work_once(self) -> bool:
        """One worker pass: take a job, run its task, record the result. False when nothing was due."""
        claimed = self.claim()
        if claimed is None:
            return False
        job_id, token = claimed
        task, args = self._row("SELECT task, args FROM jobs WHERE id = ?", job_id)
        try:
            self.tasks[task](*json.loads(args))
        except Exception as error:
            self.fail(job_id, token, error)
        else:
            self.complete(job_id, token)
        return True
```
<!-- fmt:on -->

Take a job, run its task, record success or failure. The rest of
[`tinyq/__init__.py`](../../examples/task_queue_tutorial/tinyq/__init__.py) is
one small method per step, each one or two short SQL statements:

| Method | What it does |
| --- | --- |
| `enqueue(task, *args)` | Adds a job, inside the caller's own transaction, so it is saved together with the application's writes, or not at all |
| `claim()` | Takes the oldest job that is due and marks it `running` |
| `complete(...)` / `fail(...)` | Records the result. A failure goes back to `ready` for a later retry, or to `failed` when no attempts are left |
| `reclaim_expired()` | The **sweep**: puts `running` jobs whose worker seems to have died back to `ready` |
| `run_until_idle()` | Runs `work_once` until nothing is due |

The `token` passed around is for promise 3; step 5 explains it. You can follow
steps 2 to 4 without it.

## 2. What your users will write

Start with the end result. Here is an application built on tinyq,
[`welcome`](../../examples/task_queue_tutorial/welcome/__init__.py). It signs a
user up and emails them in the background:

```python
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

And here is its test, from
[`tests/test_welcome_email.py`](../../examples/task_queue_tutorial/tests/test_welcome_email.py).
`task_contract` is something tinyq ships for its users:

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

The user says three things: how to enqueue their task, how to see what it did,
and what that should be after one successful run. In return, pytest collects 25
test cases against their real task, covering every promise above, under worker
deaths, failing providers and racing workers:

```text
tests/test_welcome_email.py::TestWelcomeEmail: 25 passed
```

Everything below is how tinyq makes those few lines possible.

## 3. Promise 1: a job survives its worker dying

### The test, in plain words

Take one job and run one worker pass on it, many times over. The first time,
let it finish normally and note the outcome: the job is `done`, one email was
sent. Then repeat it, killing the worker at a different point each time: right
after each moment tinyq saves something, and right after each call to the
email provider. After each death, run what a real deployment would run (time
passes, the sweep returns the job, workers pick it up) and look again. Every
version must end like the normal one.

pytest-obligation calls each of these runs a **history**, and a step tested
this way a [handoff](vocabulary.md#handoff). It needs three things from you.

### What it needs: when your library saves something

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

### What it needs: how your library recovers

After a death, the harness runs what a deployment would run. For tinyq, that
is: wait out the lease, run the sweep, run the workers.

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

### What it needs: the step itself

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
message that could be lost on the way, and the delivery declares none.

### What the harness ran

For the welcome email, these are the histories, and what each one ended with:

| History | What happened | Status, emails |
| --- | --- | --- |
| normal operation | Nothing failed | `done`, 1 |
| worker died after commit 1 | Died right after taking the job; the sweep gave it back and another pass ran it | `done`, 1 |
| worker died after commit 2 | Died right after recording `done`; nothing left to do | `done`, 1 |
| worker died after external call 1 | Died right after the email left, before recording `done`; the job ran again | `done`, 1 with the keyed task, **2** with the first version |

Promise 1 holds: every history ends `done`. The last row is its price: the task
ran twice. The keyed task still sends one email, because the provider ignores a
repeated key. The first version sends two. That is not tinyq's to fix, and it
is exactly what your users' tests find (step 7).

## 4. Promise 2: a failing job stops after its last attempt

Make the email provider fail every time. tinyq should try the job
`max_attempts` times, then mark it `failed` and leave it alone. `BoundedRetry`
checks that against tinyq's real worker. You point each field at a piece of
tinyq or of the user's app:

| What the proof needs | What tinyq gives it |
| --- | --- |
| A job whose task always fails | the user's command, with the provider set to fail |
| The jobs a worker would take now | `queue.due` |
| One worker pass | `queue.work_once` |
| Wait until the retry is due | move tinyq's clock by `retry_delay` |
| Has the job given up? | `queue.status(job) == "failed"` |
| How often the failing dependency was really called | a counter on the provider stand-in |

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

The proof checks four things. The job is picked up before every attempt. Each
worker pass really reaches the failing provider, once. The job becomes `failed`
exactly at the last attempt. One more worker pass changes nothing and calls
nothing. Counting the calls at the provider itself is what keeps the proof
honest: a library that only *recorded* attempts without running them would
fail it.

## 5. Promise 3: a worker that comes back late changes nothing

### The problem

A database cannot tell a dead worker from a stuck one. So tinyq gives each
worker a deadline, and if the worker misses it, tinyq assumes it died and gives
the job to someone else. Usually the worker really did die. But consider:

```text
10:00:00  worker A takes job 7
10:00:05  A gets stuck (a long pause, a hung network call)
10:00:30  A's deadline passes; the sweep puts job 7 back
10:00:31  worker B takes job 7, and finishes it
10:00:40  A wakes up, and tries to record that job 7 failed
```

What should happen at 10:00:40? Nothing. Job 7 is B's now, and it is done.

tinyq handles this with two ideas:

- The deadline is the job's **lease**. Taking a job starts it; the sweep only
  touches jobs whose lease has passed.
- Each time a job is taken, it gets a fresh random **token**, and the worker
  keeps a copy. Every update a worker makes says "only if the job still has my
  token". At 10:00:40, job 7 has B's token, so A's update matches no row.

Shutting out a worker that has lost its right to act, even though it does not
know yet, is called [fencing](vocabulary.md#claim-lease-and-fencing-token). In
tinyq it is visible in `claim` and `complete`:

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

`OWNED` is the condition `id = ? AND token = ? AND status = 'running'`, shared
by every update a worker makes.

### The proof

`FencedOwnership` replays the 10:00 story, and its variations, against tinyq's
real methods. It has more fields than the other bindings, because there are
more operations whose ownership must hold. Each field just names one of your
methods:

| What the proof needs | tinyq's method |
| --- | --- |
| Create a job that can be taken | the application's own command |
| Take a job, returning its id and token | `claim` |
| Every update a worker can make | `complete`, `fail` |
| Extend a lease | `renew` |
| Make a worker "die": let its lease pass | move tinyq's clock past the lease |
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

From this one binding, the harness checks that:

- a job cannot be taken twice, in sequence or by two threads racing;
- when the sweep returns a job, the next worker gets a new token;
- the current owner's updates and lease renewals work;
- a previous owner's updates and renewals are refused, and change nothing;
- the sweep leaves a job alone while its lease runs, and takes it back after.

### What it found

tinyq's first draft of recording a result is kept in
[`tinyq/draft.py`](../../examples/task_queue_tutorial/tinyq/draft.py). It
checks *which* job to update, but not *who* is updating it:

```python
class DraftQueue(Queue):
    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        with self._transaction():
            return self._run("UPDATE jobs SET status = 'done' WHERE id = ?", job_id) == 1
```

Against the draft, the proof fails with the 10:00:40 story:

```text
tinyq job ownership: fenced_write, other_fenced_writes['fail'] carrying a superseded token was
accepted. A slow worker that wakes up after its claim was reaped would corrupt the new owner's state
```

This gap only shows when two workers overlap, so a single-threaded unit test
never sees it. The fix is the `OWNED` condition you saw in `complete`.
[`tests/test_draft_finding.py`](../../examples/task_queue_tutorial/tests/test_draft_finding.py)
keeps the finding as a test that passes only while the harness detects it.

The two-thread check found a second problem. tinyq lets several worker threads
share one database connection, and without care, two threads' transactions on
that connection interleave. Without a lock, the check failed on every one of 30
runs:

```text
AssertionError: tinyq job ownership: a racing claim raised instead of losing cleanly:
[OperationalError('cannot commit - no transaction is active')]. ...
```

The fix is one line: `_transaction` holds a lock while it runs.

## 6. Package it for your users

Steps 3 to 5 built three bindings. `task_contract` puts them together, so a
user only supplies what is about their own task:

<!-- fmt:off -->
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
    # Builds the contract from the ownership, bounded_retry and worker_history bindings above.
    ...
```
<!-- fmt:on -->

An **`ObligationContract`** is pytest-obligation's declaration of everything
to test about one piece of work. It asks ten standard questions, the
[profiles A to J](vocabulary.md#profiles-a-to-j), and wants an answer for each.
tinyq answers them once, for all its users:

| Question | tinyq's answer |
| --- | --- |
| B: who owns a job, and what happens when the owner dies? | **Claim**: proven by `ownership` (step 5) |
| J: does a failing job stop at its limit? | **Claim**: proven by `bounded_retry` (step 4) |
| A, C, D, E, F | Declined or not applicable, each with a one-line reason: workers poll the table, so no message can be lost; tinyq runs jobs at least once; it never deletes jobs; one worker records each result; the job row is the obligation |
| G, H, I | Declined: whether a task may run yet, whether it is safe to repeat, and whether it is enqueued together with the app's writes are questions about the user's code, which the crash history tests |

Reasons that apply to any task queue come ready-worded in
`pytest_obligation.integrations.task_queues` (`settled_by_one_worker`,
`the_obligation_is_the`, `replay_safety_is_the_functions`, `application_gate`,
`application_admission`), so different queues answer those questions the same
way.

## 7. Your users' side

Besides the contract from step 2, a user writes one `conftest.py`. The example
shares it with tinyq's own suite (the `reference_jobs` lines, see step 8):

```python
from collections.abc import Iterator

import pytest
import reference_jobs
import welcome
from email_provider import MAILER
from tinyq.testing import ManualClock, empty, tinyq_host

from pytest_obligation import configure

# One host for the session: the application's packages, plus tinyq's own commit counting.
configure(tinyq_host({"reference_jobs", "welcome"}))
# Clocks the tests move by hand, so leases expire and retries come due without waiting.
reference_jobs.queue.clock = ManualClock()
reference_jobs.draft_queue.clock = ManualClock()
welcome.queue.clock = ManualClock()
# The welcome app talks to the test's email stand-in instead of a real provider.
welcome.mailer = MAILER


@pytest.fixture
def fresh_reference_jobs() -> Iterator[None]:
    """Every generated case for tinyq's own suite starts from an empty queue and an empty outbox."""
    empty(reference_jobs.queue)
    reference_jobs.outbox.__init__()
    yield


@pytest.fixture
def fresh_welcome() -> Iterator[None]:
    """Every generated case for the welcome app starts from an empty queue and an empty mailbox."""
    empty(welcome.queue)
    MAILER.__init__()
    yield
```

The host comes from tinyq; the user never writes a worker killer. The manual
clock makes leases and retry delays pass instantly. `fresh_welcome` gives every
generated case an empty queue and mailbox; the contract asks for it by name
with `fixtures=`.

In the contract, `sign_up_someone` signs up a new address for every history
and remembers it, so each history counts only its own user's emails. That
detail matters. An early version of this file signed up the same address every
time, and pytest-obligation refused it, because a second normal run saw two
emails instead of one. Checking that normal operation repeats exactly is one of
the safeguards ([positive controls](vocabulary.md#positive-control)) that stop
a test from passing for the wrong reason.

The first version of the welcome task sends two emails after a death right
after sending (step 3). Until it is fixed, the app records that as a known
finding instead of hiding it:

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

The entry becomes a [strict expected failure](vocabulary.md#strict-expected-failure):
it passes while the problem exists and fails the day someone fixes the task, so
the entry has to be removed in the same change.

## 8. Keep your own suite honest, and cover every task

tinyq's own test,
[`tests/test_tinyq_guarantees.py`](../../examples/task_queue_tutorial/tests/test_tinyq_guarantees.py),
calls the same `task_contract` with a reference job that is safe to repeat. So
the contract your users rely on is the one your CI runs. Keep the reference job
replay-safe, and any problem the suite finds is the library's.

A generated suite only covers the tasks someone wrote a contract for.
`pytest-obligation check` scans an application for the places it hands work
off and fails when one has no contract. It recognises the common frameworks
(Django's `on_commit`, Celery, RQ, procrastinate, DBOS, Dramatiq, Django
Tasks). For a new library, users list your enqueue function under `bridges` in
their configuration, and you can contribute support upstream. If your library
keeps a registry of tasks, as tinyq's `queue.tasks` is, you can also check in
CI that every registered task has a suite.

## 9. Integrations to learn from

pytest-obligation has no stack of its own; its core takes plain Python
callables. It ships integrations that do what `tinyq.testing` does for several
libraries:

| Library | What its integration drives |
| --- | --- |
| RQ | A real worker pass, its maintenance and its retries, plus a `worker_contract` like `task_contract` |
| Celery | A real worker process, its publications and its hooks, plus a `worker_contract` |
| django-tasks-db | Its `db_worker` and its retention command, plus a `worker_contract` |
| procrastinate | Its worker, heartbeats and stalled-job reclaim |
| DBOS | The application's own startup, restarted after a real process death |
| Prefect | The real body of a flow |

For a heavier layer that derives most bindings from each registered unit of
work, see Due's [conformance guide](https://github.com/gigaverse-app/due/blob/main/package/docs/conformance.md)
(`effect_contract_suite`). To apply the harness to an existing project's code,
see the [upstream playbook](../../docs/upstream-playbook.md).

## What you learned

| Name | Kind | Meaning |
| --- | --- | --- |
| Host, worker killer, `CommitWorker` | pytest-obligation | Tell the harness when your library saves something; ship it so users never write one |
| `worker_history`, `CallableDelivery` | pytest-obligation | Promise 1: one worker pass under every death, then recovery |
| `BoundedRetry` | pytest-obligation | Promise 2: a failing job stops at its limit, and stays stopped |
| `FencedOwnership` | pytest-obligation | Promise 3: leases and tokens keep a late worker from changing anything |
| `ObligationContract`, profiles | pytest-obligation | One declaration with an answer to each standard question |
| `task_contract` | Your library | What you ship: users supply enqueue, effect and expected outcome |
| `handoff_gaps` | pytest-obligation | A user's known finding, kept as a strict expected failure until fixed |
