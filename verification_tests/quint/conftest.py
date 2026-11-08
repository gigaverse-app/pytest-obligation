"""The driver every maintained Quint contract under docs/quint/<topic>/ shares.

Each topic keeps its driver in adapter.py beside its manifest, exposing
create(root, work, mutant). The quint_adapter fixture loads that module and
returns the factory pytest-quint-connect calls once per history, so a new
contract needs only its manifest, its adapter and one quint_contract() line.
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pytest_quint_connect import HistoryContext


def _load_adapter(manifest: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"quint_adapter_{name.replace('-', '_')}", manifest.parent / "adapter.py"
    )
    assert spec is not None and spec.loader is not None, manifest
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


@pytest.fixture
def quint_adapter():
    loaded: dict[Path, ModuleType] = {}

    def start(context: HistoryContext) -> Any:
        manifest = context.contract.manifest
        if manifest not in loaded:
            loaded[manifest] = _load_adapter(manifest, context.contract.name)
        return loaded[manifest].create(context.contract.root, context.work_dir, context.mutant)

    return start
