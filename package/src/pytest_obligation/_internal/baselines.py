"""What every committed baseline file shares: optional YAML, one writer, LF endings."""

import os
from pathlib import Path
from typing import Any


def yaml_module(purpose: str) -> Any:
    """PyYAML, imported only when a baseline is read; importing contracts stays framework-free."""
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(f"{purpose} require pytest-obligation[debt]") from error
    return yaml


def refuse_concurrent_update(variable: str) -> str | None:
    """Why ``variable=update`` cannot run here: xdist workers would race to rewrite one file."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return f"{variable}=update rewrites one file; run it without xdist workers (-p no:xdist)"
    return None


def write_baseline(path: Path, text: str) -> None:
    """LF on every platform, so a Windows regeneration produces no line-ending diff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
