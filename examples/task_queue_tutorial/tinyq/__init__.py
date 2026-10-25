"""tinyq: a deliberately small task queue on SQLite, written for the framework-author tutorial.

Jobs are rows. A worker claims a row with a lease and a fresh token, runs the
task, and settles the row only if it still holds that token. A sweep returns
rows whose lease expired to the queue, and a failing task is retried until its
attempts run out. That is the whole promise this tutorial tests.
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
CREATE TABLE IF NOT EXISTS tinyq_jobs (
    id INTEGER PRIMARY KEY, task TEXT NOT NULL, args TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready', attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
    token TEXT, lease_until REAL, run_after REAL NOT NULL DEFAULT 0, error TEXT
);
"""


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
        """Record a job in the caller's transaction (call it inside `with db:`): it commits or rolls back with them."""
        row = self._execute(
            "INSERT INTO tinyq_jobs(task, args, max_attempts) VALUES (?, ?, ?) RETURNING id",
            (function.__name__, json.dumps(args), max_attempts),
        ).fetchone()
        return int(row[0])

    def due(self) -> list[int]:
        """The jobs a worker may claim now."""
        rows = self._execute(
            "SELECT id FROM tinyq_jobs WHERE status = 'ready' AND run_after <= ? ORDER BY id", (self.clock(),)
        )
        return [job_id for (job_id,) in rows.fetchall()]

    def claim(self) -> tuple[int, uuid.UUID] | None:
        """Take the oldest due job: mark it running, with a fresh token and a lease."""
        token, now = uuid.uuid4(), self.clock()
        with self._transaction():
            row = self._execute(
                "UPDATE tinyq_jobs SET status = 'running', token = ?, lease_until = ? WHERE id = ("
                "SELECT id FROM tinyq_jobs WHERE status = 'ready' AND run_after <= ? ORDER BY id LIMIT 1) RETURNING id",
                (str(token), now + self.lease_seconds, now),
            ).fetchone()
        return None if row is None else (int(row[0]), token)

    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        """Settle a job as done, only if `token` still owns it."""
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET status = 'done', token = NULL, lease_until = NULL "
                "WHERE id = ? AND token = ? AND status = 'running'",
                (job_id, str(token)),
            ).rowcount
        return changed == 1

    def fail(self, job_id: int, token: uuid.UUID, error: BaseException) -> bool:
        """Count a failed attempt, only if `token` still owns the job: retry later, or stop after the last attempt."""
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET attempts = attempts + 1, error = ?, token = NULL, lease_until = NULL, "
                "status = CASE WHEN attempts + 1 >= max_attempts THEN 'failed' ELSE 'ready' END, run_after = ? "
                "WHERE id = ? AND token = ? AND status = 'running'",
                (repr(error), self.clock() + self.retry_delay, job_id, str(token)),
            ).rowcount
        return changed == 1

    def renew(self, job_id: int, token: uuid.UUID) -> bool:
        """Extend the lease of a long job, only if `token` still owns it."""
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET lease_until = ? WHERE id = ? AND token = ? AND status = 'running'",
                (self.clock() + self.lease_seconds, job_id, str(token)),
            ).rowcount
        return changed == 1

    def reclaim_expired(self) -> list[int]:
        """The sweep: return jobs whose worker stopped renewing its lease, presumed dead, to the queue."""
        with self._transaction():
            rows = self._execute(
                "UPDATE tinyq_jobs SET status = 'ready', token = NULL, lease_until = NULL "
                "WHERE status = 'running' AND lease_until < ? RETURNING id",
                (self.clock(),),
            ).fetchall()
        return [job_id for (job_id,) in rows]

    def work_once(self) -> bool:
        """One worker pass: claim a job, run its task, settle it. False when nothing was due."""
        claimed = self.claim()
        if claimed is None:
            return False
        job_id, token = claimed
        task, args = self._execute("SELECT task, args FROM tinyq_jobs WHERE id = ?", (job_id,)).fetchone()
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
        return self._execute("SELECT status FROM tinyq_jobs WHERE id = ?", (job_id,)).fetchone()[0]

    def state(self, job_id: int) -> tuple[str, int, float | None]:
        """Status, attempts used and lease deadline: what an operator's dashboard shows for a job."""
        return self._execute("SELECT status, attempts, lease_until FROM tinyq_jobs WHERE id = ?", (job_id,)).fetchone()

    # Every statement and every commit tinyq makes goes through these two methods.
    # tinyq.testing hooks them to count commits and to stop a "dead" worker.

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.db.execute(sql, parameters)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock, self.db:
            yield
