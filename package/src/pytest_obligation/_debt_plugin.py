"""Opt-in baseline enforcement before keyword/deselection filtering."""

from collections.abc import Callable
from fnmatch import fnmatch
from pathlib import Path
from typing import cast

import pytest

# pytest-global: Reuses the root guard's notion of a suite selected whole; a pure function over arguments, no setup.
from pytest_obligation.collection import requires_complete_suite

DebtMismatch = Callable[..., str | None]


def _collected_suites(config: pytest.Config, items: list[pytest.Item]) -> dict[type, pytest.Class]:
    patterns = config.getini("python_files")
    suites: dict[type, pytest.Class] = {}
    for item in items:
        cls = item.cls if isinstance(item, pytest.Function) else None
        if cls is None or cls in suites or not callable(getattr(cls, "__due_work_debt__", None)):
            continue
        node = item.getparent(pytest.Class)
        assert node is not None, f"{item.nodeid}: a generated suite method is collected outside its class"
        path = item.path.resolve()
        if not path.is_relative_to(config.rootpath) or not any(fnmatch(path.name, pattern) for pattern in patterns):
            continue
        if requires_complete_suite(config.args, path, cls.__name__):
            suites[cls] = node
    return suites


# pytest-global: An expected failure added or removed without its baseline entry must fail the run that collects the suite; pytest honours collection hooks only from plugins, a suite module cannot register one, and a conftest per adopter directory would attach the baseline to every test beneath it.
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]):
    selected = config.getoption("due_work_debt_baseline") or config.getini("due_work_debt_baseline")
    for cls, node in _collected_suites(config, items).items() if selected else ():
        mismatch = cast(DebtMismatch, cls.__due_work_debt__)(config.rootpath, baseline=Path(selected))
        if mismatch is not None:
            # Reported as this suite's collection error: once, although every xdist worker
            # collects it, and it fails the run like an import error in the module would.
            config.hook.pytest_collectreport(report=pytest.CollectReport(node.nodeid, "failed", mismatch, []))
    yield
