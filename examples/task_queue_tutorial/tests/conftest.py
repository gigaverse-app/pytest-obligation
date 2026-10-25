from collections.abc import Iterator

import pytest
import reference_jobs
import welcome
from providers import FakeMailer
from tinyq.testing import ManualClock, empty, tinyq_host

from pytest_obligation import configure

# One host for the session: the application's packages, plus tinyq's own commit counting.
configure(tinyq_host({"reference_jobs", "welcome"}))
reference_jobs.queue.clock = ManualClock()
reference_jobs.draft_queue.clock = ManualClock()
welcome.queue.clock = ManualClock()
welcome.mailer = FakeMailer()


@pytest.fixture
def fresh_reference_jobs() -> Iterator[None]:
    empty(reference_jobs.queue)
    reference_jobs.outbox.__init__()
    yield


@pytest.fixture
def fresh_welcome() -> Iterator[None]:
    empty(welcome.queue)
    welcome.mailer.__init__()
    yield
