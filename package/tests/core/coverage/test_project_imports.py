"""Import discovery is shared within a scan, never across edited source snapshots."""

import ast
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from pytest_obligation.coverage import project as project_module
from pytest_obligation.coverage.project import Module, Project

from .builders import write_project


def test_nested_imports_walk_once_and_new_scan_sees_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write_project(
        tmp_path,
        {
            "shop/orders.py": "def place():\n    from helper import work\n",
            "helper.py": "def work():\n    from celery import shared_task\n",
        },
    )
    calls: Counter[str] = Counter()
    original = project_module.imported_names

    def recorded(tree: ast.Module, module: Module) -> Iterator[str]:
        calls[module.name] += 1
        yield from original(tree, module)

    monkeypatch.setattr(project_module, "imported_names", recorded)
    before = Project(config)
    assert "helper" in {module.name for module in before.reachable}
    assert "celery.shared_task" in before.frameworks
    assert calls and set(calls.values()) == {1}
    (tmp_path / "helper.py").write_text("def work():\n    from django.db import transaction\n")
    after = Project(config)
    assert "django.db.transaction" in after.frameworks
    assert "celery.shared_task" not in after.frameworks
