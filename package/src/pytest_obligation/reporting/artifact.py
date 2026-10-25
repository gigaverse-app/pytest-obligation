"""One layout for the report artifact: staged beside a rendered report, read back to re-render it.

The ``publish`` action re-renders a fork's report in a trusted ``workflow_run`` job. There, every
file in the artifact is untrusted data: it is validated here, never imported or executed, and the
Markdown the fork rendered is never read back.
"""

import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from pytest_obligation.models import HarnessModel

from .inventory import ApplicationInventory

MANIFEST = "manifest.json"
MARKDOWN = "report.md"
INVENTORY = "inventory.json"
REPORTS = "reports"
JUNIT = "junit"
_MAX_MANIFEST = 64_000
_MAX_INVENTORY = 50_000_000
INVENTORY_UNAVAILABLE = "Collected test inventory is missing, invalid, or from a different revision."

TestOutcome = Literal["success", "failure", "cancelled", "skipped", "unknown"]


class RenderManifest(HarnessModel):
    """The render settings that are not evidence files; identity comes from the publisher, not here."""

    version: Literal[1] = 1
    expected_reports: int = Field(ge=0, le=100_000)
    test_outcome: TestOutcome
    graphics: bool
    revision: str = Field(default="", pattern=r"^([0-9a-fA-F]{40})?$")
    junit: bool = False
    inventory_unavailable: bool = False


@dataclass(frozen=True)
class StagedEvidence:
    """Evidence read back from a staged artifact; ``problems`` explain anything that could not be."""

    manifest: RenderManifest | None
    reports: list[Path] = field(default_factory=list)
    junit: list[Path] = field(default_factory=list)
    inventory: ApplicationInventory | None = None
    problems: list[str] = field(default_factory=list)


def stage(
    directory: Path,
    manifest: RenderManifest,
    *,
    reports: Sequence[Path],
    junit: Sequence[Path],
    inventory: ApplicationInventory | None,
    markdown: str,
) -> None:
    """Copy the evidence one render used under fixed names, so a reader never interprets a path."""
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError(f"artifact staging directory {directory} is not empty")
    for name, sources, suffix in ((REPORTS, reports, ".json"), (JUNIT, junit, ".xml")):
        (directory / name).mkdir()
        for index, source in enumerate(sources, start=1):
            target = directory / name / f"{index:04d}{suffix}"
            if source.is_file():
                shutil.copyfile(source, target)
            else:
                # An unreadable match stays counted, so the re-render reports it unreadable too.
                target.touch()
    if inventory is not None:
        (directory / INVENTORY).write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    (directory / MARKDOWN).write_text(markdown, encoding="utf-8")
    (directory / MANIFEST).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def _regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _members(directory: Path, suffix: str) -> list[Path]:
    if directory.is_symlink() or not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix == suffix and _regular(path))


def load(directory: Path) -> StagedEvidence:
    """Read a staged artifact as data. Anything missing or malformed becomes an explained problem."""
    manifest_path = directory / MANIFEST
    try:
        if directory.is_symlink() or not _regular(manifest_path) or manifest_path.stat().st_size > _MAX_MANIFEST:
            raise ValueError("no regular manifest")
        manifest = RenderManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValueError, ValidationError):
        # Never echo artifact content: it was written by the code under test.
        return StagedEvidence(
            manifest=None,
            problems=[
                "The evidence artifact has no valid render manifest; it was altered or written by another version."
            ],
        )
    inventory = None
    # A rejected collected inventory may still leave the statically discovered one in use.
    problems = [INVENTORY_UNAVAILABLE] if manifest.inventory_unavailable else []
    inventory_path = directory / INVENTORY
    if inventory_path.exists() or inventory_path.is_symlink():
        try:
            if not _regular(inventory_path) or inventory_path.stat().st_size > _MAX_INVENTORY:
                raise ValueError("no regular inventory")
            inventory = ApplicationInventory.model_validate_json(inventory_path.read_bytes())
        except (OSError, ValueError, ValidationError):
            problems[:] = [INVENTORY_UNAVAILABLE]
    return StagedEvidence(
        manifest=manifest,
        reports=_members(directory / REPORTS, ".json"),
        junit=_members(directory / JUNIT, ".xml"),
        inventory=inventory,
        problems=problems,
    )
