"""The report's headline as a shields.io endpoint badge.

shields.io renders any HTTPS JSON in this shape as a badge
(https://shields.io/badges/endpoint-badge), so a repository can commit the file the report
writes and show ``https://img.shields.io/endpoint?url=<raw URL of the file>``. The counts are
the report's own: a badge never says more than the report it summarizes.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field

from pytest_obligation.models import HarnessModel
from pytest_obligation.profiles.coverage import SuiteCoverage

from .artifact import TestOutcome
from .markdown import known_expected_failures, report_totals

LABEL = "pytest-obligation"


class Badge(HarnessModel):
    """A shields.io endpoint response."""

    schema_version: Literal[1] = Field(default=1, serialization_alias="schemaVersion")
    label: str = LABEL
    message: str
    color: Literal["brightgreen", "yellow", "orange", "red", "lightgrey"]


def badge(reports: dict[str, SuiteCoverage], *, unavailable: str, test_outcome: TestOutcome) -> Badge:
    """The headline: what passed, which failures were declared known defects, and anything worse."""
    if unavailable or not reports:
        return Badge(message="evidence unavailable", color="lightgrey")
    totals = report_totals(reports)
    known = known_expected_failures(reports)
    worse = {
        "failing": totals["failed"] - known,
        "rejected": totals["rejected"],
        "blocked": totals["blocked"],
    }
    parts = [f"{totals['passed']} passed"]
    parts += [f"{known} known defect{'s' if known != 1 else ''}"] if known else []
    parts += [f"{count} {kind}" for kind, count in worse.items() if count]
    if worse["failing"] or worse["rejected"] or test_outcome in ("failure", "cancelled"):
        color: Literal["brightgreen", "yellow", "orange", "red", "lightgrey"] = "red"
    elif worse["blocked"]:
        color = "orange"
    elif known:
        color = "yellow"
    else:
        color = "brightgreen"
    return Badge(message=" · ".join(parts), color=color)


def write(path: Path, value: Badge) -> bool:
    """Write ``value`` to ``path``; ``False`` when the file already held exactly this badge."""
    text = value.model_dump_json(by_alias=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True
