"""
Cloudflare's purge API as Wagtail's own CloudflareBackend reaches it, kept faithful with ``pytest_obligation.fakes``.

The demo's ``RecordingCDN`` replaces Wagtail's frontend-cache backend entirely, so
the backend's handling of a provider that refuses a purge never runs. Here
Wagtail's real ``CloudflareBackend`` runs and only its network call,
``requests.post`` to ``/zones/<id>/purge_cache``, is substituted. The fake keeps
two facts of Cloudflare's documented contract:

* a purge request carries at most 100 URLs on Free, Pro and Business plans
  (https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-single-file/);
* a throttled purge answers ``success: false`` with error code 1134, "Unable to
  purge, rate limit reached" (same page). The HTTP status of that reply is not
  documented; 429 is assumed. Wagtail reads only the body.

Cloudflare reports both in the response rather than by raising, so the fake
returns the refusal ``ProviderBoundary.call`` hands back as its reply.
"""

import json
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from unittest import mock

import requests
from django.test import override_settings
from django_tasks_db.models import DBTaskResult, DBTaskResultQuerySet
from wagtail.contrib.frontend_cache.backends import CloudflareBackend
from wagtail.contrib.frontend_cache.backends import cloudflare as cloudflare_backend_module
from wagtail.contrib.frontend_cache.tasks import purge_urls_from_cache_task

from pytest_obligation import ClassifiedFailure
from pytest_obligation.fakes import ProviderBoundary
from pytest_obligation.integrations.django_tasks import db_worker_once
from pytest_obligation.profiles.job_retry_limits import FailureClass

#: Cloudflare's documented per-request URL limit for Free, Pro and Business zones.
CLOUDFLARE_PURGE_LIMIT = 100
ZONE_ID = "demo-zone"
WAGTAIL_BACKEND = "wagtail.contrib.frontend_cache.backends.CloudflareBackend"


def _reply(status: int, body: dict[str, Any]) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(body).encode()
    return response


def rate_limited() -> requests.Response:
    """Cloudflare's documented purge rate-limit refusal (error 1134)."""
    return _reply(
        429,
        {
            "success": False,
            "errors": [{"code": 1134, "message": "Unable to purge, rate limit reached."}],
            "messages": [],
            "result": None,
        },
    )


def _too_many_files(_operation: str, size: int, limit: int) -> requests.Response:
    # Cloudflare documents the limit, not this error's code; Wagtail reads only the message.
    return _reply(
        400,
        {"success": False, "errors": [{"message": f"{size} files exceeds the maximum of {limit}"}], "result": None},
    )


class CloudflarePurgeAPI:
    """Cloudflare's purge_cache endpoint: which URLs it purged, and the requests it received."""

    def __init__(self) -> None:
        self.boundary = ProviderBoundary(
            request_limits={"purge_cache": CLOUDFLARE_PURGE_LIMIT}, limit_error=_too_many_files
        )
        self.purged: Counter[str] = Counter()

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str], timeout: float) -> requests.Response:
        assert url.endswith(f"/zones/{ZONE_ID}/purge_cache"), url
        files = json["files"]
        refused = self.boundary.call("purge_cache", files)
        if refused is not None:
            return cast(requests.Response, refused)
        self.purged.update(files)
        return _reply(200, {"success": True, "errors": [], "messages": [], "result": {"id": ZONE_ID}})


@contextmanager
def cloudflare_in_front(backend: str = WAGTAIL_BACKEND) -> Iterator[CloudflarePurgeAPI]:
    """Serve the demo site through ``backend`` with Cloudflare's API replaced by the faithful fake."""
    api = CloudflarePurgeAPI()
    cache = {"cloudflare": {"BACKEND": backend, "ZONEID": ZONE_ID, "BEARER_TOKEN": "demo-token"}}
    with (
        override_settings(WAGTAILFRONTENDCACHE=cache),
        mock.patch.object(cloudflare_backend_module.requests, "post", api.post),
    ):
        yield api


class _Refusals(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class CloudflareBackendThatFailsLoudly(CloudflareBackend):
    """
    The one change the positive control makes: a purge Cloudflare refused fails the task.

    Wagtail's backend logs a refusal to ``wagtail.frontendcache`` and returns, so
    the task ends successful and the URL keeps serving the old page. This
    subclass keeps every line of Wagtail's request and turns that log into an error.
    """

    def _purge_urls(self, urls: list[str]) -> None:
        refusals = _Refusals()
        cloudflare_backend_module.logger.addHandler(refusals)
        try:
            super()._purge_urls(urls)
        finally:
            cloudflare_backend_module.logger.removeHandler(refusals)
        if refusals.records:
            raise RuntimeError(f"Cloudflare refused the purge: {refusals.records[0].getMessage()}")


FAILS_LOUDLY_BACKEND = f"{__name__}.CloudflareBackendThatFailsLoudly"

URL = "http://localhost/opening-hours/"


@contextmanager
def cloudflare_rate_limit(backend: str = WAGTAIL_BACKEND) -> Iterator[ClassifiedFailure]:
    """
    A throttled purge, and what it must leave: a task that ended FAILED.

    django-tasks-db runs a task once, so a purge it cannot complete should at
    least end FAILED, where an operator or a later sweep can see it. Ending it
    SUCCESSFUL hides that the CDN still serves the old page.
    """
    # ARRANGE: a real purge task for one URL, enqueued as Wagtail's publish enqueues it.
    # REAL PRODUCTION: django-tasks-db's ready selection and db_worker run Wagtail's own CloudflareBackend.
    # EXTERNAL SEAM: only requests.post to Cloudflare is replaced, by a fake built on ProviderBoundary.
    # OBSERVE: the task's recorded status, Cloudflare's purge requests and what Cloudflare purged.
    with cloudflare_in_front(backend) as api:

        def make_failing() -> str:
            api.boundary.fail_next("purge_cache", rate_limited)
            return str(purge_urls_from_cache_task.enqueue([URL]).id)

        def status(identity: str) -> str:
            return DBTaskResult.objects.get(pk=identity).status

        yield ClassifiedFailure(
            name="Cloudflare purge rate limit",
            classification=FailureClass.TERMINAL,
            make_failing=make_failing,
            due_work=lambda: DBTaskResultQuerySet(model=DBTaskResult).ready().values_list("pk", flat=True),
            identity_of=str,
            run_once=db_worker_once(),
            advance_to_due=lambda _identity: None,
            # The task finished, whichever way it ended; the product outcome says which.
            is_terminal=lambda identity: status(identity) in ("SUCCESSFUL", "FAILED"),
            failure_attempt_count=lambda _identity: len(api.boundary.calls_to("purge_cache")),
            observe=lambda identity: (status(identity), dict(api.purged)),
            product_outcome=status,
            expected_product_outcome=lambda _identity: "FAILED",
        )


CLOUDFLARE_RATE_LIMIT_GAP = {
    "assert_failure_takes_its_declared_class": (
        "Wagtail's CloudflareBackend logs a throttled purge (Cloudflare error 1134) and returns, so django-tasks-db "
        "records the task SUCCESSFUL and nothing retries it: the CDN keeps serving the old page until its cache "
        "expires. CLOUDFLARE_WITH_THE_FIX shows the one change that passes"
    ),
}
