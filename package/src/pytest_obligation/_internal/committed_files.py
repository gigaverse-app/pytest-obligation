"""What every file the plugin writes for a repository to commit shares: optional YAML, one layout, LF endings."""

import os
from pathlib import Path
from types import ModuleType
from typing import TypeVar

from pydantic import BaseModel

_Baseline = TypeVar("_Baseline", bound=BaseModel)


def yaml_module(purpose: str) -> ModuleType:
    """PyYAML, imported only when a baseline is read; importing contracts stays framework-free."""
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(f"{purpose} require pytest-obligation[debt]") from error
    return yaml


def read_baseline(path: Path, model: type[_Baseline], *, purpose: str) -> _Baseline:
    """``path`` validated as ``model``; an absent file is the empty baseline."""
    if not path.is_file():
        return model()
    return model.model_validate(yaml_module(purpose).safe_load(path.read_text(encoding="utf-8")) or {})


def dump_yaml(document: object, *, purpose: str) -> str:
    """The one YAML layout every baseline file and its suggested entries use."""
    return yaml_module(purpose).safe_dump(document, sort_keys=False, allow_unicode=True, width=110)


def refuse_concurrent_update(variable: str) -> str | None:
    """Why ``variable=update`` cannot run here: xdist workers would race to rewrite one file."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return f"{variable}=update rewrites one file; run it without xdist workers (-p no:xdist)"
    return None


def write_committed(path: Path, text: str) -> None:
    """LF on every platform, so a Windows regeneration produces no line-ending diff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
