"""Re-render a staged report artifact for a trusted publisher, from its evidence data alone.

The ``publish`` action runs this in a ``workflow_run`` job holding a write token, on an artifact
uploaded by a pull request's own code. The run identity comes from the GitHub API through the
arguments; the artifact supplies only evidence, validated as data. Its rendered Markdown is never
read, so every escaping decision belongs to this revision of the reporter.
"""

import argparse
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from pytest_obligation.reporting.artifact import ARCHIVE_UNAVAILABLE, StagedEvidence, extract_archive, load
from pytest_obligation.reporting.compose import render_evidence, safe_run_url, write_report


def _commit(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a 40-character commit SHA")
    return value


def _positive(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return int(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="Downloaded artifact staged by the report action")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--head-sha", type=_commit, required=True, help="The triggering run's PR head, from the API")
    parser.add_argument("--run-id", type=_positive, required=True)
    parser.add_argument("--run-attempt", type=_positive, required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--asset-ref", default="main")
    args = parser.parse_args(argv)
    if args.run_url and not safe_run_url(args.run_url):
        parser.error("run URL must be an HTTPS URL without Markdown delimiters")
    # Keep extracted paths alive until rendering completes; no artifact path becomes an import.
    with TemporaryDirectory(prefix="obligation-evidence-") as temporary:
        if args.artifact.is_file():
            try:
                directory = Path(temporary)
                extract_archive(args.artifact, directory)
                evidence = load(directory)
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
                evidence = StagedEvidence(manifest=None, problems=[ARCHIVE_UNAVAILABLE])
        else:
            evidence = load(args.artifact)
        _render(args, evidence)


def _render(args: argparse.Namespace, evidence: StagedEvidence) -> None:
    manifest = evidence.manifest
    body = render_evidence(
        evidence.reports,
        expected_reports=manifest.expected_reports if manifest else 0,
        test_outcome=manifest.test_outcome if manifest else "unknown",
        inventory=evidence.inventory,
        problems=evidence.problems,
        junit=evidence.junit if manifest and manifest.junit else None,
        run_url=args.run_url,
        source=f"PR head {args.head_sha} · run {args.run_id} · attempt {args.run_attempt}",
        asset_ref=args.asset_ref,
        repository_url=args.repository_url,
        # The source link is anchored to the API-verified PR head. A producer's revision is only a claim.
        revision=args.head_sha,
        graphics=manifest.graphics if manifest else False,
    )
    write_report(args.output, body, evidence.inventory)


if __name__ == "__main__":
    main()
