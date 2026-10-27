"""One layout for the report artifact: staged beside a rendered report, read back to re-render it.

The ``publish`` action re-renders a fork's report in a trusted ``workflow_run`` job. There, every
file in the artifact is untrusted data: it is validated here, never imported or executed, and the
Markdown the fork rendered is never read back.
"""

import shutil
import stat
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError

from pytest_obligation.models import HarnessModel

from .inventory import ApplicationInventory

MANIFEST = "manifest.json"
MARKDOWN = "report.md"
INVENTORY = "inventory.json"
REPORTS = "reports"
JUNIT = "junit"
_MAX_MANIFEST = 64_000
_MAX_INVENTORY = 50_000_000
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 256
MAX_REPORT_BYTES = 10_000_000
MAX_JUNIT_BYTES = 10_000_000
INVENTORY_UNAVAILABLE = "Collected test inventory is missing, invalid, or from a different revision."
ARCHIVE_UNAVAILABLE = "The evidence archive is invalid or exceeds the publisher's safety limits."

TestOutcome = Literal["success", "failure", "cancelled", "skipped", "unknown"]


class RenderManifest(HarnessModel):
    """
    The render settings that are not evidence files; identity comes from the publisher, not here.

    Read by a publisher that can be an older or newer version than the report step that wrote it (a
    pull request's report step against the default branch's publisher, for one). So a field this
    version does not know is dropped, never interpreted: the producer controls every field anyway, so
    refusing extras protects nothing, while refusing the whole manifest loses the report. A change
    older publishers must not misread raises ``version`` instead, which they do refuse. A new field
    is optional, and :func:`stage` leaves it out while it holds its default, so older publishers
    that still refuse unknown fields read the manifest as before.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    version: Literal[1, 2] = 1
    expected_reports: int = Field(ge=0, le=100_000)
    test_outcome: TestOutcome
    graphics: bool
    revision: str = Field(default="", pattern=r"^([0-9a-fA-F]{40})?$")
    junit: bool = False
    inventory_unavailable: bool = False
    #: The report's lane title; the producer's text, so it is rendered as text and bounded.
    title: str = Field(default="", max_length=120)
    #: A requested lane was missing, stale or invalid. Survives trusted re-rendering.
    evidence_unavailable: bool = False


#: Fields added to version 1 after its first release: written only when set (see :class:`RenderManifest`).
_OPTIONAL_LATER = frozenset({"title", "evidence_unavailable"})


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
    unset = {name for name in _OPTIONAL_LATER if getattr(manifest, name) == RenderManifest.model_fields[name].default}
    (directory / MANIFEST).write_text(manifest.model_dump_json(indent=2, exclude=unset), encoding="utf-8")


def _regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _members(directory: Path, suffix: str) -> list[Path]:
    if directory.is_symlink() or not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix == suffix and _regular(path))


def extract_archive(archive: Path, destination: Path) -> None:
    """Validate the entire ZIP before writing; copy only the evidence layout into an empty directory.

    This runs inside the publisher's credential-free container. Metadata budgets are checked before
    decompression, and actual bytes are bounded too. Never use extractall on contributor input.
    """
    if not _regular(archive) or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError(ARCHIVE_UNAVAILABLE)
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > MAX_MEMBERS or sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
            raise ValueError(ARCHIVE_UNAVAILABLE)
        names: set[str] = set()
        selected: list[zipfile.ZipInfo] = []
        for member in members:
            name = member.filename
            path = PurePosixPath(name)
            mode = member.external_attr >> 16
            if (
                name in names
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or "\x00" in member.orig_filename
                or name.rstrip("/") != path.as_posix()
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                or member.flag_bits & 1
            ):
                raise ValueError(ARCHIVE_UNAVAILABLE)
            names.add(name)
            if member.is_dir():
                continue
            limit = None
            if name == MANIFEST:
                limit = _MAX_MANIFEST
            elif name == INVENTORY:
                limit = _MAX_INVENTORY
            elif len(path.parts) == 2 and path.parts[0] == REPORTS and path.suffix == ".json":
                limit = MAX_REPORT_BYTES
            elif len(path.parts) == 2 and path.parts[0] == JUNIT and path.suffix == ".xml":
                limit = MAX_JUNIT_BYTES
            if limit is not None:
                if member.file_size > limit:
                    raise ValueError(ARCHIVE_UNAVAILABLE)
                selected.append(member)
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            raise ValueError("archive destination must be empty")
        for member in selected:
            target = destination / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            # read(n) also bounds an entry whose declared size differs from its stream.
            with source.open(member) as stream:
                data = stream.read(member.file_size + 1)
            if len(data) != member.file_size:
                raise ValueError(ARCHIVE_UNAVAILABLE)
            target.write_bytes(data)


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
    if manifest.evidence_unavailable:
        problems.append("One or more requested CI evidence lanes were unavailable or incompatible.")
    inventory_path = directory / INVENTORY
    if inventory_path.exists() or inventory_path.is_symlink():
        try:
            if not _regular(inventory_path) or inventory_path.stat().st_size > _MAX_INVENTORY:
                raise ValueError("no regular inventory")
            inventory = ApplicationInventory.model_validate_json(inventory_path.read_bytes())
        except (OSError, ValueError, ValidationError):
            problems.append(INVENTORY_UNAVAILABLE)
    return StagedEvidence(
        manifest=manifest,
        reports=_members(directory / REPORTS, ".json"),
        junit=_members(directory / JUNIT, ".xml"),
        inventory=inventory,
        problems=problems,
    )
