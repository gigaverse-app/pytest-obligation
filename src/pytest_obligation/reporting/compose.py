"""Compose one report from evidence files, as data: shared by the CLI and the trusted re-render."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.profiles.reporting import merge_reports

from .artifact import TestOutcome
from .inventory import ApplicationInventory
from .markdown import render


def safe_run_url(url: str) -> bool:
    return urlparse(url).scheme == "https" and not any(c in url for c in "()\r\n<>")


@dataclass(frozen=True)
class Evidence:
    """One run's merged evidence: the reports, why any of it is unavailable, and JUnit-classified skips."""

    reports: dict[str, SuiteCoverage]
    unavailable: str
    collected_skips: int | None


def merge_evidence(
    paths: Sequence[Path],
    *,
    expected_reports: int,
    test_outcome: TestOutcome,
    inventory: ApplicationInventory | None,
    problems: Sequence[str],
    junit: Sequence[Path] | None,
) -> Evidence:
    """Recompute verdicts from evidence files. ``junit`` is ``None`` when no JUnit input was requested."""
    reports: dict[str, SuiteCoverage] = {}
    problems = list(problems)
    skipped = test_outcome == "skipped" and expected_reports == 0
    if (not paths and not skipped) or (expected_reports and len(paths) != expected_reports):
        problems.append(f"Expected {expected_reports or 'at least one'} report(s); found {len(paths)}.")
    for path in paths:
        try:
            if path.stat().st_size > 10_000_000:
                raise ValueError("report exceeds 10 MB")
            incoming = TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes())
            if inventory is not None:
                # Older pytest import modes use only the file's module basename.
                # Resolve an unambiguous module/class suffix at the same suite
                # source. Static names may be unresolved; decorator/class line
                # numbers differ. Older reports without suite locations retain
                # the declared-name fallback.
                for key in list(incoming):
                    if key not in inventory.applications:
                        location = incoming[key].source
                        matches = [
                            identity
                            for identity, app in inventory.applications.items()
                            if identity.endswith("." + key)
                            and (
                                app.source.path == location.path
                                if location is not None and location.kind == "suite"
                                else app.name == incoming[key].name
                            )
                        ]
                        if len(matches) == 1:
                            suite = incoming.pop(key)
                            merge_reports(incoming, {matches[0]: suite})
            # Reuse the plugin's declaration checks and evidence merge. Missing or
            # incompatible shards must never turn a partial run into an all-green report.
            merge_reports(reports, incoming)
        except (OSError, ValidationError, ValueError, AssertionError) as error:
            # Preserve valid evidence; never print application input or exception messages.
            problems.append(f"A report could not be read or combined ({type(error).__name__}).")
    unavailable = " ".join(problems)
    collected_skips = None
    if junit is not None and inventory is not None and not unavailable:
        from xml.etree.ElementTree import ParseError

        from defusedxml.common import DefusedXmlException

        from .collected import skipped_tests

        junit_paths = list(junit)
        if len(junit_paths) < expected_reports or (not junit_paths and test_outcome != "skipped"):
            unavailable = "Expected JUnit reports are missing; skipped-test count is unknown."
        elif test_outcome in ("failure", "cancelled"):
            unavailable = "Test execution did not complete; unreported tests cannot be classified as skips."
        else:
            try:
                collected_skips = skipped_tests(inventory, junit_paths)
            except (OSError, ParseError, DefusedXmlException):
                unavailable = "JUnit evidence could not be read; skipped-test count is unknown."
    if unavailable:
        unavailable += " Check the JSON artifacts and pytest logs; available evidence is shown below."
    return Evidence(reports=reports, unavailable=unavailable, collected_skips=collected_skips)


def render_merged(
    evidence: Evidence,
    *,
    test_outcome: TestOutcome,
    inventory: ApplicationInventory | None,
    run_url: str,
    source: str,
    asset_ref: str,
    repository_url: str,
    revision: str,
    graphics: bool,
    timing: bool = True,
    own_text: bool = False,
) -> str:
    return render(
        evidence.reports,
        run_url=run_url,
        source=source,
        unavailable=evidence.unavailable,
        test_outcome=test_outcome,
        asset_ref=asset_ref,
        repository_url=repository_url,
        revision=revision,
        graphics=graphics,
        inventory=inventory,
        collected_skips=evidence.collected_skips,
        timing=timing,
        own_text=own_text,
    )


def render_evidence(
    paths: Sequence[Path],
    *,
    expected_reports: int,
    test_outcome: TestOutcome,
    inventory: ApplicationInventory | None,
    problems: Sequence[str],
    junit: Sequence[Path] | None,
    run_url: str,
    source: str,
    asset_ref: str,
    repository_url: str,
    revision: str,
    graphics: bool,
    own_text: bool = False,
) -> str:
    """Merge evidence files and render them: the trusted re-render's one call."""
    evidence = merge_evidence(
        paths,
        expected_reports=expected_reports,
        test_outcome=test_outcome,
        inventory=inventory,
        problems=problems,
        junit=junit,
    )
    return render_merged(
        evidence,
        test_outcome=test_outcome,
        inventory=inventory,
        run_url=run_url,
        source=source,
        asset_ref=asset_ref,
        repository_url=repository_url,
        revision=revision,
        graphics=graphics,
        own_text=own_text,
    )


def write_report(output: Path, body: str, inventory: ApplicationInventory | None) -> None:
    """Write the Markdown, the inventory beside it, and the job summary."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    if inventory is not None:
        output.with_suffix(".inventory.json").write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(body + "\n")
