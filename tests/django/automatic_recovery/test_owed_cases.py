"""Exercise the public declaration all the way through generated PostgreSQL cases."""

from datetime import timedelta
from typing import Any

import pytest

from pytest_obligation import (
    Adoption,
    Claim,
    NotApplicable,
    ObligationContract,
    ObligationContractDesignError,
    Profile,
    ScheduledSelection,
    contract_cases,
    scheduled_selection_cases,
)
from pytest_obligation.integrations.django.edge_values import model_edges
from pytest_obligation.integrations.django.lifecycle_states import Lifecycle
from pytest_obligation.integrations.django.owed_references import (
    PrimitiveOwner,
    ReferenceLoop,
    owed_owners,
)
from pytest_obligation.integrations.django.owed_references import (
    isolated_primitive as isolated_primitive,
)
from pytest_obligation.integrations.django.owed_rows import OWED_ROW_PROOFS, EdgeFamily, OwedRowNotHandled, OwedRows
from pytest_obligation.poison import PoisonDropped, StopRequestDropped
from pytest_obligation.profiles.automatic_recovery import DueWorkSweep


def rows() -> OwedRows:
    # ARRANGE: each case owns one production-shaped reference loop.
    loop = ReferenceLoop()
    # REAL PRODUCTION: the reference selection and execution are library-owned controls.
    # EXTERNAL SEAM: the same per-row fault seam tests failure and stop requests.
    # OBSERVE: only successful execution adds to this dispatch recorder.
    return OwedRows(
        make_owed=lambda: PrimitiveOwner.objects.create(value="valid"),
        execute=loop.execute,
        run_tick=loop.tick,
        dispatched_ids=lambda: loop.dispatched,
        poison=lambda row: loop.poison.poisoned(row.pk),
    )


def selection(**changes: Any) -> ScheduledSelection:
    return ScheduledSelection(
        name="reference rows",
        due_work=owed_owners,
        owed_rows=rows,
        owed_edges={"owner": EdgeFamily(model=PrimitiveOwner)},
        assert_scheduled=lambda: None,
        **changes,
    )


def generated_ids() -> list[str]:
    # Host is configured by the Django conftest before collection.
    return [
        param.id
        for param in scheduled_selection_cases(selection())
        if param.id
        not in {
            "assert_the_adapter_does_not_author_the_selection",
            "assert_selection_is_index_served",
            "assert_selection_does_not_read_the_replica",
            "assert_the_selection_is_actually_scheduled",
        }
    ]


@pytest.mark.usefixtures("isolated_primitive")
@pytest.mark.parametrize("case_id", generated_ids())
def test_generated_light_contract(case_id: str) -> None:
    case = next(param.values[0] for param in scheduled_selection_cases(selection()) if param.id == case_id)
    case.run()


def test_each_legal_edge_has_both_generated_proofs() -> None:
    names = set(generated_ids())
    for edge in model_edges(PrimitiveOwner):
        assert f"assert_database_legal_owed_row_is_handled[owner-{edge.id}]" in names
        assert f"assert_inadmissible_owed_row_does_not_block_the_next[owner-{edge.id}]" in names
    assert {edge.kind for edge in model_edges(PrimitiveOwner)} == {
        "blank",
        "whitespace",
        "max_length",
        "zero",
        "negative",
        "maximum",
    }


def test_light_contract_gap_types_cannot_absorb_a_broken_control() -> None:
    key = "assert_database_legal_owed_row_is_handled[owner-value-blank]"
    params = scheduled_selection_cases(selection(adoption=Adoption.LEGACY, gaps={key: "old worker rejects blanks"}))
    param = next(p for p in params if p.id == key)
    mark = next(m for m in param.marks if m.name == "xfail")
    assert mark.kwargs["raises"] is OwedRowNotHandled
    with pytest.raises(ObligationContractDesignError):
        selection(adoption=Adoption.LEGACY, gaps={"assert_valid_owed_row_leaves_the_selection": "broken example"})


@pytest.mark.parametrize(
    "proof,failure",
    [
        ("assert_one_poisoned_identity_does_not_stall_the_tick", PoisonDropped),
        ("assert_a_soft_time_limit_ends_the_tick", StopRequestDropped),
    ],
)
def test_each_gap_resolves_in_its_own_failure_family(proof: str, failure: type[AssertionError]) -> None:
    params = scheduled_selection_cases(selection(adoption=Adoption.LEGACY, gaps={f"{proof}[dropped]": "legacy drop"}))
    param = next(p for p in params if p.id == proof)
    assert next(m for m in param.marks if m.name == "xfail").kwargs["raises"] is failure


def sweep() -> DueWorkSweep:
    # ARRANGE: the same reference lifecycle, with rows already eligible.
    loop = ReferenceLoop()
    # REAL PRODUCTION: invoke the actual reference loop.
    # EXTERNAL SEAM: the per-row switch is the only injected failure.
    # OBSERVE: use the loop's dispatch recorder.
    return DueWorkSweep(
        name="reference",
        due_work=owed_owners,
        run_tick=loop.tick,
        make_owed=lambda **_kwargs: PrimitiveOwner.objects.create(value="valid"),
        make_terminal=lambda **_kwargs: [],
        recovery_delay=timedelta(),
        page_size=10,
        lifecycle=Lifecycle(state_fields=("value",), execute=loop.execute),
        dispatched_ids=lambda: loop.dispatched,
    )


def native() -> ObligationContract:
    return ObligationContract(
        name="native reference",
        sweep=sweep,
        owed_model=PrimitiveOwner,
        profiles={p: Claim() if p is Profile.A else NotApplicable("unrelated control") for p in Profile},
    )


@pytest.mark.usefixtures("isolated_primitive")
@pytest.mark.parametrize(
    "key", [f"{proof}[{edge.id}]" for proof in OWED_ROW_PROOFS for edge in model_edges(PrimitiveOwner)]
)
def test_generated_native_contract(key: str) -> None:
    case = next(param.values[0] for param in contract_cases(native()) if param.id == f"A-{key}")
    assert case.profile is Profile.A and case.family == "owed-row-admissibility"
    case.run()


def test_edge_catalog_respects_database_column_constraints() -> None:
    from django.db import models

    from pytest_obligation.integrations.django.edge_values import database_legal_edges

    cases = [
        (
            models.CharField(max_length=5, choices=[("~", "tilde"), ("plain", "plain")]),
            {"blank", "whitespace", "max_length", "unknown_choice"},
        ),
        (models.PositiveSmallIntegerField(), {"zero", "maximum"}),
        (models.BigIntegerField(), {"zero", "negative", "maximum"}),
        (models.CharField(max_length=5, null=True), set()),
        (models.AutoField(primary_key=True), set()),
    ]
    for field, expected in cases:
        field.set_attributes_from_name("value")
        edges = database_legal_edges(field)
        assert {edge.kind for edge in edges} == expected
        for edge in edges:
            if edge.kind == "unknown_choice":
                assert len(str(edge.value)) <= 5
                assert edge.value not in dict(field.flatchoices)
            if edge.kind == "maximum":
                assert edge.value in (32767, 9223372036854775807)


@pytest.mark.usefixtures("isolated_primitive")
@pytest.mark.parametrize("retire", [False, True])
def test_related_row_edge_reaches_the_worker(retire: bool) -> None:
    from django.utils import timezone

    from pytest_obligation.integrations.django.edge_values import CandidateEdge
    from pytest_obligation.integrations.django.owed_references import PrimitiveWork
    from pytest_obligation.integrations.django.owed_rows import assert_database_legal_owed_row_is_handled

    def make() -> PrimitiveWork:
        return PrimitiveWork.objects.create(owner=PrimitiveOwner.objects.create(value="valid"))

    def execute(identity: int) -> None:
        work = PrimitiveWork.objects.select_related("owner").get(pk=identity)
        if not work.owner.value and not retire:
            raise ValueError("empty related value")
        PrimitiveOwner.objects.filter(pk=work.owner_id).update(completed_at=timezone.now())

    def prove() -> None:
        assert_database_legal_owed_row_is_handled(
            name="related owner",
            edge=CandidateEdge(field="value", kind="blank", value=""),
            selection=lambda: PrimitiveWork.objects.filter(owner__completed_at__isnull=True),
            rows=OwedRows(make_owed=make, execute=execute, run_tick=lambda: None, dispatched_ids=lambda: []),
            family=EdgeFamily(model=PrimitiveOwner, edge_row=lambda work: work.owner),
        )

    if retire:
        prove()
    else:
        with pytest.raises(OwedRowNotHandled, match="empty related value"):
            prove()


_COMBINATION_GAP = "assert_selection_is_complete[value:ready]"


def test_generated_selection_completeness_is_opt_in_and_gap_is_narrow() -> None:
    from pytest_obligation.integrations.django.selection_completeness import GAP_FAILURES

    assert not any(p.id == "A-assert_selection_is_complete" for p in contract_cases(native()))
    contract = native().model_copy(update={"prove_selection_complete": True})
    cases = {p.id: p for p in contract_cases(contract)}
    assert cases["A-assert_selection_is_complete"].values[0].fixtures[-1] == "due_work_selection_budget"
    declared = selection(
        state_fields=("value",),
        adoption=Adoption.LEGACY,
        gaps={_COMBINATION_GAP: "legacy branch requires a production repair"},
    )
    cases = {p.id: p for p in scheduled_selection_cases(declared)}
    mark = next(m for m in cases[_COMBINATION_GAP].marks if m.name == "xfail")
    assert mark.kwargs["strict"] and mark.kwargs["raises"] == GAP_FAILURES
    assert not any(m.name == "xfail" for m in cases["assert_selection_is_complete"].marks)


@pytest.mark.parametrize(
    "gap",
    [
        "assert_selection_is_complete",
        "assert_selection_is_complete[value:ready|done]",
        "assert_selection_is_complete[value:ready",
    ],
)
def test_selection_completeness_rejects_broad_or_malformed_gaps(gap: str) -> None:
    with pytest.raises(ObligationContractDesignError):
        selection(state_fields=("value",), adoption=Adoption.LEGACY, gaps={gap: "legacy branch requires repair"})
