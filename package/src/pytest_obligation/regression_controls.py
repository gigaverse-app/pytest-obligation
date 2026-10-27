"""Check that a behavioral proof can detect a specific, independently introduced regression."""

import re
from collections.abc import Callable
from contextlib import AbstractContextManager


def assert_detects_regression(
    check: Callable[[], object],
    *,
    regression: Callable[[], AbstractContextManager[object]],
    match: str,
) -> None:
    """Run the same check clean, then with bad behavior, requiring its specific assertion.

    ``check`` must arrange fresh work on every call. For an existing known gap,
    use the pinned-outcome check, which passes on the baseline. ``regression``
    changes production behavior or an external dependency and restores it on
    exit; it must not alter the observer, expectation, or findings table.

    This establishes sensitivity only to the supplied regression. Context
    entry/exit errors, unrelated assertions and non-assertion exceptions never
    count as detection. A missing dependency is not a reproduced product bug.
    """
    if not match.strip():
        raise ValueError("match must identify the expected behavioral failure")
    pattern = re.compile(match)
    try:
        check()
    except AssertionError as error:
        raise AssertionError(f"regression control baseline failed: {error}") from error
    detected = False
    with regression():
        # Catch only the proof itself: a failing setup or cleanup is not detection.
        try:
            check()
        except AssertionError as error:
            if not pattern.search(str(error)):
                raise AssertionError(f"regression failed for an unrelated reason: {error}") from error
            detected = True
    assert detected, "the check did not detect the regression; strengthen the observation before claiming coverage"
