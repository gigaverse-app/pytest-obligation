import sys
from pathlib import Path

import pytest

from tests.rq.fixtures import empty_redis as empty_redis

#: The cases that reclaim a job with a failure callback. RQ does not support Windows, and there the reclaim
#: fails inside RQ: StartedJobRegistry.cleanup runs the callback under UnixSignalDeathPenalty, which arms
#: SIGALRM, and Windows has no SIGALRM. Every other case runs on Windows too.
RECLAIMING_CASES = (
    "B-assert_fence_rotates_through_recovery",
    "B-assert_expired_lease_permits_reclaim",
    "B-assert_lease_renewal_is_fenced",
    "handoff-the worker runs a task-assert_crash_at_every_commit_converges",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(
        reason="RQ does not support Windows: StartedJobRegistry.cleanup runs a reclaimed job's failure callback "
        "under UnixSignalDeathPenalty, which arms SIGALRM, and Windows has no SIGALRM"
    )
    # The hook sees the whole session's items; only this directory's contract is RQ's.
    here = Path(__file__).parent.name
    for item in items:
        if item.path.parent.name == here and any(f"[{case}]" in item.nodeid for case in RECLAIMING_CASES):
            item.add_marker(skip)
