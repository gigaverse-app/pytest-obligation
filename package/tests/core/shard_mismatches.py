"""Shards that disagree with an already merged report in exactly one way, shared by the report merge tests."""

from pytest_obligation.debt import DebtEntry
from pytest_obligation.profiles.coverage import (
    Assessment,
    CaseEvidence,
    ProfileCoverage,
    SourceLocation,
    SuiteCoverage,
)

#: Every way a shard can disagree with the merged report about what was expected.
MISMATCHES = ("family", "debt", "declaration", "case-set", "source", "assessment")
#: Whether the incompatible suite is the only one in the shard, or follows a compatible one and a new one.
LOCATIONS = ("same-suite", "later-suite")


def replay_profile() -> ProfileCoverage:
    return ProfileCoverage(
        title="Harmless Replay",
        assessment=Assessment(state="claimed"),
        cases={"first": CaseEvidence(family="replay"), "duplicate": CaseEvidence(family="replay")},
    )


def merged_suite() -> SuiteCoverage:
    return SuiteCoverage(name="effect", profiles={"H": replay_profile()})


def mismatched_shard(
    initial: SuiteCoverage, mismatch: str, location: str
) -> tuple[dict[str, SuiteCoverage], dict[str, SuiteCoverage]]:
    """Return ``(target, shard)``: passing evidence for ``initial``, with one suite disagreeing by ``mismatch``."""
    incoming = initial.model_copy(deep=True)
    for case in incoming.profiles["H"].cases.values():
        case.collected = case.selected = True
        case.outcomes = {phase: ["passed"] for phase in ("setup", "call", "teardown")}
    target = {"suite": initial}
    shard = {"suite": incoming}
    incompatible = incoming
    if location == "later-suite":
        target["later"] = initial.model_copy(deep=True)
        incompatible = incoming.model_copy(deep=True)
        shard["new"] = incoming.model_copy(deep=True)
        shard["later"] = incompatible
    else:
        assert location == "same-suite", location
    last = incompatible.profiles["H"].cases["duplicate"]
    if mismatch == "case-set":
        incompatible.profiles["H"].cases.pop("duplicate")
    elif mismatch == "source":
        incompatible.source = SourceLocation(path="different.py", line=1, kind="suite")
    elif mismatch == "family":
        last.family = "incompatible"
    elif mismatch == "debt":
        last.debt = DebtEntry(case="duplicate", kind="known-defect", reason="Reviewed finding.")
    elif mismatch == "declaration":
        last.declaration = "not applicable"
    elif mismatch == "assessment":
        incompatible.profiles["H"].assessment = Assessment(state="declined", because="Not claimed by this worker.")
    else:
        raise ValueError(f"unknown mismatch: {mismatch}")
    return target, shard
