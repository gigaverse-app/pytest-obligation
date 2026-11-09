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
    COST_BASELINE,
    COST_UPDATE_ENVIRONMENT,
    prune_cost_entries,
    stale_cost_entries,
    visited_contracts,
)

COMPLETE = "--obligation-cost-baseline-complete"
#: The report property naming one contract a test measured; xdist forwards it to the controller.
PROPERTY = "obligation_cost_contract"
#: How to retire an entry when no run can prune it, e.g. a suite whose cost tests always skip somewhere.
MANUAL_REMOVAL = f"delete the entries from {COST_BASELINE} by hand"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, Any, None]:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    report.user_properties.extend((PROPERTY, contract) for contract in visited_contracts())


class CostCompleteness:
    """
    Collects every measured contract, then holds the baseline to having no unmeasured entry.

    Contract: contracts/pytest_obligation/_cost_plugin/cost_baseline/ replays Quint histories
    against these hooks. Change them and the model in the same pull request.
    """

    def __init__(self, config: pytest.Config) -> None:
        self.root = config.rootpath
        self.visited: set[str] = set()
        self.stale: list[str] = []
        # Why update mode may not prune, in the order first seen; empty means complete so far.
        self.causes: dict[str, None] = {}
        for option, cause in (
            ("collectonly", "--collect-only"),
            ("setuponly", "--setup-only/--setup-plan"),
            ("setupplan", "--setup-only/--setup-plan"),
            # --lf skips whole files through passed, empty collect reports, without deselecting.
            ("lf", "--lf"),
            ("numprocesses", "xdist"),
        ):
            if config.getoption(option, default=None):
                self.causes[cause] = None
        self.finished = 0
        self.passed_calls = 0
        self.update_blocked = False

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if not report.passed:
            self.causes["collection error or skipped module"] = None

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        if items:
            self.causes["deselected tests"] = None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.visited.update(str(value) for name, value in report.user_properties if name == PROPERTY)
        if report.skipped:
            self.causes["skipped or xfailed test"] = None
        elif report.failed:
            self.causes["failed test"] = None
        # A test body ran only if its call phase passed: --setup-only and --setup-plan report
        # setup and teardown alone. Teardowns still count, so an exit during teardown blocks too.
        if report.when == "call" and report.passed:
            self.passed_calls += 1
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
            completed = min(self.passed_calls, self.finished)
            if not self.passed_calls == self.finished == session.testscollected:
                self.causes[f"{completed} of {session.testscollected} collected tests ran to completion"] = None
            if session.exitstatus not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
                self.causes[f"exit status {int(session.exitstatus)}"] = None
            if self.causes:
                self.update_blocked = True
            else:
                prune_cost_entries(self.root, stale)
            return
        self.stale = stale
        if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        if self.update_blocked:
            terminalreporter.line(
                f"Cost baseline pruning skipped ({'; '.join(self.causes)}): it requires a complete, unfiltered "
                f"serial run. To retire an unmeasured contract anyway, {MANUAL_REMOVAL}.",
                yellow=True,
            )
        if not self.stale:
            return
        terminalreporter.section("cost contracts: baseline entries no test measured", red=True)
        for contract in self.stale:
            terminalreporter.line(f"  - {contract}")
        terminalreporter.line(
            f"Remove them with {COST_UPDATE_ENVIRONMENT}=update and {COMPLETE} on a full run, or {MANUAL_REMOVAL}."
        )
