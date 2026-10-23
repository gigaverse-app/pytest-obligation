"""Render report JSON as data without importing the application or its tests."""

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from pytest_obligation.profiles.coverage import SuiteCoverage
from pytest_obligation.reporting.markdown import render


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", default="")
    parser.add_argument("--asset-ref", default="main")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument(
        "--test-outcome", choices=("success", "failure", "cancelled", "skipped", "unknown"), default="unknown"
    )
    args = parser.parse_args()
    if args.run_url and (urlparse(args.run_url).scheme != "https" or any(c in args.run_url for c in "()\r\n<>")):
        parser.error("run URL must be an HTTPS URL without Markdown delimiters")
    reports = {}
    unavailable = ""
    try:
        if args.input.stat().st_size > 10_000_000:
            raise ValueError("report exceeds 10 MB")
        reports = TypeAdapter(dict[str, SuiteCoverage]).validate_json(args.input.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        # Preserve a reviewable report even after collection crashes or schema mismatch.
        # Never print validation input, which can contain application values.
        unavailable = f"Report could not be read ({type(error).__name__}). Check the JSON artifact and pytest log."
    body = render(
        reports,
        run_url=args.run_url,
        source=args.source,
        unavailable=unavailable,
        test_outcome=args.test_outcome,
        asset_ref=args.asset_ref,
        repository_url=args.repository_url,
        revision=args.revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(body + "\n")


if __name__ == "__main__":
    main()
