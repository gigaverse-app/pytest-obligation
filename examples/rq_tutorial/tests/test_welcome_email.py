"""The welcome app's contract: the contract RQ ships, bound to the app's own job."""

from collections.abc import Callable
from itertools import count

import welcome_rq
from email_provider import MAILER, FakeMailer
from rq_testing import job_contract

from pytest_obligation import ExternalCall, ObligationContract, due_work_contract_suite
from pytest_obligation.integrations.task_queues import TaskOutcome

numbers = count(1)
# Which address each history's job emails, so every history observes only its own user.
addresses: dict[str, str] = {}


def sign_up_someone(job: Callable[[str], None]) -> str:
    """ARRANGE: a new user per history, signed up through the application's own command."""
    email = f"user{next(numbers)}@example.com"
    job_id = welcome_rq.sign_up(email, job=job)
    addresses[job_id] = email
    return job_id


def a_failing_welcome() -> str:
    """ARRANGE: a sign-up while the email provider is down."""
    MAILER.down = True
    return sign_up_someone(welcome_rq.send_welcome_email_once)


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
