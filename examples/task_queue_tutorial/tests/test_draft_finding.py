"""The finding in tinyq's first draft: a worker that lost its job can still settle it."""

import pytest
import reference_jobs
from tinyq.testing import ownership

from pytest_obligation.profiles.bounded_ownership import assert_stale_token_is_rejected


def test_the_draft_lets_a_presumed_dead_worker_settle_a_job_it_no_longer_owns():
    binding = ownership(reference_jobs.draft_queue, enqueue=lambda: reference_jobs.owe_a_message_on_the_draft("hi"))
    with pytest.raises(AssertionError, match="carrying a superseded token was accepted"):
        assert_stale_token_is_rejected(binding)
