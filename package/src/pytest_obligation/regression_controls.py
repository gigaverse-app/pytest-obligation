"""Check that a behavioral proof can detect a specific, independently introduced regression."""

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from pytest_obligation.binding import callable_code, is_harness_owned
from pytest_obligation.gap_probes import assert_semantic_binding_is_production_bound
from pytest_obligation.helpers import Binding, BindingScopeError, entered_binding
from pytest_obligation.models import HarnessModel


class RegressionControl(HarnessModel):
    """A configured shared proof, declared as ``ExtraProof(run=RegressionControl(...))``.

    Each execution builds fresh production-bound profile evidence. The unchanged
    shared proof must pass, reject the selected production fault, then pass again.
    Application fault factories change production or provider seams, never the
    observer or expectation. ExtraProof owns collection, fixtures and reporting.
    """

    binding: Binding[Any]
    proof: Callable[[Any], None]
    regression: Callable[[], AbstractContextManager[object]]
    match: str

    def __call__(self) -> None:
        code = callable_code(self.proof)
        assert code is not None and is_harness_owned(code), "regression proof must be owned by the shared harness"

        def check() -> None:
            with entered_binding(self.binding) as binding:
                assert_semantic_binding_is_production_bound(binding)
                self.proof(binding)

        assert_detects_regression(check, regression=self.regression, match=self.match)


def assert_detects_regression(
    check: Callable[[], object],
    *,
    regression: Callable[[], AbstractContextManager[object]],
    match: str,
) -> None:
    """Check the baseline, require a specific regression failure, then check restoration.

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
    except BindingScopeError:
        raise
    except AssertionError as error:
        raise AssertionError(f"regression control baseline failed: {error}") from error
    detected = False
    with regression():
        # Catch only the proof itself: a failing setup or cleanup is not detection.
        try:
            check()
        except BindingScopeError:
            raise
        except AssertionError as error:
            if not pattern.search(str(error)):
                raise AssertionError(f"regression failed for an unrelated reason: {error}") from error
            detected = True
    assert detected, "the check did not detect the regression; strengthen the observation before claiming coverage"
    try:
        check()
    except BindingScopeError:
        raise
    except AssertionError as error:
        raise AssertionError(f"regression control restored baseline failed: {error}") from error
