"""Render report JSON as data without importing the application or its tests."""

import argparse
import glob
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.profiles.reporting import merge_reports
from pytest_obligation.reporting.inventory import ApplicationInventory, discover
from pytest_obligation.reporting.markdown import render


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON file or glob of shards from this run")
    parser.add_argument(
        "--expected-reports", type=int, default=0, help="Expected shard count; 0 disables count checking"
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", default="")
    parser.add_argument("--asset-ref", default="main")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--collection-revision", default="")
    parser.add_argument("--junit-input", default="")
    parser.add_argument("--graphics", action="store_true", help="Compose fixed themed glyphs in the Markdown report")
    parser.add_argument(
        "--application-path",
        action="append",
        default=[],
        help="Source file/directory to inventory without imports; repeat for multiple roots",
    )
    parser.add_argument(
        "--test-outcome", choices=("success", "failure", "cancelled", "skipped", "unknown"), default="unknown"
    )
    parser.add_argument(
        "--suite-decorator",
        action="append",
        default=[],
        help="Additional fully-qualified application wrapper to inventory without imports; repeat for multiple wrappers",
    )
    args = parser.parse_args()
    inventory = (
        discover(Path.cwd(), args.application_path, suite_decorators=args.suite_decorator)
        if args.application_path
        else None
    )
    if args.run_url and (urlparse(args.run_url).scheme != "https" or any(c in args.run_url for c in "()\r\n<>")):
        parser.error("run URL must be an HTTPS URL without Markdown delimiters")
    reports: dict[str, SuiteCoverage] = {}
    problems: list[str] = []
    if args.inventory:
        try:
            collected = ApplicationInventory.model_validate_json(args.inventory.read_bytes())
            if not args.collection_revision or collected.revision != args.collection_revision:
                raise ValueError("Collection revision mismatch")
            inventory = collected
        except (OSError, ValueError):
            problems.append("Collected test inventory is missing, invalid, or from a different revision.")
    paths = sorted(glob.glob(args.input, recursive=True))
    skipped = args.test_outcome == "skipped" and args.expected_reports == 0
    if (not paths and not skipped) or (args.expected_reports and len(paths) != args.expected_reports):
        problems.append(f"Expected {args.expected_reports or 'at least one'} report(s); found {len(paths)}.")
    for source in paths:
        try:
            path = Path(source)
            if path.stat().st_size > 10_000_000:
                raise ValueError("report exceeds 10 MB")
            incoming = TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes())
            if inventory is not None:
                # Older pytest import modes use only the file's module basename.
                # Resolve only an unambiguous module/class suffix with the same
                # declared application name; never merge merely similar names.
                for key in list(incoming):
                    if key not in inventory.applications:
                        matches = [
                            identity
                            for identity, app in inventory.applications.items()
                            if identity.endswith("." + key) and app.name == incoming[key].name
                        ]
                        if len(matches) == 1:
                            incoming[matches[0]] = incoming.pop(key)
            # Reuse the plugin's declaration checks and evidence merge. Missing or
            # incompatible shards must never turn a partial run into an all-green report.
            merge_reports(reports, incoming)
        except (OSError, ValidationError, ValueError, AssertionError) as error:
            # Preserve valid evidence; never print application input or exception messages.
            problems.append(f"A report could not be read or combined ({type(error).__name__}).")
    unavailable = " ".join(problems)
    collected_skips = None
    if args.junit_input and inventory is not None and not unavailable:
        from xml.etree.ElementTree import ParseError

        from defusedxml.common import DefusedXmlException

        from .collected import skipped_tests

        junit_paths = [Path(path) for path in sorted(glob.glob(args.junit_input, recursive=True))]
        if len(junit_paths) < args.expected_reports or (not junit_paths and args.test_outcome != "skipped"):
            unavailable = "Expected JUnit reports are missing; skipped-test count is unknown."
        elif args.test_outcome in ("failure", "cancelled"):
            unavailable = "Test execution did not complete; unreported tests cannot be classified as skips."
        else:
            try:
                collected_skips = skipped_tests(inventory, junit_paths)
            except (OSError, ParseError, DefusedXmlException):
                unavailable = "JUnit evidence could not be read; skipped-test count is unknown."
    if unavailable:
        unavailable += " Check the JSON artifacts and pytest logs; available evidence is shown below."
    body = render(
        reports,
        run_url=args.run_url,
        source=args.source,
        unavailable=unavailable,
        test_outcome=args.test_outcome,
        asset_ref=args.asset_ref,
        repository_url=args.repository_url,
        revision=args.revision,
        graphics=args.graphics,
        inventory=inventory,
        collected_skips=collected_skips,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    if inventory is not None:
        args.output.with_suffix(".inventory.json").write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(body + "\n")


if __name__ == "__main__":
    main()
