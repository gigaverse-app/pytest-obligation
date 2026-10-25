"""tinyq: a deliberately small task queue on SQLite, written for the framework-author tutorial.

A job is a row in the `jobs` table. Its status moves ready -> running -> done,
or back to ready to retry, or to failed when its attempts run out. A worker
takes a job, runs its task, and records the result. If a worker dies, a sweep
gives its job back to the queue. That is the whole promise this tutorial tests.
"""

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, task TEXT NOT NULL, args TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL, run_after REAL NOT NULL DEFAULT 0,
    token TEXT, lease_until REAL, error TEXT
);
"""

DUE = "SELECT id FROM jobs WHERE status = 'ready' AND run_after <= ? ORDER BY id"
# A worker may change a job only while it is running and still carries the worker's token.
OWNED = "id = ? AND token = ? AND status = 'running'"


class Queue:
    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        lease_seconds: float = 30.0,
        retry_delay: float = 10.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db, self.lease_seconds, self.retry_delay, self.clock = db, lease_seconds, retry_delay, clock
        self.tasks: dict[str, Callable[..., Any]] = {}
        # Workers in several threads may share one connection; one transaction at a time on it.
        self._lock = threading.RLock()
        self.db.executescript(SCHEMA)

    def task(self, function: Callable[..., Any]) -> Callable[..., Any]:
        """Register a function as a task: `@queue.task`."""
        self.tasks[function.__name__] = function
        return function

    def enqueue(self, function: Callable[..., Any], *args: Any, max_attempts: int = 3) -> int:
        """Add a job. Call it inside `with db:`, so the job commits or rolls back with your own writes."""
        sql = "INSERT INTO jobs (task, args, max_attempts) VALUES (?, ?, ?) RETURNING id"
        return self._one(sql, function.__name__, json.dumps(args), max_attempts)

    def due(self) -> list[int]:
        """The jobs a worker may take now."""
        return self._column(DUE, self.clock())

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

    def fail(self, job_id: int, token: uuid.UUID, error: BaseException) -> bool:
        """Count a failed attempt, if the caller still owns the job: retry it later, or stop after the last one."""
        with self._transaction():
            row = self._row(f"SELECT attempts, max_attempts FROM jobs WHERE {OWNED}", job_id, str(token))
            if row is None:
                return False
            attempts, max_attempts = row[0] + 1, row[1]
            status = "failed" if attempts >= max_attempts else "ready"
            sql = "UPDATE jobs SET status = ?, attempts = ?, error = ?, token = NULL, run_after = ? WHERE id = ?"
            self._run(sql, status, attempts, repr(error), self.clock() + self.retry_delay, job_id)
        return True

    def renew(self, job_id: int, token: uuid.UUID) -> bool:
        """Extend a long job's lease, if the caller still owns it."""
        lease_until = self.clock() + self.lease_seconds
        with self._transaction():
            return self._run(f"UPDATE jobs SET lease_until = ? WHERE {OWNED}", lease_until, job_id, str(token)) == 1

    def reclaim_expired(self) -> list[int]:
        """The sweep: give back to the queue every job whose worker's lease ran out, presumed dead."""
        sql = "UPDATE jobs SET status = 'ready', token = NULL WHERE status = 'running' AND lease_until < ? RETURNING id"
        with self._transaction():
            return self._column(sql, self.clock())

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

    def run_until_idle(self) -> None:
        while self.work_once():
            pass

    def status(self, job_id: int) -> str:
        return self._one("SELECT status FROM jobs WHERE id = ?", job_id)

    def state(self, job_id: int) -> tuple[str, int, float | None]:
        """Status, attempts used and lease deadline: what an operator's dashboard shows for a job."""
        return self._row("SELECT status, attempts, lease_until FROM jobs WHERE id = ?", job_id)

    # Small helpers, so each method above reads as one SQL statement per step.

    def _one(self, sql: str, *parameters: Any) -> Any:
        row = self._execute(sql, parameters).fetchone()
        return None if row is None else row[0]

    def _row(self, sql: str, *parameters: Any) -> Any:
        return self._execute(sql, parameters).fetchone()

    def _column(self, sql: str, *parameters: Any) -> list[Any]:
        return [row[0] for row in self._execute(sql, parameters).fetchall()]

    def _run(self, sql: str, *parameters: Any) -> int:
        return self._execute(sql, parameters).rowcount

    # Every statement and every commit tinyq makes goes through these two methods.
    # tinyq.testing hooks them to count commits and to stop a "dead" worker.

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.db.execute(sql, parameters)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock, self.db:
            yield
