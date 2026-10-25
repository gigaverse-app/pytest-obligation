"""Teach pytest-obligation where this application's commits are, so it can kill a worker after each one.

pytest-obligation never guesses where your transactions end. A framework
integration (Django, MongoDB, Redis, ...) tells it; this plain-SQLite
application tells it with a connection class that reports every commit.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from pytest_obligation.worker_death import CommitWorker

# The worker the harness is currently counting, while a history's transition runs.
_current: CommitWorker | None = None


class CountedConnection(sqlite3.Connection):
    """A SQLite connection whose commits the harness can count and interrupt."""

    def execute(self, sql: str, parameters: object = (), /) -> sqlite3.Cursor:
        if _current is not None:
            _current.refuse_if_dead()
        return super().execute(sql, parameters)  # type: ignore[arg-type]

    def commit(self) -> None:
        if _current is not None:
            _current.refuse_if_dead()
        super().commit()
        if _current is not None:
            _current.committed()

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> bool:
        # `with connection:` commits in C, bypassing commit() above; route it through commit().
        if kind is None:
            self.commit()
        else:
            self.rollback()
        return False


@contextmanager
def sqlite_worker_killer(kill_after: int | None) -> Iterator[CommitWorker]:
    """The host's worker killer: count commits, and die right after commit `kill_after` (None: only count)."""
    global _current
    _current = CommitWorker(kill_after)
    try:
        yield _current
    finally:
        _current = None
