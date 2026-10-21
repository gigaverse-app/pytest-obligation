"""Require every generated case when collecting a complete contract class."""

from typing import Any

import pytest

from pytest_obligation.collection import assert_collected_proofs, requires_complete_suite


class CollectionCoverage:
    """Small pytest boundary; selected suites supply their own canonical expected cases."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.expected: dict[str, set[str]] = {}
        self.collected: dict[str, tuple[set[str], set[str]]] = {}

    def pytest_collectstart(self, collector: Any) -> None:
        if not isinstance(collector, pytest.Class):
            return
        required = getattr(collector.obj, "__obligation_required_cases__", None)
        if required is not None and requires_complete_suite(
            self.config.args, collector.path.resolve(), collector.obj.__name__
        ):
            self.expected[collector.nodeid] = required()

    def pytest_collectreport(self, report: Any) -> None:
        expected = self.expected.pop(report.nodeid, None)
        if expected is None or report.failed:
            return
        self.collected[report.nodeid] = (expected, {item.name for item in report.result})

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self) -> None:
        # Runtime integrations may first validate a richer inventory. Judge
        # the pre-filter class collection, so -k cannot hide a missing case.
        for suite, (expected, actual) in self.collected.items():
            try:
                assert_collected_proofs(expected, actual, suite)
            except AssertionError as error:
                raise pytest.UsageError(str(error)) from error
