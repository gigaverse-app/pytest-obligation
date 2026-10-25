"""
Wagtail's real Cloudflare backend against a faithful fake of Cloudflare's purge API.

The publishing contract's CDN is ``RecordingCDN``, which never refuses anything,
so it cannot show how Wagtail treats a CDN that does. This module runs Wagtail's
own ``CloudflareBackend`` over :class:`~demos.wagtail_tasks.cloudflare.CloudflarePurgeAPI`,
built from ``pytest_obligation.fakes``, and finds:

* **Request limit: conforming.** Wagtail chunks a purge into requests of 30
  URLs, inside Cloudflare's documented 100. The fake refuses a larger request,
  so a regression in that chunking would fail here: the mutation test proves it.
* **Rate limit: a finding.** When Cloudflare throttles a purge, Wagtail logs the
  refusal and returns. django-tasks-db records the task as successful, nothing
  retries it, and the CDN keeps serving the old page until its cache expires.
  ``WAGTAIL_PUBLISHING`` declares this as a gap on its classified failure; the
  contract below, with the one-line fix, is the positive control.
* **Acknowledgement: not applicable.** Cloudflare answers a purge with
  ``success: true`` and offers no status to read back, so there is nothing an
  implementation could verify. Profile C's ``acknowledged_effects`` binding is
  for APIs that do offer one (a task id, an invalidation status).
"""

import logging
from functools import partial
from unittest import mock

import pytest
from wagtail.contrib.frontend_cache.backends import CloudflareBackend
from wagtail.contrib.frontend_cache.tasks import purge_urls_from_cache_task

from pytest_obligation import (
    Claim,
    NotApplicable,
    ObligationContract,
    Profile,
    due_work_contract_suite,
)

from .cloudflare import (
    CLOUDFLARE_PURGE_LIMIT,
    FAILS_LOUDLY_BACKEND,
    cloudflare_in_front,
    cloudflare_rate_limit,
)

_CONTROL_SCOPE = "the positive control measures one classification; WAGTAIL_PUBLISHING declares this profile"

CLOUDFLARE_WITH_THE_FIX = ObligationContract(
    name="wagtail: a throttled Cloudflare purge, with its fix",
    transactional=True,
    profiles={
        **{profile: NotApplicable(_CONTROL_SCOPE) for profile in Profile},
        Profile.J: Claim(),
    },
    classified_failures={"Cloudflare purge rate limit": partial(cloudflare_rate_limit, FAILS_LOUDLY_BACKEND)},
)


@due_work_contract_suite(CLOUDFLARE_WITH_THE_FIX)
class TestCloudflareWithTheFix:
    """A refusal the backend raises instead of logging ends the task FAILED, so the classified failure passes."""


@pytest.mark.django_db
def test_wagtail_purges_stay_within_cloudflares_request_limit() -> None:
    urls = [f"http://localhost/page-{index}/" for index in range(CLOUDFLARE_PURGE_LIMIT * 2 + 1)]

    with cloudflare_in_front() as api:
        purge_urls_from_cache_task.call(urls)

    assert all(call.refused is None for call in api.boundary.calls)
    assert max(call.size or 0 for call in api.boundary.calls) <= CLOUDFLARE_PURGE_LIMIT
    assert set(api.purged) == set(urls)


@pytest.mark.django_db
def test_the_fake_catches_a_purge_over_the_limit(caplog: pytest.LogCaptureFixture) -> None:
    # Mutation: without its chunking, Wagtail's backend sends every URL in one request.
    urls = [f"http://localhost/page-{index}/" for index in range(CLOUDFLARE_PURGE_LIMIT + 1)]

    with (
        cloudflare_in_front() as api,
        mock.patch.object(CloudflareBackend, "CHUNK_SIZE", len(urls)),
        caplog.at_level(logging.ERROR, logger="wagtail.frontendcache"),
    ):
        purge_urls_from_cache_task.call(urls)

    assert [call.size for call in api.boundary.calls] == [len(urls)]
    assert api.boundary.calls[0].refused is not None
    assert not api.purged, "Cloudflare purged nothing from the refused request"
    assert "exceeds the maximum of 100" in caplog.text, "Wagtail only logs the refusal"
