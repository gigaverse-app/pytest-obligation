"""The welcome app's view: tinyq's contract, bound to the app's own task in a dozen lines."""

from itertools import count

import welcome
from providers import FakeMailer
from tinyq.testing import task_contract

from pytest_obligation import ExternalCall, due_work_contract_suite

numbers = count(1)
# Which address each history's job emails, so every history observes only its own user.
addresses: dict[int, str] = {}


def sign_up_someone(task) -> int:  # noqa: ANN001 - one of the welcome app's tasks
    """ARRANGE: a new user per history, signed up through the application's own command."""
    email = f"user{next(numbers)}@example.com"
    job_id = welcome.sign_up(email, task=task)
    addresses[job_id] = email
    return job_id


def a_failing_welcome() -> int:
    welcome.mailer.down = True
    return sign_up_someone(welcome.send_welcome_email_once)


def welcome_contract(name: str, task, **gaps: str):  # noqa: ANN001, ANN201
    return task_contract(
        welcome.queue,
        name=name,
        enqueue=lambda: sign_up_someone(task),
        effect=lambda job_id: welcome.mailer.delivered.count(addresses[job_id]),
        expected=1,
        enqueue_failing=a_failing_welcome,
        failures=lambda _job_id: welcome.mailer.failed_calls,
        max_attempts=3,
        external_calls=(ExternalCall(FakeMailer, "send"),),
        fixtures=("fresh_welcome",),
        handoff_gaps=gaps or None,
    )


@due_work_contract_suite(welcome_contract("welcome email", welcome.send_welcome_email_once))
class TestWelcomeEmail:
    pass


FIRST_VERSION = welcome_contract(
    "first welcome email",
    welcome.send_welcome_email,
    **{"a worker runs the task": "a worker that dies after sending, before tinyq records the job done, sends it twice"},
)


@due_work_contract_suite(FIRST_VERSION)
class TestFirstWelcomeEmail:
    pass
