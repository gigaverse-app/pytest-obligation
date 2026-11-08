"""Carry each test's measured cost contracts to the controller, and optionally hold the baseline complete.

A baseline entry whose contract no test measures any more (a renamed capability,
a retired path) would otherwise stay forever. On a full run with
``--obligation-cost-baseline-complete``, such entries fail the session; with
``OBLIGATION_COST_BASELINE=update`` they are removed instead. A filtered run
measures only some contracts, so pass the flag only where every cost test runs.
"""

import os
from collections.abc import Generator
from typing import Any

import pytest

from pytest_obligation.costs import (
    COST_UPDATE_ENVIRONMENT,
    prune_cost_entries,
    stale_cost_entries,
    visited_contracts,
)

COMPLETE = "--obligation-cost-baseline-complete"
#: The report property naming one contract a test measured; xdist forwards it to the controller.
PROPERTY = "obligation_cost_contract"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, Any, None]:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    report.user_properties.extend((PROPERTY, contract) for contract in visited_contracts())


class CostCompleteness:
    """Collects every measured contract, then holds the baseline to having no unmeasured entry."""

    def __init__(self, config: pytest.Config) -> None:
        self.root = config.rootpath
        self.visited: set[str] = set()
        self.stale: list[str] = []
        self.incomplete = bool(config.getoption("collectonly") or config.getoption("numprocesses", default=None))
        self.finished = 0
        self.update_blocked = False

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        self.incomplete |= not report.passed

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self.incomplete |= bool(items)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.visited.update(str(value) for name, value in report.user_properties if name == PROPERTY)
        self.incomplete |= not report.passed
        if report.when == "teardown":
            self.finished += 1

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        stale = stale_cost_entries(self.root, self.visited)
        if not stale:
            return
        if os.environ.get(COST_UPDATE_ENVIRONMENT) == "update":
            # The flag declares full-suite intent; absence only proves retirement
            # after collection and execution completed. An empty successful
            # collection may deliberately retire the final cost test.
            complete = (
                not self.incomplete
                and self.finished == session.testscollected
                and session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED)
            )
            if complete:
                prune_cost_entries(self.root, stale)
            else:
                self.update_blocked = True
            return
        self.stale = stale
        if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if self.update_blocked:
            terminalreporter.line(
                "Cost baseline pruning skipped: requires a complete, unfiltered serial run.", yellow=True
            )
        if not self.stale:
            return
        terminalreporter.section("cost contracts: baseline entries no test measured", red=True)
        for contract in self.stale:
            terminalreporter.line(f"  - {contract}")
        terminalreporter.line(f"Remove them with {COST_UPDATE_ENVIRONMENT}=update and {COMPLETE} on a full run.")
