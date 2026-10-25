"""Render report JSON as data without importing the application or its tests."""

import argparse
import glob
import re
from collections.abc import Sequence
from pathlib import Path

from pytest_obligation.reporting import badge, readme
from pytest_obligation.reporting.artifact import INVENTORY_UNAVAILABLE, RenderManifest, stage
from pytest_obligation.reporting.compose import merge_evidence, render_merged, safe_run_url, write_report
from pytest_obligation.reporting.inventory import ApplicationInventory, discover


def main(argv: Sequence[str] | None = None) -> None:
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
    parser.add_argument(
        "--readme",
        type=Path,
        help="Markdown document whose text between the pytest-obligation start and end markers becomes the report",
    )
    parser.add_argument(
        "--readme-source",
        default="",
        help="Source line for the document's copy, which leaves out run-specific times and links",
    )
    parser.add_argument("--badge", type=Path, help="shields.io endpoint JSON to write with the report's headline")
    parser.add_argument(
        "--stage-artifact",
        type=Path,
        help="Empty directory receiving the evidence this render used, under fixed names, for a trusted re-render",
    )
    args = parser.parse_args(argv)
    inventory = (
        discover(Path.cwd(), args.application_path, suite_decorators=args.suite_decorator)
        if args.application_path
        else None
    )
    if args.run_url and not safe_run_url(args.run_url):
        parser.error("run URL must be an HTTPS URL without Markdown delimiters")
    inventory_unavailable = False
    if args.inventory:
        try:
            collected = ApplicationInventory.model_validate_json(args.inventory.read_bytes())
            if not args.collection_revision or collected.revision != args.collection_revision:
                raise ValueError("Collection revision mismatch")
            inventory = collected
        except (OSError, ValueError):
            inventory_unavailable = True
    paths = [Path(path) for path in sorted(glob.glob(args.input, recursive=True))]
    junit = [Path(path) for path in sorted(glob.glob(args.junit_input, recursive=True))] if args.junit_input else None
    evidence = merge_evidence(
        paths,
        expected_reports=args.expected_reports,
        test_outcome=args.test_outcome,
        inventory=inventory,
        problems=[INVENTORY_UNAVAILABLE] if inventory_unavailable else [],
        junit=junit,
    )

    def rendered(*, run_url: str, source: str, revision: str, timing: bool = True) -> str:
        return render_merged(
            evidence,
            test_outcome=args.test_outcome,
            inventory=inventory,
            run_url=run_url,
            source=source,
            asset_ref=args.asset_ref,
            repository_url=args.repository_url,
            revision=revision,
            graphics=args.graphics,
            timing=timing,
        )

    body = rendered(run_url=args.run_url, source=args.source, revision=args.revision)
    write_report(args.output, body, inventory)
    if args.readme:
        try:
            # No run-specific times, run link or commit-pinned source links: the document changes only when
            # the evidence does.
            readme.update(args.readme, rendered(run_url="", source=args.readme_source, revision="", timing=False))
        except (OSError, ValueError) as error:
            parser.error(f"--readme {args.readme}: {error}")
    if args.badge:
        badge.write(
            args.badge, badge.badge(evidence.reports, unavailable=evidence.unavailable, test_outcome=args.test_outcome)
        )
    if args.stage_artifact:
        manifest = RenderManifest(
            expected_reports=args.expected_reports,
            test_outcome=args.test_outcome,
            graphics=args.graphics,
            # Only an immutable commit ever links sources, so nothing else needs to survive a re-render.
            revision=args.revision if re.fullmatch(r"[0-9a-fA-F]{40}", args.revision) else "",
            junit=junit is not None,
            inventory_unavailable=inventory_unavailable,
        )
        stage(args.stage_artifact, manifest, reports=paths, junit=junit or [], inventory=inventory, markdown=body)


if __name__ == "__main__":
    main()
