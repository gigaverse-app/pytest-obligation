"""The job tinyq's own test suite runs: deliver a message to an outbox, once per job.

A framework needs a reference task to test its worker with. This one is safe to
repeat (the outbox ignores a message it already holds), so any divergence the
harness finds belongs to tinyq, not to the task.
"""

import sqlite3

from tinyq import Queue
from tinyq.draft import DraftQueue

db = sqlite3.connect(":memory:", check_same_thread=False)
queue = Queue(db)


class Outbox:
    def __init__(self) -> None:
        self.messages: set[str] = set()
        self.calls = 0
        self.down = False

    def deliver(self, message: str) -> None:
        self.calls += 1
        if self.down:
            raise ConnectionError("the outbox is down")
        self.messages.add(message)


outbox = Outbox()


@queue.task
def deliver(message: str) -> None:
    outbox.deliver(message)


def owe_a_message(message: str, *, max_attempts: int = 3) -> int:
    """The application command: record the job in its own transaction, and return its id."""
    with db:
        return queue.enqueue(deliver, message, max_attempts=max_attempts)


# tinyq's first draft of settlement, on a queue of its own; the tutorial shows what the harness finds in it.
draft_db = sqlite3.connect(":memory:", check_same_thread=False)
draft_queue = DraftQueue(draft_db)


def owe_a_message_on_the_draft(message: str) -> int:
    with draft_db:
        return draft_queue.enqueue(deliver, message)
