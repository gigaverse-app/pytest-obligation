"""
Owed identities that are not database rows: a reconciler that lists provider resources and deletes orphans.

The generated light contract must pass on a conforming reconciler bound
through its listing seam, and each case must fail on the defect it names: a
reconciler that stops at its first failing orphan, one that reports nothing,
one that adopts a failing orphan so it stops being listed, and a step that
never deletes. The declaration itself is checked both ways: a listing must be
declared, and a declared listing must be bound, production-owned and keyed by
its own identity.
"""

from collections.abc import Callable
from typing import Any

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from pytest_obligation import (
    Adoption,
    ExternalIdentities,
    ObligationContractDesignError,
    Polling,
    ScheduledSelection,
    scheduled_selection_cases,
)
from pytest_obligation.integrations.django.owed_references import (
    OrphanReconciler,
    PrimitiveOwner,
    ProviderResource,
    ResourceProvider,
    owed_owners,
)
from pytest_obligation.integrations.django.owed_references import isolated_primitive as isolated_primitive
from pytest_obligation.integrations.django.owed_rows import EdgeFamily, OwedRows
from pytest_obligation.poison import PoisonDropped, PoisonStalled, PoisonUnreported

EXTERNAL = ExternalIdentities("orphans are provider resources no owner row names; the provider listing produces them")
SELECTION_PROOF_IDS = {
    "assert_the_adapter_does_not_author_the_selection",
    "assert_selection_is_index_served",
    "assert_selection_does_not_read_the_replica",
    "assert_the_selection_is_actually_scheduled",
}


def _name(resource: ProviderResource) -> str:
    return resource.name


def reconciled(reconciler_type: type[OrphanReconciler] = OrphanReconciler, **changes: Any) -> Callable[[], OwedRows]:
    def bind() -> OwedRows:
        # ARRANGE: each case owns one provider fake and the reconciler reading it.
        provider = ResourceProvider()
        reconciler = reconciler_type(provider)
        # REAL PRODUCTION: the reference listing, step and tick are library-owned controls.
        # EXTERNAL SEAM: the provider fake supplies the resources; the per-resource switch injects failure.
        # OBSERVE: only successful deletion adds to this dispatch recorder.
        rows = OwedRows(
            make_owed=provider.create,
            listed=reconciler.orphans,
            identity_of=_name,
            execute=reconciler.execute,
            run_tick=reconciler.tick,
            dispatched_ids=lambda: reconciler.dispatched,
            poison=lambda resource: reconciler.poison.poisoned(resource.name),
        )
        return rows.model_copy(update=changes)

    return bind


def selection(**changes: Any) -> ScheduledSelection:
    declared: dict[str, Any] = {
        "name": "orphaned resources",
        # The row-backed part of the loop: the owners whose names make a resource known.
        "due_work": owed_owners,
        "owed_rows": reconciled(),
        "external_identities": EXTERNAL,
        "assert_scheduled": lambda: None,
    }
    return ScheduledSelection(**{**declared, **changes})


def case(declaration: ScheduledSelection, case_id: str) -> Any:
    return next(param.values[0] for param in scheduled_selection_cases(declaration) if param.id == case_id)


def owed_ids(declaration: ScheduledSelection) -> list[str]:
    return [p.id for p in scheduled_selection_cases(declaration) if p.id not in SELECTION_PROOF_IDS]


@pytest.fixture(autouse=True)
def _stop_exception():
    from pytest_obligation.host import current_host, hosted

    with hosted(current_host().model_copy(update={"stop_exception": SoftTimeLimitExceeded})):
        yield


@pytest.mark.usefixtures("isolated_primitive")
@pytest.mark.parametrize("case_id", owed_ids(selection()))
def test_generated_external_identity_contract(case_id: str) -> None:
    case(selection(), case_id).run()


def test_external_identities_generate_the_loop_cases_and_no_edge_cases() -> None:
    assert owed_ids(selection()) == [
        "assert_owed_row_bindings_are_production_bound",
        "assert_valid_owed_row_leaves_the_selection",
        "assert_the_tick_dispatches_owed_rows_in_selection_order",
        "assert_one_poisoned_identity_does_not_stall_the_tick",
        "assert_a_soft_time_limit_ends_the_tick",
    ]


class _StoppingReconciler(OrphanReconciler):
    """DEFECTIVE: the first failing orphan ends the tick, so it blocks every orphan listed behind it."""

    def tick(self) -> None:
        for identity in self.owed():
            self.execute(identity)
            self.dispatched.append(identity)


class _SilentReconciler(OrphanReconciler):
    """DEFECTIVE: isolates each failure and logs nothing, so the tick reports success."""

    def tick(self) -> None:
        try:
            super().tick()
        except ExceptionGroup:
            pass


class _AdoptingReconciler(OrphanReconciler):
    """DEFECTIVE: adopts a resource it could not delete, so it is never listed as an orphan again."""

    def tick(self) -> None:
        try:
            super().tick()
        except ExceptionGroup:
            for identity in self.owed():
                if identity not in self.dispatched:
                    PrimitiveOwner.objects.create(value=identity)
            raise


class _KeepingReconciler(OrphanReconciler):
    """DEFECTIVE as a binding: the step never deletes, so a valid orphan stays listed."""

    def execute(self, identity: Any) -> None:
        self.poison.check(identity)


POISON = "assert_one_poisoned_identity_does_not_stall_the_tick"


@pytest.mark.usefixtures("isolated_primitive")
@pytest.mark.parametrize(
    "reconciler_type,failure,message",
    [
        (_StoppingReconciler, PoisonStalled, "did not progress"),
        (_SilentReconciler, PoisonUnreported, "reported nothing"),
        (_AdoptingReconciler, PoisonDropped, "no longer owed"),
    ],
)
def test_the_generated_poison_case_finds_each_isolation_defect(
    reconciler_type: type[OrphanReconciler], failure: type[AssertionError], message: str
) -> None:
    with pytest.raises(failure, match=message):
        case(selection(owed_rows=reconciled(reconciler_type)), POISON).run()


@pytest.mark.usefixtures("isolated_primitive")
def test_the_generated_control_rejects_a_step_that_never_deletes() -> None:
    declaration = selection(owed_rows=reconciled(_KeepingReconciler))
    with pytest.raises(AssertionError, match="still selected after the production step"):
        case(declaration, "assert_valid_owed_row_leaves_the_selection").run()


@pytest.mark.usefixtures("isolated_primitive")
def test_a_declared_external_selection_requires_the_listing() -> None:
    declaration = selection(owed_rows=reconciled(listed=None))
    with pytest.raises(AssertionError, match="owed_rows.listed is unbound"):
        case(declaration, POISON).run()


@pytest.mark.usefixtures("isolated_primitive")
def test_a_listing_needs_the_external_declaration() -> None:
    declaration = selection(external_identities=None, owed_edges={"owner": EdgeFamily(model=PrimitiveOwner)})
    with pytest.raises(AssertionError, match="does not declare external identities"):
        case(declaration, "assert_owed_row_bindings_are_production_bound").run()


@pytest.mark.usefixtures("isolated_primitive")
def test_an_external_identity_needs_its_own_identity_of() -> None:
    def bind() -> OwedRows:
        # ARRANGE: the conforming binding above,
        # REAL PRODUCTION: with its reconciler's step, tick and listing,
        # EXTERNAL SEAM: its provider fake and switch,
        # OBSERVE: and its recorder, rebuilt without identity_of so a primary-key default would apply.
        return OwedRows(**reconciled()().model_dump(exclude={"identity_of"}))

    with pytest.raises(AssertionError, match="bind owed_rows.identity_of"):
        case(selection(owed_rows=bind), POISON).run()


@pytest.mark.usefixtures("isolated_primitive")
def test_the_guard_rejects_a_listing_written_in_the_test() -> None:
    def bind() -> OwedRows:
        # ARRANGE: the conforming binding above,
        # REAL PRODUCTION: except the listing,
        # EXTERNAL SEAM: which reads a provider fake of its own
        # OBSERVE: through an orphan predicate retyped in the test (DEFECTIVE).
        provider = ResourceProvider()
        return reconciled()().model_copy(
            update={
                "listed": lambda: [
                    r for r in provider.list() if not PrimitiveOwner.objects.filter(value=r.name).exists()
                ]
            }
        )

    with pytest.raises(AssertionError, match="owed_rows.listed"):
        case(selection(owed_rows=bind), "assert_owed_row_bindings_are_production_bound").run()


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"owed_rows": None}, "declare owed_rows with it"),
        ({"owed_edges": {"owner": EdgeFamily(model=PrimitiveOwner)}}, "no database row to perturb"),
        ({"state_fields": ("value",)}, "no database row to perturb"),
        ({"external_identities": ExternalIdentities(" ")}, "external_identities.because is empty"),
        ({"external_identities": None}, "owed_rows and owed_edges come together"),
    ],
)
def test_the_external_declaration_is_validated(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ObligationContractDesignError, match=message):
        selection(**changes)


def test_a_legacy_external_poison_gap_names_its_failure() -> None:
    declared = selection(adoption=Adoption.LEGACY, gaps={f"{POISON}[unreported]": "the reconciler logs and moves on"})
    param = next(p for p in scheduled_selection_cases(declared) if p.id == POISON)
    assert next(m for m in param.marks if m.name == "xfail").kwargs["raises"] is PoisonUnreported


def test_external_identities_compose_with_polling() -> None:
    assert "assert_a_polled_row_is_served_and_stays_selected" in owed_ids(
        selection(polling=Polling("resources are re-read every tick and never deleted"))
    )
