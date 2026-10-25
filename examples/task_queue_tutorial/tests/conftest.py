from collections.abc import Iterator

import pytest
import reference_jobs
import welcome
from email_provider import MAILER
from tinyq.testing import ManualClock, empty, tinyq_host

from pytest_obligation import configure

# One host for the session: the application's packages, plus tinyq's own commit counting.
configure(tinyq_host({"reference_jobs", "welcome"}))
# Clocks the tests move by hand, so leases expire and retries come due without waiting.
reference_jobs.queue.clock = ManualClock()
reference_jobs.draft_queue.clock = ManualClock()
welcome.queue.clock = ManualClock()
# The welcome app talks to the test's email stand-in instead of a real provider.
welcome.mailer = MAILER


@pytest.fixture
def fresh_reference_jobs() -> Iterator[None]:
    """Every generated case for tinyq's own suite starts from an empty queue and an empty outbox."""
    empty(reference_jobs.queue)
    reference_jobs.outbox.__init__()
    yield


@pytest.fixture
def fresh_welcome() -> Iterator[None]:
    """Every generated case for the welcome app starts from an empty queue and an empty mailbox."""
    empty(welcome.queue)
    MAILER.__init__()
    yield
