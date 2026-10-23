"""Render report JSON as data without importing the application or its tests."""

import argparse
import glob
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.profiles.reporting import merge_reports
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
    parser.add_argument(
        "--test-outcome", choices=("success", "failure", "cancelled", "skipped", "unknown"), default="unknown"
    )
    args = parser.parse_args()
    if args.run_url and (urlparse(args.run_url).scheme != "https" or any(c in args.run_url for c in "()\r\n<>")):
        parser.error("run URL must be an HTTPS URL without Markdown delimiters")
    reports: dict[str, SuiteCoverage] = {}
    problems: list[str] = []
    paths = sorted(glob.glob(args.input, recursive=True))
    if not paths or (args.expected_reports and len(paths) != args.expected_reports):
        problems.append(f"Expected {args.expected_reports or 'at least one'} report(s); found {len(paths)}.")
    for source in paths:
        try:
            path = Path(source)
            if path.stat().st_size > 10_000_000:
                raise ValueError("report exceeds 10 MB")
            incoming = TypeAdapter(dict[str, SuiteCoverage]).validate_json(path.read_bytes())
            # Reuse the plugin's declaration checks and evidence merge. Missing or
            # incompatible shards must never turn a partial run into an all-green report.
            merge_reports(reports, incoming)
        except (OSError, ValidationError, ValueError, AssertionError) as error:
            # Preserve valid evidence; never print application input or exception messages.
            problems.append(f"A report could not be read or combined ({type(error).__name__}).")
    unavailable = " ".join(problems)
    if unavailable:
        unavailable += " Check the JSON artifacts and pytest logs; available evidence is shown below."
    body = render(
        reports,
        run_url=args.run_url,
        source=args.source,
        unavailable=unavailable,
        test_outcome=args.test_outcome,
        asset_ref=args.asset_ref,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(body + "\n")


if __name__ == "__main__":
    main()
