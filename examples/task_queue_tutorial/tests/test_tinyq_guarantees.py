"""tinyq's own suite: its contract with its worker, bound to the reference job."""

from itertools import count

import reference_jobs
from tinyq.testing import task_contract

from pytest_obligation import ExternalCall, due_work_contract_suite

numbers = count(1)
# Which message each history's job delivers, so every history observes only its own job.
messages: dict[int, str] = {}


def owe_a_new_message() -> int:
    """ARRANGE: a fresh message per history, owed through the application's own command."""
    message = f"message {next(numbers)}"
    job_id = reference_jobs.owe_a_message(message)
    messages[job_id] = message
    return job_id


def a_failing_job() -> int:
    reference_jobs.outbox.down = True
    return reference_jobs.owe_a_message("never delivered")


TINYQ = task_contract(
    reference_jobs.queue,
    name="tinyq reference job",
    enqueue=owe_a_new_message,
    effect=lambda job_id: messages[job_id] in reference_jobs.outbox.messages,
    expected=True,
    enqueue_failing=a_failing_job,
    failures=lambda _job_id: reference_jobs.outbox.calls,
    max_attempts=3,
    external_calls=(ExternalCall(reference_jobs.Outbox, "deliver"),),
    fixtures=("fresh_reference_jobs",),
)


@due_work_contract_suite(TINYQ)
class TestTinyq:
    pass
