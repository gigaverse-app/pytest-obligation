"""tinyq's first draft of recording a result, kept so the tutorial can show what the harness finds in it.

It checks which job it is updating, but not whether the caller still owns it.
"""

import uuid

from tinyq import Queue


class DraftQueue(Queue):
    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        with self._transaction():
            return self._run("UPDATE jobs SET status = 'done' WHERE id = ?", job_id) == 1

    def fail(self, job_id: int, token: uuid.UUID, error: BaseException) -> bool:
        with self._transaction():
            return self._run("UPDATE jobs SET status = 'ready', attempts = attempts + 1 WHERE id = ?", job_id) == 1
