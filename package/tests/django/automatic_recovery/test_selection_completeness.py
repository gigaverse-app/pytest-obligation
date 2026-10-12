"""
Root controls for the selection-completeness property.

Each verdict must fail on the defect it names and pass on the repair, over the
reference batch lifecycle (a real table, a recovery step that only publishes
its dispatcher): a selection that drops the READY-batch branch, a dispatcher
that works items past the attempt budget the selection stops at, a selection
that returns rows its dispatcher ignores, a completion step no selection
recovers, and exclusions that are true and false. Draws the database refuses
are rejected, and the same declaration draws the same rows twice.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import pytest
from django.db.models import QuerySet

from pytest_obligation.host import current_host, hosted
from pytest_obligation.integrations.celery import celery_handoffs
from pytest_obligation.integrations.django import selection_completeness
from pytest_obligation.integrations.django.batch_references import (
    Batch,
    BatchItem,
    batch_of,
    items_awaiting_dispatch,
    items_of_live_batches_with_parked,
    items_of_running_batches,
    make_ready_item,
    run_batch_ignoring_budget,
    schedule_batch,
    schedule_completing_batch,
)
from pytest_obligation.integrations.django.batch_references import (
    batch_tables_fixture as batch_tables_fixture,
)
from pytest_obligation.integrations.django.lifecycle_states import (
    resolve_state_path,
)
from pytest_obligation.integrations.django.owed_rows import (
    OwedRowNotHandled,
)
from pytest_obligation.integrations.django.selection_completeness import (
    CompletenessBinding,
    SelectionIncomplete,
    assert_declared_gap_still_fails,
    assert_selection_is_complete,
    gap_combination,
    gap_key,
)


@pytest.fixture(autouse=True)
def handoff_host():
    with hosted(current_host().model_copy(update={"handoff_runner": celery_handoffs})):
        yield


pytestmark = pytest.mark.usefixtures("batch_tables")

#: The unrecovered completion: a started batch whose items are all done.
FINISHED_BUT_RUNNING = {"state": "done", "batch__status": "running"}


def _reference(
    selection: Callable[[], QuerySet[Any]],
    *,
    execute: Callable[[Any], Any] = schedule_batch,
    excluded_states: Mapping[str, str] | None = None,
    state_fields: tuple[str, ...] = ("state", "batch__status"),
    fixed_fields: Mapping[str, str] | None = None,
) -> Callable[[], AbstractContextManager[CompletenessBinding]]:
    @contextmanager
    def enter() -> Iterator[CompletenessBinding]:
        yield CompletenessBinding(
            name="reference batches",
            selection=selection,
            make_owed=make_ready_item,
            execute=execute,
            identity_of=batch_of,
            state_fields=state_fields,
            excluded_states=excluded_states or {},
            fixed_fields=fixed_fields or {},
        )

    return enter


def test_a_complete_selection_passes() -> None:
    verdicts = assert_selection_is_complete(_reference(items_awaiting_dispatch))
    # Both halves measured something: rows were served, and rows were skipped and left alone.
    assert verdicts["selected"] and verdicts["skipped"], verdicts


def test_a_selection_missing_a_branch_the_worker_acts_on_fails() -> None:
    # The dispatcher starts a READY batch and works its item; the selection no longer returns it.
    with pytest.raises(SelectionIncomplete, match=r"skips a row .*'batch__status': 'ready'.* moved its states"):
        assert_selection_is_complete(_reference(items_of_running_batches))


def test_a_skipped_row_is_judged_by_what_its_handoff_does() -> None:
    # schedule_batch publishes for every batch it is given; only the dispatcher's work counts, so the
    # complete selection passes above, and the broken one names the state the dispatcher moved.
    with pytest.raises(SelectionIncomplete, match=r"moved its states from"):
        assert_selection_is_complete(_reference(items_of_running_batches, execute=schedule_batch))


def test_a_worker_past_the_budget_the_selection_stops_at_fails() -> None:
    # attempts is a compared field, drawn and edged (its maximum is a catalog example).
    with pytest.raises(SelectionIncomplete, match=r"attempts"):
        assert_selection_is_complete(_reference(items_awaiting_dispatch, execute=run_batch_ignoring_budget))


def _tick(selection: Callable[[], QuerySet[Any]], dispatched: list[int]) -> Callable[[], None]:
    def tick() -> None:
        for batch_id in selection().values_list("batch_id", flat=True).distinct():
            dispatched.append(batch_id)
            schedule_batch(batch_id)

    return tick


@pytest.mark.parametrize(
    ("walks", "fails"), [(items_awaiting_dispatch, False), (items_of_running_batches, True)], ids=["same", "narrower"]
)
def test_a_tick_walking_a_narrower_query_than_the_selection_fails(
    walks: Callable[[], QuerySet[Any]], fails: bool
) -> None:
    dispatched: list[int] = []

    @contextmanager
    def enter() -> Iterator[CompletenessBinding]:
        yield CompletenessBinding(
            name="reference batches",
            selection=items_awaiting_dispatch,
            make_owed=make_ready_item,
            execute=schedule_batch,
            identity_of=batch_of,
            dispatched_ids=lambda: list(dispatched),
            run_tick=_tick(walks, dispatched),
            state_fields=("state", "batch__status"),
        )

    if not fails:
        assert_selection_is_complete(enter)
        return
    with pytest.raises(SelectionIncomplete, match=r"one production tick did not dispatch it"):
        assert_selection_is_complete(enter)


def test_a_selected_row_its_worker_ignores_fails() -> None:
    with pytest.raises(OwedRowNotHandled, match=r"did nothing at all"):
        assert_selection_is_complete(_reference(items_of_live_batches_with_parked))


def test_an_unrecovered_completion_fails() -> None:
    with pytest.raises(SelectionIncomplete, match=r"'state': 'done', 'batch__status': 'running'"):
        assert_selection_is_complete(_reference(items_awaiting_dispatch, execute=schedule_completing_batch))


def test_a_declared_exclusion_passes() -> None:
    reference = _reference(
        items_awaiting_dispatch,
        execute=schedule_completing_batch,
        excluded_states={
            "state:done,batch__status:running": (
                "the reference declares the finishing step completes its batch in the same transaction"
            )
        },
    )
    assert assert_selection_is_complete(reference)["excluded"]


def test_an_exclusion_the_selection_returns_fails() -> None:
    reference = _reference(
        items_awaiting_dispatch,
        excluded_states={"state:ready,batch__status:running": "declared unreachable, but the selection returns it"},
    )
    with pytest.raises(SelectionIncomplete, match=r"declares owes nothing"):
        assert_selection_is_complete(reference)


def test_a_declared_gap_is_left_to_its_own_case_which_still_fails() -> None:
    reference = _reference(items_awaiting_dispatch, execute=schedule_completing_batch)
    gap = gap_key(FINISHED_BUT_RUNNING)
    assert gap == "assert_selection_is_complete[batch__status:running,state:done]"
    assert_selection_is_complete(reference, gaps=(gap,))
    with pytest.raises(SelectionIncomplete):
        assert_declared_gap_still_fails(reference, gap)


def test_a_declared_gap_on_a_combination_that_owes_nothing_does_not_fail() -> None:
    # The repaired workflow: the same gap now names a row the dispatcher leaves alone, so its strict xfail would pass.
    assert_declared_gap_still_fails(_reference(items_awaiting_dispatch), gap_key(FINISHED_BUT_RUNNING))


def test_a_draw_the_database_refuses_is_rejected_not_failed() -> None:
    # A claimed item must name its owner (a CHECK constraint); writing "claimed" alone cannot exist in a row.
    verdicts = assert_selection_is_complete(_reference(items_awaiting_dispatch, state_fields=("state",)))
    assert verdicts["rejected"], verdicts


def test_the_same_declaration_draws_the_same_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[list[str]] = [[], []]
    run_one = selection_completeness._run_one
    for run in drawn:

        def recording(enter: Any, assignment: dict[str, Any], gaps: Any, *, commits: bool, run: list[str] = run) -> str:
            run.append(repr(sorted(assignment.items())))
            return run_one(enter, assignment, gaps, commits=commits)

        monkeypatch.setattr(selection_completeness, "_run_one", recording)
        assert_selection_is_complete(_reference(items_awaiting_dispatch))
    assert drawn[0] == drawn[1] and len(drawn[0]) > selection_completeness.PR_EXAMPLES


@pytest.mark.parametrize(
    "gap",
    [
        "assert_selection_is_complete",
        "assert_selection_is_complete[]",
        "assert_selection_is_complete[state:ready|done]",
        "assert_selection_is_complete[state]",
    ],
)
def test_a_gap_names_one_value_per_state_path(gap: str) -> None:
    if gap == "assert_selection_is_complete":
        assert gap_combination(gap) is None
        return
    with pytest.raises(AssertionError, match="one value per state path"):
        gap_combination(gap)


def test_an_exclusion_naming_an_unknown_state_is_refused() -> None:
    reference = _reference(items_awaiting_dispatch, excluded_states={"state:archived": "no such state exists here"})
    with pytest.raises(AssertionError, match="not values of state"):
        assert_selection_is_complete(reference)


def test_a_related_state_path_walks_forward_relations_only() -> None:
    state = resolve_state_path(BatchItem, "batch__status")
    assert (state.model, state.field.name, state.relations) == (Batch, "status", ("batch",))
    with pytest.raises(AssertionError, match="not a forward relation"):
        resolve_state_path(Batch, "items__state")


def test_a_handoff_sql_failure_does_not_abort_the_proofs_transaction() -> None:
    from celery import shared_task
    from django.db import DataError, connection, transaction

    @shared_task(name="selection_completeness.sql_failure")
    def sql_failure() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 / 0")

    with transaction.atomic():
        with pytest.raises(DataError):
            celery_handoffs(sql_failure.delay)
        # The failed delivery is evidence, not a broken connection hiding the final observation.
        assert Batch.objects.count() == 0


@pytest.mark.parametrize("declared_gap", [False, True])
def test_committing_proofs_clean_up_examples_even_when_the_verdict_fails(declared_gap: bool) -> None:
    existing = make_ready_item()
    existing.state = BatchItem.State.DONE
    existing.save(update_fields=["state"])
    if declared_gap:
        with pytest.raises(SelectionIncomplete):
            assert_declared_gap_still_fails(
                _reference(items_awaiting_dispatch, execute=schedule_completing_batch),
                gap_key(FINISHED_BUT_RUNNING),
                commits=True,
            )
    else:
        assert_selection_is_complete(_reference(items_awaiting_dispatch), commits=True)
    # Retain pre-existing application rows; no proof-created selected row may
    # occupy the next example's recovery page, even after a failing verdict.
    assert list(BatchItem.objects.values_list("pk", flat=True)) == [existing.pk]


@pytest.mark.parametrize("kind", ["blank", "whitespace", "max_length", "unknown_choice"])
def test_selection_gaps_can_name_exact_database_legal_state_edges(kind: str) -> None:
    from pytest_obligation.integrations.django.edge_values import database_legal_edges
    from pytest_obligation.integrations.django.selection_completeness import parse_combination

    state = resolve_state_path(BatchItem, "state")
    edge = next(edge for edge in database_legal_edges(state.field) if edge.kind == kind)
    parsed = parse_combination(f"state:@{kind}", {"state": state})
    assert parsed.assignment() == {"state": edge.value}
    assert isinstance(edge.value, str)
    assert parsed.matches({"state": edge.value})
    assert not parsed.matches({"state": BatchItem.State.READY})


def test_an_unknown_edge_alias_is_not_a_blanket_selection_gap() -> None:
    from pytest_obligation.integrations.django.selection_completeness import parse_combination

    state = resolve_state_path(BatchItem, "state")
    with pytest.raises(AssertionError, match="not values"):
        parse_combination("state:@anything", {"state": state})


@pytest.mark.parametrize(
    "field, reason",
    [
        ("missing", "A different worker owns this routing key."),
        ("state", "A different worker owns this lifecycle state."),
        ("attempts", ""),
    ],
)
def test_fixed_selection_fields_require_a_compared_non_state_column_and_reason(field: str, reason: str) -> None:
    with pytest.raises(AssertionError, match="fixed_fields"):
        assert_selection_is_complete(_reference(items_awaiting_dispatch, fixed_fields={field: reason}))


def test_fixing_a_compared_field_does_not_hide_a_missing_lifecycle_branch() -> None:
    with pytest.raises(SelectionIncomplete, match="batch__status"):
        assert_selection_is_complete(
            _reference(
                items_of_running_batches,
                fixed_fields={
                    "attempts": "This scenario starts with a newly admitted item; retry-budget boundaries have independent controls."
                },
            )
        )
