# 5. Ship the same for your library

[Previous: 4. First-party tests for your users: how Due does it](framework-4-due.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

tinyq is much smaller than Due, so its testing layer is too: one function,
`task_contract`, that puts chapters 1 and 2 together for one of the user's
tasks.

## task_contract

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

The user supplies what is about their task: how to enqueue it, how to see its
effect, what that effect should be, and how to make it fail. tinyq supplies
the rest, in an **`ObligationContract`**: pytest-obligation's declaration of
everything to test about one piece of work. A contract answers ten standard
questions, the [profiles A to J](vocabulary.md#profiles-a-to-j), and tinyq
answers them once for all its users:

| Question | tinyq's answer |
| --- | --- |
| B: who owns a job, and what happens when the owner dies? | **Claim**, proven by `ownership` (chapter 2) |
| J: does a failing job stop at its limit? | **Claim**, proven by `bounded_retry` (chapter 2) |
| A, C, D, E, F | Declined or not applicable, each with a one-line reason: workers poll the table, so no message can be lost; tinyq runs jobs at least once; it never deletes jobs; one worker records each result; the job row is the obligation |
| G, H, I | Declined: whether a task may run yet, whether it is safe to repeat, and whether it is enqueued together with the app's writes are questions about the user's code, which the crash history from chapter 1 tests |

Reasons that apply to any task queue come ready-worded in
`pytest_obligation.integrations.task_queues` (`settled_by_one_worker`,
`the_obligation_is_the`, `replay_safety_is_the_functions`, `application_gate`,
`application_admission`), so different queues answer those questions the same
way.

## What a user writes

The [`welcome`](../../examples/task_queue_tutorial/welcome/__init__.py) app
signs a user up and emails them in the background:

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

Its test, from
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

```text
tests/test_welcome_email.py::TestWelcomeEmail: 25 passed
```

25 cases against the user's real task: every ownership and retry proof from
chapter 2, and the crash history of a worker running *their* task.

The user's `conftest.py` configures tinyq's host, gives the queue a
`ManualClock` (so leases and retry delays pass instantly), points the app at
its email stand-in, and defines the `fresh_welcome` fixture the contract asks
for, which empties the queue and mailbox before every case. See
[`tests/conftest.py`](../../examples/task_queue_tutorial/tests/conftest.py).
`sign_up_someone` signs up a new address for each history, so each history
counts only its own user's emails; pytest-obligation refused an earlier
version that reused one address, because a second normal run saw two emails.

## What the user learns about their own task

The app's first version of the task sent no deduplication key:

```python
@queue.task
def send_welcome_email(email: str) -> None:
    """The first version: every run sends another email."""
    mailer.send(email, key=None)
```

Its crash history diverges where chapter 1 said it would: a worker that dies
right after sending, before tinyq records the job done, sends a second email
when the job runs again. Until the task is fixed, the app records that as a
known finding:

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
it passes while the problem exists and fails the day someone fixes the task.

This is what your library's documentation could only warn about ("tasks may
run more than once; make them idempotent"), turned into a test that tells each
user whether *their* task is.

## Keep your own suite honest, and cover every task

tinyq's own test,
[`tests/test_tinyq_guarantees.py`](../../examples/task_queue_tutorial/tests/test_tinyq_guarantees.py),
calls the same `task_contract` with a reference job that is safe to repeat. So
the contract your users rely on is the one your CI runs, and any problem it
finds is the library's.

A generated suite covers only the tasks someone wrote a contract for.
`pytest-obligation check` scans an application for the places it hands work
off and fails when one has no contract. It recognises the common frameworks
(Django's `on_commit`, Celery, RQ, procrastinate, DBOS, Dramatiq, Django
Tasks); for a new library, users list your enqueue function under `bridges` in
their configuration, and you can contribute support upstream. If your library
keeps a registry of tasks, as tinyq's `queue.tasks` is, an enrollment check
like Due's is a few lines.

## Integrations to learn from

pytest-obligation has no stack of its own; its core takes plain Python
callables. These integrations do for their libraries what `tinyq.testing` does
for tinyq:

| Library | What its integration drives |
| --- | --- |
| RQ | A real worker pass, its maintenance and its retries, plus a `worker_contract` like `task_contract` |
| Celery | A real worker process, its publications and its hooks, plus a `worker_contract` |
| django-tasks-db | Its `db_worker` and its retention command, plus a `worker_contract` |
| procrastinate | Its worker, heartbeats and stalled-job reclaim |
| DBOS | The application's own startup, restarted after a real process death |
| Prefect | The real body of a flow |
| Due | The full first-party layer from chapter 4 |

To apply the harness to an existing project's code, see the
[upstream playbook](../../docs/upstream-playbook.md).

## What you learned

| Name | Kind | Meaning |
| --- | --- | --- |
| Host, worker killer, `CommitWorker` | pytest-obligation | Tell the harness when your library saves something; ship it so users never write one |
| `worker_history`, `CallableDelivery` | pytest-obligation | A worker pass under every death, then recovery |
| `BoundedRetry`, `FencedOwnership` | pytest-obligation | Retries that stop, and ownership that holds when a worker comes back late |
| Fault breakers, Hypothesis exploration | pytest-obligation | More histories from the same binding, and search for orderings nobody wrote down |
| `ObligationContract`, profiles | pytest-obligation | One declaration with an answer to each standard question |
| `task_contract` | Your library | What you ship: users supply enqueue, effect and expected outcome |
| `handoff_gaps` | pytest-obligation | A user's known finding, kept as a strict expected failure until fixed |
