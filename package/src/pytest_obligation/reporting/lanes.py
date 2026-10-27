"""Combine downloaded CI artifacts using the same validated evidence layout as publication.

Callers download artifacts from the intended run/attempt. A commit is a necessary
compatibility check, not authentication: uploaded evidence is always untrusted data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .artifact import TestOutcome, load
from .compose import merge_evidence


@dataclass(frozen=True)
class LaneInputs:
    reports: list[Path]
    junit: list[Path]
    expected_reports: int
    test_outcome: TestOutcome
    problems: list[str]


def combine_lanes(directories: Sequence[Path], *, revision: str, test_outcome: TestOutcome) -> LaneInputs:
    reports: list[Path] = []
    junit: list[Path] = []
    problems: list[str] = []
    expected = 0
    outcomes: set[TestOutcome] = {test_outcome}
    # Repeated paths commonly arise from download globs. Do not count their observations twice.
    for directory in dict.fromkeys(path.resolve() for path in directories):
        lane = load(directory)
        manifest = lane.manifest
        if manifest is None or not revision or manifest.revision != revision:
            problems.append("A requested CI evidence lane is missing, invalid, or from a different revision.")
            outcomes.add("unknown")
            continue
        outcomes.add(manifest.test_outcome)
        # Validate each lane's cardinality before flattening: excess files in
        # one job must never compensate for a missing shard in another.
        evidence = merge_evidence(
            lane.reports,
            expected_reports=manifest.expected_reports,
            test_outcome=manifest.test_outcome,
            inventory=None,
            problems=lane.problems,
            junit=None,
        )
        if evidence.unavailable:
            problems.append("A requested CI evidence lane is incomplete or incompatible.")
        reports.extend(lane.reports)
        junit.extend(lane.junit)
        expected += manifest.expected_reports or len(lane.reports)
    # A successful lane cannot hide a failed/cancelled/unknown peer.
    priority: tuple[TestOutcome, ...] = ("failure", "cancelled", "unknown", "success", "skipped")
    outcome = next(value for value in priority if value in outcomes)
    return LaneInputs(reports, junit, expected, outcome, problems)
