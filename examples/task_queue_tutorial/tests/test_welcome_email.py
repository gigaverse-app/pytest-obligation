"""The welcome app's view: tinyq's contract, bound to the app's own task in a few lines."""

from collections.abc import Callable
from itertools import count

import welcome
from email_provider import MAILER, FakeMailer
from tinyq.testing import task_contract

from pytest_obligation import ExternalCall, ObligationContract, due_work_contract_suite

numbers = count(1)
# Which address each history's job emails, so every history observes only its own user.
addresses: dict[int, str] = {}


def sign_up_someone(task: Callable[[str], None]) -> int:
    """ARRANGE: a new user per history, signed up through the application's own command."""
    email = f"user{next(numbers)}@example.com"
    job_id = welcome.sign_up(email, task=task)
    addresses[job_id] = email
    return job_id


def a_failing_welcome() -> int:
    """ARRANGE: a sign-up while the email provider is down."""
    MAILER.down = True
    return sign_up_someone(welcome.send_welcome_email_once)


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


@due_work_contract_suite(
    welcome_contract(
        "first welcome email",
        welcome.send_welcome_email,
        gaps={"a worker runs the task": "a worker that dies after sending, before tinyq records it, sends it twice"},
    )
)
class TestFirstWelcomeEmail:
    pass
