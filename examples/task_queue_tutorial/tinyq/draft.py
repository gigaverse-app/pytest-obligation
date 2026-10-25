"""tinyq's first draft of settling a job, kept so the tutorial can show what the harness finds in it.

It checks which job to settle, but not whether the worker settling it still owns it.
"""

import uuid

from tinyq import Queue


class DraftQueue(Queue):
    def complete(self, job_id: int, token: uuid.UUID) -> bool:
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET status = 'done', token = NULL, lease_until = NULL WHERE id = ?", (job_id,)
            ).rowcount
        return changed == 1

    def fail(self, job_id: int, token: uuid.UUID, error: BaseException) -> bool:
        with self._transaction():
            changed = self._execute(
                "UPDATE tinyq_jobs SET attempts = attempts + 1, error = ?, token = NULL, lease_until = NULL, "
                "status = CASE WHEN attempts + 1 >= max_attempts THEN 'failed' ELSE 'ready' END, run_after = ? "
                "WHERE id = ?",
                (repr(error), self.clock() + self.retry_delay, job_id),
            ).rowcount
        return changed == 1
