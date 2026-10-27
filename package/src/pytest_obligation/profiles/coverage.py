"""
Derived profile evidence shared by native and work-table suites.

Declarations remain canonical in contract.py. This report projects only coverage
metadata and pytest outcomes; it never executes bindings or serializes domain data.
"""

from collections.abc import Iterator, Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, computed_field, model_validator

from pytest_obligation.debt import DebtEntry
from pytest_obligation.models import HarnessModel, MutableHarnessModel

from .failures import FailureEvidence

AssessmentState = Literal["claimed", "declined", "not applicable", "known gap", "not assessed"]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Assessment(HarnessModel):
    """A declaration decision, independent of whether any selected test passed."""

    state: AssessmentState = Field(description="The adopter’s explicit decision; not a test verdict.")
    because: str | None = Field(default=None, description="Reason for an unclaimed guarantee or family.")


class _ExecutedEvidence(MutableHarnessModel):
    """Read our own JSON while deriving every verdict from validated evidence."""

    @model_validator(mode="before")
    @classmethod
    def discard_stored_verdicts(cls, value: Any) -> Any:
        # INVARIANT: serialized verdicts are display metadata, never proof.
        # Ignore only this model's computed fields; unknown evidence stays an
        # error. Copy the mapping so nested validation does not mutate callers.
        if isinstance(value, Mapping):
            return {key: item for key, item in value.items() if key not in cls.model_computed_fields}
        return value


class CaseEvidence(_ExecutedEvidence):
    """Coverage of one generated case; a pass requires successful setup, call and teardown."""

    family: str = Field(description="Binding or history family that generated this case.")
    declaration: str | None = None
    debt: DebtEntry | None = Field(default=None, description="Declared expected failure, with its baseline ticket.")
    collected: bool = Field(default=False, description="Pytest collected this expected case before selection filters.")
    selected: bool = Field(default=False, description="The case survived pytest selection filters.")
    outcomes: dict[str, list[str]] = Field(
        default_factory=dict,
        description="All observed outcomes by pytest phase, including retries and distributed runs.",
    )
    failures: list[FailureEvidence] = Field(
        default_factory=list, description="Observed failures; diagnostic metadata is not proof."
    )
    durations: list[Seconds] = Field(default_factory=list, description="Observed phase seconds, including retries.")

    @computed_field
    @property
    def passed(self) -> bool:
        return self.declaration is None and self._completed("passed")

    @computed_field
    @property
    def declaration_recorded(self) -> bool:
        """Only a completed declaration call counts; setup skips and teardown errors do not."""
        return self.declaration is not None and self._completed("skipped")

    def _completed(self, call_outcome: str) -> bool:
        # A prior completed attempt cannot cover a failed or interrupted repeat.
        phases = ("setup", "call", "teardown")
        return (
            self.collected
            and self.selected
            and len({len(self.outcomes.get(phase, ())) for phase in phases}) == 1
            and all(
                self.outcomes.get(phase) and all(outcome == expected for outcome in self.outcomes[phase])
                for phase, expected in (("setup", "passed"), ("call", call_outcome), ("teardown", "passed"))
            )
        )


class ProfileCoverage(_ExecutedEvidence):
    """Named guarantee, independently assessed families, and evidence for its expected cases."""

    title: str = Field(description="Canonical A–J guarantee or a narrower selection/exemption scope.")
    assessment: Assessment
    families: dict[str, Assessment] = Field(default_factory=dict, description="Independent family coverage decisions.")
    cases: dict[str, CaseEvidence] = Field(
        default_factory=dict, description="Every expected behavioral proof, including uncollected or unselected cases."
    )

    @computed_field
    @property
    def verified(self) -> bool:
        """No inferred whole-profile success from a filtered run, omitted family or known failure."""
        return (
            self.assessment.state == "claimed"
            and all(family.state in ("claimed", "not applicable") for family in self.families.values())
            and bool(self.cases)
            and all(case.passed for case in self.cases.values())
        )


class SourceLocation(HarnessModel):
    path: str
    line: int = Field(ge=1)
    kind: Literal["contract setup", "suite"] = "suite"


class SuiteCoverage(_ExecutedEvidence):
    """Coverage scoped to a collected suite; absent/unimported suites are never certified."""

    name: str = Field(description="Adopter contract name; the report key identifies its collected suite class.")
    profiles: dict[str, ProfileCoverage]
    additional_cases: dict[str, CaseEvidence] = Field(
        default_factory=dict, description="Extra proofs and assessment checks outside profile behavioral cases."
    )
    source: SourceLocation | None = None
    session_seconds: Seconds | None = Field(
        default=None, description="Whole pytest session wall time; not per-suite latency."
    )
    exploration: dict[str, CaseEvidence] | None = Field(
        default=None, description="Optional generated Hypothesis scenario checks; None means not reported."
    )

    def case_groups(self) -> Iterator[dict[str, CaseEvidence]]:
        """All expected evidence, including checks without a profile claim."""
        yield self.additional_cases
        for letter in sorted(self.profiles):
            yield self.profiles[letter].cases

    @computed_field
    @property
    def verified(self) -> bool:
        """Verify the explicitly assessed scope, requiring at least one executed claim."""
        return (
            any(profile.verified for profile in self.profiles.values())
            and all(
                profile.verified or profile.assessment.state == "not applicable" for profile in self.profiles.values()
            )
            and all(case.passed or case.declaration_recorded for case in self.additional_cases.values())
        )
