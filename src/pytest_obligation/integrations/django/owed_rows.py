"""Database-legal owed rows, ordered recovery and poison isolation proofs."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta
from typing import Any

from django.db import connection, transaction
from django.db.models import Model, QuerySet
from django.test import TestCase

from pytest_obligation.binding import (
    INVOCATION_AUTHORING_OPERATIONS,
    assert_binding_reaches_production,
    assert_test_binding_consumes_its_first_parameter,
)
from pytest_obligation.host import HandoffsNeverStop, current_host
from pytest_obligation.integrations.django.edge_values import CandidateEdge, write_unvalidated
from pytest_obligation.integrations.django.lifecycle_states import (
    new_entries,
    observed_effects,
    resolve_state_path,
)
from pytest_obligation.models import HarnessModel
from pytest_obligation.poison import (
    PoisonedHistory,
    assert_a_stop_request_ends_the_tick,
    assert_poison_is_isolated,
)
from pytest_obligation.profiles.automatic_recovery import (
    DueWorkSweep,
    declared_recovery_delay,
)


def _selected(selection: Callable[[], Iterable[Any]], identity_of: Callable[[Any], Any]) -> list[Any]:
    """One evaluation of the production selection, in its order, as identities."""
    return [identity_of(row) for row in selection()]


class _OwedPair(HarnessModel):
    """Two fresh owed rows by identity, and which of them the production selection returns first."""

    rows: dict[Any, Any]
    head: Any
    behind: Any


def _two_owed_in_selection_order(
    name: str, selection: Callable[[], Iterable[Any]], make_owed: Callable[[], Any], identity_of: Callable[[Any], Any]
) -> _OwedPair:
    rows = {identity_of(row): row for row in (make_owed(), make_owed())}
    order = [identity for identity in _selected(selection, identity_of) if identity in rows]
    assert len(rows) == 2 and sorted(order, key=repr) == sorted(rows, key=repr), (
        f"{name}: two owed examples with distinct identities must both be selected; the selection returned "
        f"{order} of {list(rows)}"
    )
    head, behind = order
    return _OwedPair(rows=rows, head=head, behind=behind)


def _persisted(model: type[Model], pk: Any) -> dict[str, Any] | None:
    """Every concrete column of the row as the database holds it; None once it is deleted."""
    columns = [field.attname for field in model._meta.concrete_fields]
    return model._base_manager.filter(pk=pk).values(*columns).first()


def _rows_as_persisted(rows: tuple[Model, ...]) -> tuple[dict[str, Any] | None, ...]:
    return tuple(_persisted(type(row), row.pk) for row in rows)


def _edge_target(row: Any, edge_row: Callable[[Any], Model] | None, edge_model: type[Model] | None) -> Model:
    """The row whose field the edge value goes into: the selected row, or one it relates to."""
    target = edge_row(row) if edge_row is not None else row
    # A family whose model is not the written row's would enumerate one table's
    # fields and write them into another: loud on a missing name, silent on a shared one.
    assert edge_model is None or type(target)._meta.concrete_model is edge_model._meta.concrete_model, (
        f"the edge values are {edge_model.__name__ if edge_model else None} fields, but they would be written into "
        f"{type(target).__name__}. Name the related row the worker reads with `edge_row=`, or declare the model "
        f"the selection returns"
    )
    return target


class OwedRowNotHandled(AssertionError):
    """
    The invariant itself failed, as opposed to a positive control or a binding check.

    A declared legacy gap expects exactly this, so a broken example or a wrong
    ``owed_model`` still fails a gapped case instead of being absorbed by it.
    """


class FailureEnds(HarnessModel):
    """
    What ends an owed row whose delivery chain raised after moving it out of the selection.

    Projected by the contract (:func:`failure_ends_of_sweep`), never bound by
    the adopter: a field on :class:`OwedRows` would let a binding declare its
    own failures handled. The default, nothing, is the light contract's.
    """

    #: Whether the row is in one of the sweep's own terminal states; a deleted row is ended too.
    is_terminal: Callable[[Any], bool] | None = None
    #: The contract claims profile J without gaps: a persistently failing row reaches a terminal state at its budget.
    retries_bounded: bool = False

    def end(self, row: Any) -> bool:
        return self.retries_bounded or (self.is_terminal is not None and self.is_terminal(row))


#: The light contract's ends: no terminal declaration and no profile J, so a raise that leaves the selection fails.
NOTHING_ENDS_A_FAILURE = FailureEnds()


def failure_ends_of_sweep(sweep: DueWorkSweep, *, retries_bounded: bool) -> FailureEnds:
    """A profile-A sweep's ends: the lifecycle states of its ``make_terminal`` examples, and its profile J claim."""
    assert sweep.lifecycle is not None, (
        f"{sweep.name}: owed-row admissibility reads Lifecycle.state_fields; declare one"
    )
    state_fields = sweep.lifecycle.state_fields

    def state_of(row: Model) -> tuple[Any, ...]:
        # A related path ("campaign__status") is read from the row it reaches.
        paths = [resolve_state_path(type(row), state_field) for state_field in state_fields]
        return tuple(getattr(path.holder(row), path.field.attname) for path in paths)

    def is_terminal(row: Any) -> bool:
        if not type(row)._base_manager.filter(pk=row.pk).exists():
            return True  # nothing can select a deleted row again
        row.refresh_from_db()
        return state_of(row) in {state_of(example) for example in sweep.make_terminal(age=timedelta(days=1))}

    return FailureEnds(is_terminal=is_terminal, retries_bounded=retries_bounded)


class ServedRow(HarnessModel):
    """What one production delivery, and the handoff chain it started, did to an owed row."""

    #: What raised, in the worker or anywhere in its chain; an autoretry's ``Retry`` carries what it raised.
    failure: BaseException | None
    #: Where the outcome happened, for the failure message.
    ran_in: str
    #: Whether anything besides publishing and recording the dispatch happened.
    worked: bool
    created: tuple[str, ...]


def serve_row(
    execute: Callable[[Any], Any], delivery: Any, *, dispatched_ids: Callable[[], list[Any]] | None
) -> ServedRow:
    """
    Deliver one owed row to the production worker, then the chain it hands off to.

    Commit callbacks run, as they would after the worker commits: inside a
    test's enclosing transaction they would otherwise never run, and the
    handoff they publish (the publish-after-commit pattern, AGENTS L4) would go
    unexamined. A chain still handing off after the host's handoff limit
    raises ``HandoffsNeverStop``.
    """
    failure: BaseException | None = None
    with observed_effects(dispatched_ids) as effects:
        try:
            runner = current_host().handoff_runner
            if runner is not None:

                def run_delivery() -> object:
                    with worker_transaction():
                        return execute(delivery)

                runner(run_delivery)
            else:
                with TestCase.captureOnCommitCallbacks(execute=True), worker_transaction():
                    execute(delivery)
        except HandoffsNeverStop:
            raise
        except Exception as error:
            failure = error
    assert not effects.published, (
        "the worker published follow-up work but the host did not deliver it; configure "
        "handoff_runner (celery_handoffs for Celery) so the proof observes the downstream outcome"
    )
    return ServedRow(
        failure=failure,
        ran_in="the production worker and its handoffs",
        worked=effects.did_work,
        created=tuple(effects.created),
    )


def assert_database_legal_owed_row_is_handled(
    *,
    name: str,
    edge: CandidateEdge,
    make_owed: Callable[[], Any],
    selection: Callable[[], Iterable[Any]],
    identity_of: Callable[[Any], Any],
    execute: Callable[[Any], Any],
    run_tick: Callable[[], Any],
    deliver: Callable[[Any], Any] | None = None,
    dispatched_ids: Callable[[], list[Any]] | None = None,
    effect_calls_for: Callable[[Any], int] | None = None,
    edge_row: Callable[[Any], Model] | None = None,
    edge_model: type[Model] | None = None,
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE,
) -> None:
    """
    INVARIANT: one production delivery of a selected database-legal owed row neither raises nor idles on it.

    ``edge_row`` maps the selected row to the row whose field the edge value
    goes into, when the worker reads a related row (a chunk's campaign);
    "unchanged" then covers both rows. ``edge_model`` is the model the edge
    was enumerated from, checked against that row. ``dispatched_ids`` is read
    for a recorder that patches a task instance, but an entry in it is not
    work: a run that reaches a row and skips it records one too. ``ends`` is
    what the contract says ends a row whose chain raised after moving it out
    of the selection.
    """
    row = make_owed()
    identity = identity_of(row)
    target = _edge_target(row, edge_row, edge_model)
    # POSITIVE CONTROL: the unmodified example is selected, so an absent edge
    # row below means the selection excluded it, not that nothing was selected.
    assert identity in _selected(selection, identity_of), (
        f"{name}: the owed example is not selected before any edge value is written; invariant 1 is the one to read"
    )
    if not (write_unvalidated(type(target), target.pk, edge) and identity in _selected(selection, identity_of)):
        # Excluded, or a value the database rejects: the same tick still runs,
        # so no case passes without running production.
        try:
            run_tick()
        except Exception as error:
            raise AssertionError(
                f"{name}: the tick raised {error!r} in a pass where the row with {edge.id} is not selected. "
                f"The example or its environment is broken, not the edge row"
            ) from error
        return

    row.refresh_from_db()
    assert_selected_owed_row_is_handled(
        name=name,
        row=row,
        related=(target,),
        describe=f"with {edge.id} ({edge.value!r})",
        selection=selection,
        identity_of=identity_of,
        execute=execute,
        deliver=deliver,
        dispatched_ids=dispatched_ids,
        effect_calls_for=effect_calls_for,
        ends=ends,
    )


def assert_inadmissible_owed_row_does_not_block_the_next(
    *,
    name: str,
    edge: CandidateEdge,
    make_owed: Callable[[], Any],
    selection: Callable[[], Iterable[Any]],
    identity_of: Callable[[Any], Any],
    run_tick: Callable[[], Any],
    dispatched_ids: Callable[[], Any],
    edge_row: Callable[[Any], Model] | None = None,
    edge_model: type[Model] | None = None,
) -> None:
    """INVARIANT: an edge row first in selection order does not stop the tick before the valid row behind it."""
    pair = _two_owed_in_selection_order(name, selection, make_owed, identity_of)
    target = _edge_target(pair.rows[pair.head], edge_row, edge_model)
    write_unvalidated(type(target), target.pk, edge)
    # Excluded, rejected by the database, or sorted after the valid row, the
    # edge row cannot precede it; the tick still runs and must still reach it.
    ahead = [identity for identity in _selected(selection, identity_of) if identity in pair.rows] == [
        pair.head,
        pair.behind,
    ]
    recorded = list(dispatched_ids())
    error: Exception | None = None
    try:
        run_tick()
    except Exception as raised:  # noqa: BLE001 - a loud tick is allowed; abandoning the next row is not
        error = raised
    # INVARIANT ENFORCEMENT: the valid row was dispatched by this tick, not before it.
    if pair.behind not in new_entries(recorded, list(dispatched_ids())):
        raise OwedRowNotHandled(
            f"{name}: a database-legal owed row with {edge.id} ({edge.value!r}) "
            f"{'first in selection order' if ahead else 'in the same tick'} stopped the tick before the valid row "
            f"behind it (the tick raised {error!r}). Selection is oldest-first, so that row leads every tick and "
            f"blocks every later row of its kind"
        ) from error


def _pk(row: Any) -> Any:
    return row.pk


class EdgeFamily(HarnessModel):
    """
    One model whose database-legal values the owed-row proofs perturb.

    ``edge_row`` maps the selected row to the row of ``model`` that receives the
    value, when the worker reads a related row (a chunk's campaign); ``None``
    perturbs the selected row itself, which must then be a ``model`` row.
    Declared on the
    :class:`~pytest_obligation.contract.ScheduledSelection`
    because cases are enumerated at collection.
    """

    model: type[Model]
    edge_row: Callable[[Any], Model] | None = None


class OwedRows(HarnessModel):
    """
    The per-row recovery loop behind a selection: what every owed-row proof reads.

    A ``ScheduledSelection`` declares one directly (``owed_rows=``), built per
    case by its factory, so it may hold the provider fakes and recorders; a
    ``DueWorkContract`` claiming profile A gets one projected from its
    ``DueWorkSweep`` and ``Lifecycle`` (:func:`owed_rows_of_sweep`).
    """

    #: ARRANGE: one more row the production selection returns, each call.
    make_owed: Callable[[], Any]
    #: REAL PRODUCTION: the per-identity step the tick runs, on what ``deliver`` builds.
    execute: Callable[[Any], Any]
    #: REAL PRODUCTION: one tick of the scheduled task.
    run_tick: Callable[[], Any]
    #: OBSERVE: identities the ticks dispatched or ran, in the order they did,
    #: recorded at the broker or a production audit record; never read from the
    #: selection. The generated order control proves it is such a recorder.
    dispatched_ids: Callable[[], list[Any]]
    identity_of: Callable[[Any], Any] = _pk
    deliver: Callable[[Any], Any] | None = None
    effect_calls_for: Callable[[Any], int] | None = None
    #: EXTERNAL SEAM: a context manager under which the per-identity step raises
    #: for the given owed row on every attempt, yielding ``fired()`` (the same
    #: contract as ``DueWorkSweep.poison``; ``PoisonSwitch`` supplies both
    #: halves, ``integrations.celery.refusing_publication`` the broker seam). Required
    #: by the generated poison case; ``None`` fails it with the instruction to
    #: bind one or declare the case a gap.
    poison: Callable[[Any], AbstractContextManager[Callable[[], int]]] | None = None
    #: OBSERVE: whether an owed row whose step raised is still owed after the
    #: tick. The poison case otherwise requires the selection to return it
    #: again; bind this when the step hands the obligation to another
    #: production selection before the call that failed (email unpark makes the
    #: campaign RUNNING, and the reaper's selection owns its READY chunks). It
    #: must read that production selection, which the binding guard checks,
    #: and answer for this row: in the state the poison tick leaves, a row the
    #: step and its handoffs served to completion must read False.
    still_owed: Callable[[Any], bool] | None = None


def owed_rows_of_sweep(sweep: DueWorkSweep, model: type[Model]) -> OwedRows:
    """
    A profile-A sweep as the owed-row binding, so both contracts run the same proofs.

    The examples are just past the sweep's recovery delay; the step is the
    lifecycle's production worker.
    """
    queryset = sweep.due_work()
    assert isinstance(queryset, QuerySet), "Django owed_model requires a QuerySet selection"
    selected = queryset.model
    assert selected._meta.concrete_model is model._meta.concrete_model, (
        f"{sweep.name}: owed_model={model.__name__} but the production selection returns "
        f"{selected.__name__}. Declare the model `due_work()` selects"
    )
    assert sweep.lifecycle is not None, (
        f"{sweep.name}: owed-row admissibility delivers the edge row to Lifecycle.execute; declare `lifecycle=`"
    )
    assert sweep.dispatched_ids is not None, (
        f"{sweep.name}: owed-row liveness reads which rows the tick dispatched; declare `dispatched_ids=`"
    )
    age = declared_recovery_delay(sweep) + timedelta(minutes=1)
    return OwedRows(
        make_owed=lambda: sweep.make_owed(age=age),
        execute=sweep.lifecycle.execute,
        run_tick=sweep.run_tick,
        dispatched_ids=sweep.dispatched_ids,
        identity_of=sweep.identity_of,
        deliver=sweep.lifecycle.deliver,
        effect_calls_for=sweep.lifecycle.effect_calls_for,
    )


def assert_owed_row_bindings_are_production_bound(name: str, rows: OwedRows) -> None:
    """INVARIANT 0 for the light contract: ``execute``, ``run_tick`` and ``still_owed`` invoke production, not a copy."""
    bindings = [
        ("execute", rows.execute, "the per-identity step the scheduled tick runs"),
        ("run_tick", rows.run_tick, "the scheduled task body"),
    ]
    if rows.still_owed is not None:
        bindings.append(("still_owed", rows.still_owed, "the production selection that owns the row next"))
    for field_name, binding, shape in bindings:
        assert_binding_reaches_production(
            adopter=name,
            field=f"owed_rows.{field_name}",
            binding=binding,
            forbidden=INVOCATION_AUTHORING_OPERATIONS,
            production_shape=shape,
        )
    if rows.still_owed is not None:
        # A still_owed that ignores its row ("is anything owed at all") would pass any poisoned row.
        assert_test_binding_consumes_its_first_parameter(
            adopter=name, field="owed_rows.still_owed", binding=rows.still_owed, parameter_shape="the poisoned row"
        )


def assert_valid_owed_row_leaves_the_selection(
    name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows
) -> None:
    """
    POSITIVE CONTROL: the unmodified owed row is served by the same step and handoffs.

    A sweep under the light contract runs no invariant 2c, so this is the
    control the "did nothing at all" oracle compares against: a valid row must
    leave the selection, through ``execute`` and the tasks it publishes, with no
    raise or retry anywhere in the chain. A sweep that legitimately re-reads a
    served row (polling) does not fit the light contract's owed-row proofs.
    """
    _served_to_completion(name, selection, rows)


def _served_to_completion(name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows) -> Any:
    """One fresh owed row, served by the production step and every task it hands off to; it leaves the selection."""
    row = rows.make_owed()
    identity = rows.identity_of(row)
    assert identity in _selected(selection, rows.identity_of), (
        f"{name}: the owed example is not selected, so nothing below would be measured"
    )
    failure = serve_row(
        rows.execute, rows.deliver(row) if rows.deliver is not None else identity, dispatched_ids=None
    ).failure
    assert failure is None, (
        f"{name}: a valid owed row failed in the production step or its handoffs ({failure!r}). Every edge case "
        f"would measure that failure, not its edge value; fix the binding's fakes or the example"
    )
    assert identity not in _selected(selection, rows.identity_of), (
        f"{name}: a valid owed row is still selected after the production step and its handoffs ran. Either "
        f"`execute` is not what serves the row, or the sweep re-reads served rows and does not fit these proofs"
    )
    return row


def assert_the_tick_dispatches_owed_rows_in_selection_order(
    name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows
) -> None:
    """
    POSITIVE CONTROL for the recorder: ``dispatched_ids`` reports what one production tick dispatched, in order.

    Order is each identity's first dispatch, so a tick that publishes one
    identity several times (a fan-out) records it once here.

    The liveness and poison cases read ``dispatched_ids`` after one tick, and
    the poison case arms whichever row leads ``selection``. A recorder that
    reads the table passes an aborting tick; a tick that walks another order
    is poisoned on a row it reaches last. Profile A rules both out with
    invariant 0b; the light contract has only this.
    """
    pair = _two_owed_in_selection_order(name, selection, rows.make_owed, rows.identity_of)
    premature = [identity for identity in rows.dispatched_ids() if identity in pair.rows]
    assert premature == [], (
        f"{name}: dispatched_ids() reported {premature} before any tick ran. A recorder of what production "
        f"dispatched is empty for rows no tick has reached; this one reads the selection or the table"
    )
    rows.run_tick()
    # First dispatch of each: a fan-out publishes one identity more than once (the email engine's two dispatchers).
    reached = list(dict.fromkeys(identity for identity in rows.dispatched_ids() if identity in pair.rows))
    assert reached == [pair.head, pair.behind], (
        f"{name}: one tick over two valid owed rows first dispatched {reached}; the selection orders them "
        f"{[pair.head, pair.behind]}. The liveness and poison cases need a recorder of what the tick dispatched, "
        f"and a tick that walks the order `due_work` declares"
    )


def _owed_row_is_handled(
    name: str,
    selection: Callable[[], Iterable[Any]],
    family: EdgeFamily,
    edge: CandidateEdge,
    rows: OwedRows,
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE,
) -> None:
    """Invariant 1 bound to an owed-row binding."""
    assert_database_legal_owed_row_is_handled(
        name=name,
        edge=edge,
        make_owed=rows.make_owed,
        selection=selection,
        identity_of=rows.identity_of,
        execute=rows.execute,
        run_tick=rows.run_tick,
        deliver=rows.deliver,
        dispatched_ids=rows.dispatched_ids,
        effect_calls_for=rows.effect_calls_for,
        edge_row=family.edge_row,
        edge_model=family.model,
        ends=ends,
    )


def _owed_row_does_not_block_the_next(
    name: str,
    selection: Callable[[], Iterable[Any]],
    family: EdgeFamily,
    edge: CandidateEdge,
    rows: OwedRows,
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE,
) -> None:
    """Invariant 2 bound to an owed-row binding; a stalled tick is not ended by anything, so ``ends`` is unread."""
    assert_inadmissible_owed_row_does_not_block_the_next(
        name=name,
        edge=edge,
        make_owed=rows.make_owed,
        selection=selection,
        identity_of=rows.identity_of,
        run_tick=rows.run_tick,
        dispatched_ids=rows.dispatched_ids,
        edge_row=family.edge_row,
        edge_model=family.model,
    )


def assert_the_loop_isolates_a_poisoned_row(name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows) -> None:
    """
    INVARIANT 12 on the light contract: one poisoned row first in selection order does not stall the next.

    The light contract has no row ages, so the proof reads the production
    order and poisons whichever owed row leads it. The oracle is the one
    profile A's ``assert_one_poisoned_identity_does_not_stall_the_tick`` runs
    (:func:`~pytest_obligation.poison.assert_poison_is_isolated`):
    the poison fired, *that* tick recorded the healthy row, the tick reported
    the injected failure, and the poisoned row is still selected. Only an
    isolation failure is a :class:`~pytest_obligation.poison.PoisonNotIsolated`,
    and a declared gap names which one it expects (``"<proof>[unreported]"``).

    A bound ``still_owed`` is checked against a row production served to
    completion before the tick, in the state that tick leaves: it must say
    that row is owed nowhere while it says the poisoned one is. One that
    answers "is anything owed" instead (email unpark's reaper selection is
    never empty while the healthy campaign's dispatcher is in flight) passes
    every dropped row; that is a binding failure, which no poison gap absorbs.
    """
    history = _poisoned_row_history(
        name, selection, rows, proof="assert_one_poisoned_identity_does_not_stall_the_tick", proves="does not stall"
    )
    assert_poison_is_isolated(name=name, run_tick=rows.run_tick, **history)


def assert_a_soft_time_limit_ends_the_loop(name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows) -> None:
    """
    INVARIANT 12b on the light contract: Celery's soft time limit in the leading row's step ends the tick there.

    The same history and ``poison=`` seam as
    :func:`assert_the_loop_isolates_a_poisoned_row`, run under
    :func:`~pytest_obligation.poison.stop_requests`
    so the armed seam raises the soft limit. The oracle
    (:func:`~pytest_obligation.poison.assert_a_stop_request_ends_the_tick`)
    requires the limit to escape the tick, the row behind not to have run, and
    the interrupted row to still be owed. A declared gap names the one failure
    it expects (``"<proof>[swallowed]"``).
    """
    history = _poisoned_row_history(
        name,
        selection,
        rows,
        proof="assert_a_soft_time_limit_ends_the_tick",
        proves="ends on Celery's soft time limit",
    )
    assert_a_stop_request_ends_the_tick(name=name, run_tick=rows.run_tick, **history)


def _poisoned_row_history(
    name: str, selection: Callable[[], Iterable[Any]], rows: OwedRows, *, proof: str, proves: str
) -> PoisonedHistory:
    """Two owed rows in production order, the leading one poisoned; the poison and stop-request cases share it."""
    assert rows.poison is not None, (
        f"{name}: no `poison=` on the owed-row binding, so the suite cannot prove that a loop whose leading row's "
        f"step raises {proves}. Bind the seam the tick calls per identity (integrations.celery.refusing_publication for a "
        f"broker publication), or declare `{proof}` as a gap for a loop known not to"
    )
    owned_next = rows.still_owed
    settled = _served_to_completion(name, selection, rows) if owned_next is not None else None
    pair = _two_owed_in_selection_order(name, selection, rows.make_owed, rows.identity_of)
    poisoned_row = pair.rows[pair.head]
    before = list(rows.dispatched_ids())
    return PoisonedHistory(
        poison=rows.poison(poisoned_row),
        # Only what this tick recorded counts, so an identity recorded earlier does not pass.
        progressed=lambda: pair.behind in new_entries(before, list(rows.dispatched_ids())),
        # The light contract declares no lifecycle: still selected, or owed by the selection the step handed it to.
        still_owed=(
            (lambda: _owed_next(name, owned_next, poisoned_row, settled))
            if owned_next is not None
            else (lambda: pair.head in _selected(selection, rows.identity_of))
        ),
    )


def _owed_next(name: str, still_owed: Callable[[Any], bool], row: Any, settled: Any) -> bool:
    owed = still_owed(row)
    # A truthy object (the row itself, a queryset) would pass every dropped row.
    assert isinstance(owed, bool), f"{name}: owed_rows.still_owed returned {type(owed).__name__}, not a bool"
    # BINDING CHECK: in the same state, a row production served to completion is owed nowhere.
    settled_owed = still_owed(settled)
    assert settled_owed is False, (
        f"{name}: owed_rows.still_owed reports a row the production step and its handoffs served to completion "
        f"as still owed (it returned {settled_owed!r}), in the same tick in which it is asked about the poisoned "
        f"row. It must say whether this row is owed by the selection the step handed it to; one that answers "
        f"whether anything is owed passes every dropped row"
    )
    return owed


#: A per-edge owed-row proof: ``(name, selection, family, edge, rows, ends)``.
OwedRowProof = Callable[[str, Callable[[], Iterable[Any]], EdgeFamily, CandidateEdge, OwedRows, FailureEnds], None]

#: The per-edge owed-row proofs both contracts generate, keyed by the invariant
#: name their case ids and gap keys use.
OWED_ROW_PROOFS: Mapping[str, OwedRowProof] = {
    assert_database_legal_owed_row_is_handled.__name__: _owed_row_is_handled,
    assert_inadmissible_owed_row_does_not_block_the_next.__name__: _owed_row_does_not_block_the_next,
}


@contextmanager
def worker_transaction() -> Iterator[None]:
    """
    One delivery, run so that a failed SQL statement in it does not abort the proof's own transaction.

    In autocommit (a transactional test) nothing is added: each statement
    already ends on its own. Inside an enclosing test transaction a failed
    statement would make every later query of the proof raise, so the delivery
    runs under a savepoint. What it wrote is kept, as autocommit keeps it, even
    when it raises; only a delivery that left the transaction aborted is rolled
    back to the savepoint, with the commit callbacks it registered.
    """
    if not connection.in_atomic_block:
        yield
        return
    savepoint = transaction.savepoint()
    try:
        yield
    finally:
        _end_delivery(savepoint)


def _end_delivery(savepoint: str) -> None:
    # PostgreSQL INERROR is 3: psycopg 2 exposes an int, psycopg 3 an IntEnum.
    aborted = int(connection.connection.info.transaction_status) == 3
    if aborted or connection.needs_rollback:
        # Django refuses every query, the rollback's own included, until its flag is cleared (as Atomic does).
        transaction.set_rollback(False)
        transaction.savepoint_rollback(savepoint)
    else:
        transaction.savepoint_commit(savepoint)


def assert_selected_owed_row_is_handled(
    *,
    name: str,
    row: Any,
    related: tuple[Model, ...],
    describe: str,
    selection: Callable[[], Iterable[Any]],
    identity_of: Callable[[Any], Any],
    execute: Callable[[Any], Any],
    deliver: Callable[[Any], Any] | None = None,
    dispatched_ids: Callable[[], list[Any]] | None = None,
    effect_calls_for: Callable[[Any], int] | None = None,
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE,
) -> None:
    """
    INVARIANT: one production delivery of a row the selection returns neither raises nor idles on it.

    The judgment both owed-row admissibility and selection completeness pass
    on a selected row, however it was made: ``related`` are rows the worker
    reads through it, so "unchanged" covers them too, and ``describe`` names
    what makes the row unusual (``"with status-blank ('')"``). ``ends`` is what
    the contract says ends a row whose chain raised after moving it out of the
    selection.
    """
    identity = identity_of(row)
    # ARRANGE: what the tick would publish for this row now, read after the edge write.
    delivery = deliver(row) if deliver is not None else identity
    before = _rows_as_persisted((row, *related))
    calls_before = effect_calls_for(row) if effect_calls_for is not None else 0
    try:
        served = serve_row(execute, delivery, dispatched_ids=dispatched_ids)
    except HandoffsNeverStop as endless:
        raise OwedRowNotHandled(
            f"{name}: delivering the row {describe} started a chain that {endless}; every tick would start it again"
        ) from endless
    failure, worked = served.failure, served.worked
    if effect_calls_for is not None and effect_calls_for(row) > calls_before:
        worked = True
    still_selected = identity in _selected(selection, identity_of)
    unchanged = still_selected and _rows_as_persisted((row, *related)) == before
    # INVARIANT ENFORCEMENT: a row the next tick hands over again must not have
    # raised (whatever the attempt stamped first), and must not have been handed
    # back untouched by a chain that did nothing; either repeats on every tick.
    if (failure is not None and still_selected) or (failure is None and unchanged and not worked):
        outcome = (
            f"{served.ran_in} raised {failure!r}" if failure is not None else f"{served.ran_in} did nothing at all"
        )
        left = "still selected" if failure is not None else "unchanged and still selected"
        raise OwedRowNotHandled(
            f"{name}: the selection returns a database-legal owed row {describe}, and "
            f"{outcome}, leaving the row {left}. The next tick hands it "
            f"the same row, so this repeats on every tick and the row holds a page slot a valid one needs. Exclude "
            f"the row in the selection, or make the worker settle, fail or retire it"
        ) from failure
    # INVARIANT ENFORCEMENT: a raise on a row the chain moved out of the
    # selection repeats once what moved it expires, or strands the row unfinished.
    if failure is not None and not ends.end(row):
        raise OwedRowNotHandled(
            f"{name}: {served.ran_in} raised {failure!r} on a database-legal owed row {describe} "
            f"after moving it out of the selection, and nothing ends it there: the row is in no "
            f"terminal state {'of the sweep' if ends.is_terminal is not None else '(this contract declares none)'} "
            f"and the contract claims no profile J to bound a repeat. Either what moved it expires (a claim, a lease, "
            f"a backoff) and recovery hands the same row to the same raise, or no selection looks at it again and it "
            f"stays unfinished. Exclude the row in the selection, end it in a terminal state instead of raising, or "
            f"bound the retry with profile J"
        ) from failure
