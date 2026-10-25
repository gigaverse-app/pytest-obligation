# 5. An application on your library

[Previous: 4. The module you ship](framework-4-module.md) · [All chapters](tutorial-framework-authors.md#chapters) · [Vocabulary](vocabulary.md)

Now switch sides. You build an application on RQ, and your library's
maintainers shipped the module from chapter 4. This is what testing your
background work looks like.

## The application

[`welcome_rq`](../../examples/rq_tutorial/welcome_rq/__init__.py) signs a user
up and emails them in a background job:

```python
def send_welcome_email(email: str) -> None:
    """The first version: every run sends another email."""
    mailer.send(email, key=None)


def send_welcome_email_once(email: str) -> None:
    """The fixed version: the provider drops a repeat of the same key."""
    mailer.send(email, key=f"welcome:{email}")


def sign_up(email: str, *, job: Callable[[str], None] = send_welcome_email) -> str:
    """Create the user and enqueue their welcome email, with two retries; return the job's id."""
    users.append(email)
    return emails.enqueue(job, email, retry=Retry(max=2)).id
```

Ordinary RQ code. Nothing in it knows about tests.

## Its test setup

One `conftest.py`, from
[`tests/conftest.py`](../../examples/rq_tutorial/tests/conftest.py):

```python
from collections.abc import Iterator

import pytest
import welcome_rq
from email_provider import MAILER

from pytest_obligation import configure
from pytest_obligation.integrations.redis import redis_host

# The host: Redis writes are the commits a worker can die after, and their replies can be lost.
configure(redis_host(welcome_rq.connection, {"welcome_rq"}))
# The welcome app talks to the test's email stand-in instead of a real provider.
welcome_rq.mailer = MAILER


@pytest.fixture
def empty_redis() -> Iterator[None]:
    """Every generated case starts from an empty Redis database and an empty mailbox."""
    welcome_rq.connection.flushdb()
    MAILER.__init__()
    yield
    welcome_rq.connection.flushdb()
```

`MAILER` is a stand-in for the email provider, from
[`tests/email_provider.py`](../../examples/rq_tutorial/tests/email_provider.py).
It delivers every message unless it repeats a key it has seen, and counts
failed calls when it is set to be down.

## Its contract

From [`tests/test_welcome_email.py`](../../examples/rq_tutorial/tests/test_welcome_email.py):

```python
def welcome_contract(name: str, job: Callable[[str], None], **declared: object) -> ObligationContract:
    return job_contract(
        welcome_rq.connection,
        name=name,
        queue="emails",
        # REAL PRODUCTION: the app's sign-up command, which enqueues the job with RQ's Retry.
        enqueue=lambda: sign_up_someone(job),
        # OBSERVE: how many welcome emails this user received; one successful run sends exactly one.
        effect=lambda job_id: MAILER.delivered.count(addresses[job_id]),
        expected=TaskOutcome(status="finished", effect=1),
        enqueue_failing=a_failing_welcome,
        failures=lambda _job_id: MAILER.failed_calls,
        max_retries=2,
        # EXTERNAL SEAM: the email provider; the worker also dies right after each send.
        external_calls=(ExternalCall(FakeMailer, "send"),),
        fixtures=("empty_redis",),
        **declared,
    )


@due_work_contract_suite(welcome_contract("welcome email", welcome_rq.send_welcome_email_once))
class TestWelcomeEmail:
    pass
```

| Name | Comes from | What it does |
| --- | --- | --- |
| `job_contract` | The module RQ ships (`rq_testing`) | Everything from chapter 4: the application supplies only what is about its job |
| `sign_up_someone` | The application's test | Signs up a new address for each history, through the real `sign_up`, and remembers it, so each history counts only its own user's emails |
| `TaskOutcome(status="finished", effect=1)` | pytest-obligation | What RQ should record and what the job should have done: one email |
| `@due_work_contract_suite(...)` | pytest-obligation | Turns the empty class into a suite: pytest collects one case per proof |

pytest collects 25 cases from it, against the application's real job and a
real Redis:

```text
tests/test_welcome_email.py::TestWelcomeEmail: 24 passed, 1 xfailed
```

The expected failure is RQ's declared property from chapter 4, which the
application did not have to know about. The 24 passing cases include the
ownership and retry proofs from chapter 2, run against this job, and the crash
history from chapter 1, with all 52 histories ending in exactly one email.

## What the application learns about its own job

The first version of the job sent no deduplication key. Bound the same way,
its crash history diverges. Six of the 52 histories send the welcome email
twice:

| History | Emails |
| --- | --- |
| normal operation | 1 |
| worker died after commit 10 | **2** |
| worker died after commit 13 | **2** |
| worker died after external call 1 | **2** |
| the reply to commit 10 was lost | **2** |
| the reply to commit 13 was lost | **2** |
| the reply to commit 14 was lost | **2** |
| every other history | 1 |

In each of them, the email went out, the worker died or lost a reply before RQ
recorded the job as done, and RQ, being at-least-once, ran the job again. The
library behaved as designed. It was the job that was not safe to run twice,
and the fix (the deduplication key) belongs to the application.

Until the job is fixed, the application records the finding instead of hiding
it:

```python
@due_work_contract_suite(
    welcome_contract(
        "first welcome email",
        welcome_rq.send_welcome_email,
        handoff_gaps={
            "the worker runs a task": "a worker that dies after sending, before RQ records it, sends it twice"
        },
    )
)
class TestFirstWelcomeEmail:
    pass
```

The entry is a [strict expected failure](vocabulary.md#strict-expected-failure):
it passes while the problem exists and fails the day someone fixes the job.

This is the point of chapter 4. A library's documentation can only say "jobs
may run more than once; make them idempotent". A shipped contract tells each
application whether *its* job is, by running it through every failure the
library knows about.

## Making sure every job is covered

A suite covers only the jobs someone wrote a contract for.
`pytest-obligation check` scans an application for the places it hands work
off and fails when one has no contract. It recognises RQ's `enqueue` calls, as
well as Django's `on_commit`, Celery, procrastinate, DBOS, Dramatiq and Django
Tasks. For a library it does not know yet, applications list your enqueue
function under `bridges` in their configuration, and you can contribute
support upstream. If your library keeps a registry of tasks, a check that
every registered task has a suite is a few lines.

## Integrations to learn from

pytest-obligation has no stack of its own; its core takes plain Python
callables. These integrations are worked examples of the six pieces from
chapter 4:

| Library | What its integration drives |
| --- | --- |
| RQ | A real worker pass, its maintenance and its retries, and `worker_contract` |
| Celery | A real worker process, its publications and its hooks, and a `worker_contract` |
| django-tasks-db | Its `db_worker` and its retention command, and a `worker_contract` with its declared properties |
| procrastinate | Its worker, heartbeats and stalled-job reclaim |
| DBOS | The application's own startup, restarted after a real process death |
| Prefect | The real body of a flow |
| Due | A first-party layer that derives bindings from each registered unit of work |

To apply the harness to an existing project's code, see the
[upstream playbook](../../docs/upstream-playbook.md).

## What you learned

| Name | Kind | Meaning |
| --- | --- | --- |
| Host (`redis_host`), `worker_pass`, `maintenance_passes` | pytest-obligation's RQ integration | Where the library writes, one real worker pass, and recovery |
| `worker_history` | pytest-obligation | A worker pass under every death and lost reply, then recovery |
| `FencedOwnership`, `BoundedRetry` | pytest-obligation | Ownership that holds when a worker comes back late; retries that stop |
| Fault breakers, Hypothesis exploration | pytest-obligation | More histories from the same binding, and search for orderings nobody wrote down |
| `worker_contract` plus declared properties | The module you ship | The application supplies its job; the library supplies everything it knows about itself |
| `handoff_gaps` | pytest-obligation | An application's known finding, kept as a strict expected failure until fixed |
