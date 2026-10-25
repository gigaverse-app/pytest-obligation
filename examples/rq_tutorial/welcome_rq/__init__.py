"""An application built on RQ: sign a user up, then email them a welcome message in a background job."""

import os
from collections.abc import Callable
from typing import Protocol

from redis import Redis
from rq import Queue, Retry

connection = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
emails = Queue("emails", connection=connection)
users: list[str] = []


class Mailer(Protocol):
    def send(self, to: str, *, key: str | None) -> None:
        """Send one email. A provider that honours `key` delivers once per key."""
        ...


class _Unconfigured:
    def send(self, to: str, *, key: str | None) -> None:
        raise RuntimeError("configure welcome_rq.mailer with your email provider's client")


mailer: Mailer = _Unconfigured()  # replaced by the application's configuration, and by the tests


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
