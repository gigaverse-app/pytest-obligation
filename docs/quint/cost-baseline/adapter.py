"""Replay Quint events at the production pytest cost-hook boundary, without pruning policy here."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pytest_obligation import _cost_plugin
from pytest_obligation.costs import COST_BASELINE, COST_UPDATE_ENVIRONMENT, load_cost_baseline


class DeselectedItem(pytest.Item):
    def runtest(self) -> None:
        raise RuntimeError("a deselected trace input must never execute")


class Adapter:
    def __init__(self, root: Path, work: Path, mutant: str | None) -> None:
        self.work = work
        self.config: pytest.Config | None = None
        self.patches: list[Any] = []
        self.root = root
        if mutant == "unconditional-prune":

            def old_pruning(plugin: Any, session: pytest.Session) -> None:
                _cost_plugin.prune_cost_entries(
                    plugin.root, _cost_plugin.stale_cost_entries(plugin.root, plugin.visited)
                )

            self.patches.append(patch.object(_cost_plugin.CostCompleteness, "pytest_sessionfinish", old_pruning))
        elif mutant == "ignore-deselection":
            self.patches.append(patch.object(_cost_plugin.CostCompleteness, "pytest_deselected", lambda *args: None))
        elif mutant == "disable-retirement":
            self.patches.append(patch.object(_cost_plugin, "prune_cost_entries", lambda *args: None))
        elif mutant is not None:
            raise ValueError(mutant)
        self.patches.append(patch.dict(os.environ, {COST_UPDATE_ENVIRONMENT: "update"}))
        for replacement in self.patches:
            replacement.start()

    def reports(self, *, measured: bool = False, failed: bool = False) -> None:
        for phase in ("setup", "call", "teardown"):
            report = pytest.TestReport(
                nodeid="test_cost.py::test_cost",
                location=("test_cost.py", 1, "test_cost"),
                keywords={},
                outcome="failed" if failed and phase == "call" else "passed",
                longrepr="injected test failure" if failed and phase == "call" else None,
                when=phase,
                user_properties=[(_cost_plugin.PROPERTY, "required")] if measured else [],
            )
            self.plugin.pytest_runtest_logreport(report)

    def apply(self, event: dict[str, Any]) -> None:
        op = event["op"]
        if op == "init":
            ini = self.work / "pytest.ini"
            ini.write_text("[pytest]\n", encoding="utf-8")
            (self.work / COST_BASELINE).write_text(
                "costs:\n- contract: required\n  statements: {read: 1}\n- contract: retired\n  statements: {read: 1}\n",
                encoding="utf-8",
            )
            self.config = pytest.Config.fromdictargs({}, ["-c", str(ini), "--rootdir", str(self.work)])
            self.session = pytest.Session.from_config(self.config)
            self.plugin = _cost_plugin.CostCompleteness(self.config)
        elif op == "collectionError":
            self.plugin.pytest_collectreport(pytest.CollectReport("test_bad.py", "failed", "syntax error", []))
        elif op == "skipOrDeselect":
            self.reports()
            item = DeselectedItem.from_parent(self.session, name="deselected")
            self.plugin.pytest_deselected([item])
        elif op == "earlySuccessfulExit":
            self.reports()
        elif op == "testFailure":
            self.reports(failed=True)
        elif op in ("collectOnly", "distributedRun"):
            assert self.config is not None
            self.config.option.collectonly = op == "collectOnly"
            self.config.option.numprocesses = 2 if op == "distributedRun" else 0
            self.plugin = _cost_plugin.CostCompleteness(self.config)
            if op == "distributedRun":
                self.reports(measured=True)
        elif op == "completeRun":
            self.reports(measured=True)
        elif op == "finishUpdate":
            self.session.testscollected = event["collected"]
            self.session.exitstatus = event["status"]
            self.plugin.pytest_sessionfinish(self.session)
        elif op not in ("emptyCollection", "inspect"):
            raise ValueError(op)

    def observe(self) -> dict[str, Any]:
        return {
            "baseline": sorted(entry.contract for entry in load_cost_baseline(self.work).costs),
            "visited": sorted(self.plugin.visited),
            "finished": self.plugin.finished,
        }

    def close(self) -> None:
        if self.config is not None:
            self.config._ensure_unconfigure()
        for replacement in reversed(self.patches):
            replacement.stop()


def create(root: Path, work: Path, mutant: str | None = None) -> Adapter:
    return Adapter(root, work, mutant)
