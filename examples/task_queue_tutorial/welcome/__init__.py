"""An application built on tinyq: sign a user up, then email them a welcome message in the background."""

import sqlite3
from collections.abc import Callable
from typing import Protocol

from tinyq import Queue


class Mailer(Protocol):
    def send(self, to: str, *, key: str | None) -> None:
        """Send one email. A provider that honours `key` delivers once per key."""
        ...


db = sqlite3.connect(":memory:", check_same_thread=False)
db.executescript("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
queue = Queue(db)


class _Unconfigured:
    def send(self, to: str, *, key: str | None) -> None:
        raise RuntimeError("configure welcome.mailer with your email provider's client")


mailer: Mailer = _Unconfigured()  # replaced by the application's configuration, and by the tests


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
