"""
A recovery selection must return every row its worker would act on (profile A and the light contract).

The owed-row proofs ask what the selection does with one valid owed row and
one edge value at a time. They never ask what it *skips*. A selection is a
predicate with several branches, and dropping one leaves every example the
adopter wrote still selected: the email reaper's respawn selection
(``chunks_awaiting_dispatch``) returns READY chunks of READY or RUNNING
campaigns, and narrowing it to RUNNING strands a built campaign whose first
dispatcher was lost. In a mutation audit that left the reaper, chunk and unpark
contracts green; only a handwritten test with a READY campaign failed. The
skipped branch was a state of a *related* row (the campaign), which neither the
light contract nor :class:`~.terminal_states.Lifecycle` enumerated.

This module generates that question from the declaration instead of from
hand-picked examples. It starts from a valid ``make_owed`` row, writes a state
combination and field values into it with an unvalidated ``update()``, the way
legacy writers and migrations leave rows, and lets production decide:

* **Selected** by the production selection: one production tick must dispatch
  it (when the binding has a tick and a recorder), so a tick that walks a
  narrower query than the one bound is caught too, and one delivery to the
  production worker, with every task it hands off to, must serve it. That is
  owed-row admissibility's judgment
  (:func:`~.owed_row_admissibility.assert_selected_owed_row_is_handled`): no
  raise on a row still selected, and not "nothing at all" on a row left
  unchanged. Every selected combination is therefore what an
  ``OwedWorkVariant`` proves for one hand-built row.
* **Not selected**, now or at any recovery horizon: the production worker, if a
  message for the row did arrive, must not act on it. Acting is invariant 2c's
  notion of a new obligation, judged on the worker *and* the chain it hands
  off to (a reaper step that only publishes a dispatcher acts only if the
  dispatcher does): a row created anywhere, a declared state moved (the row's
  own or a related row's, the row deleted), an external call counted by
  ``effect_calls_for``, a retry scheduled, a row newly selectable by the
  production selection, or a raise. A row the selection skips and the worker
  acts on is a missed owed branch: nothing recovers it after a lost message.
  Plain updates of existing rows are progress, as in 2c.
* **Excluded** with a reason (``excluded_states``, the :class:`Lifecycle` key
  syntax, combinations allowed): never delivered, but the production selection
  must not return it. An exclusion the selection returns is owed work, not an
  exclusion; that is invariant 2b's refusal lifted to combinations.

A write the database refuses (a CHECK constraint, a value out of range) cannot
exist in a row; the draw is rejected, not failed.

**What is drawn.** Each declared state path (``"state"``, ``"campaign__status"``)
takes every value of its ``choices``; every *combination* of them is a fixed
example when there are at most :data:`_PRODUCT_LIMIT`, each value of each path
on its own otherwise. Then the selected model's other fields that the
selection's WHERE clause compares are drawn from
:func:`hypothesis.extra.django.from_field` (time fields within two years of
now), with the deterministic edge catalog
(:mod:`~pytest_obligation.integrations.django.edge_values`) as fixed
examples (a state field's own edges among them: blank, whitespace, a value
outside its choices), and Hypothesis spends its budget on combinations of the
two. Fixed examples do not spend the budget, so the enumerated combinations run
on every run. Values outside the choices are not combined with every related
state: a retired value in a combination nothing reaches would only need an
exclusion nobody can name.

**Cost and determinism.** ``derandomize=True`` and no example database: the
same declaration draws the same rows on every machine. Each example runs in
its own transaction, rolled back, with the binding entered afresh, so a
recorder, a provider fake or a row from one example never reaches the next.
PR CI spends :data:`PR_EXAMPLES` generated examples per contract;
``--due-work-explore=deep`` spends :data:`EXTENDED_EXAMPLES`.

**Known findings.** A contract under ``Adoption.LEGACY`` declares a defect it
cannot fix yet as a gap on one combination,
``"assert_selection_is_complete[campaign__status:RUNNING,state:ACCEPTED]"``: a
strict xfail that runs exactly that combination and expects
:class:`SelectionIncomplete` (or :class:`~.owed_row_admissibility.OwedRowNotHandled`),
while the search assumes it away. The bare proof name is not a gap: one
waiver would hide every combination.

**What this cannot see.** States that are not ``choices`` (a counter, a
timestamp) are drawn as fields, not enumerated. Related rows contribute only
the state paths declared, never their other fields, and the worker's view of a
related row is otherwise the example's. An inline tick bound as the worker (no
per-identity step) never touches a row it does not select, so the skipped
branch is true by construction there and only the selected branch measures
anything. A selection aged by SQL ``NOW()`` sees no horizon pass (2c's limit).
A worker that acts on an unselected row only through a provider the
``effect_calls_for`` fake does not count, or only by updating rows that already
exist, passes. A green run is evidence for the combinations enumerated and
the values drawn, not for every row in a production table.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any

from django.db import DataError, IntegrityError, models, transaction
from django.db.models import Model, QuerySet
from django.test import TestCase
from django.utils import timezone
from hypothesis import HealthCheck, Phase, assume, example, given, note, settings
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument, ResolutionFailed
from hypothesis.extra.django import from_field
from pydantic import Field

from pytest_obligation.binding import is_real_reason
from pytest_obligation.host import HandoffsNeverStop
from pytest_obligation.integrations.clocks import time_machine_clock as frozen_scheduler_clock
from pytest_obligation.integrations.django.edge_values import CandidateEdge, database_legal_edges, model_edges
from pytest_obligation.integrations.django.lifecycle_states import (
    StatePath,
    filtered_fields,
    lifecycle_paths,
    new_entries,
)
from pytest_obligation.integrations.django.owed_rows import (
    NOTHING_ENDS_A_FAILURE,
    FailureEnds,
    OwedRowNotHandled,
    OwedRows,
    RowExecution,
    assert_selected_owed_row_is_handled,
    failure_ends_of_sweep,
    owed_rows_of_sweep,
    serve_row,
    worker_transaction,
)
from pytest_obligation.profiles.automatic_recovery import DueWorkSweep

#: The case id, and the prefix of a declared per-combination gap.
PROOF_NAME = "assert_selection_is_complete"

#: Generated examples per contract in PR CI, beyond the fixed ones.
PR_EXAMPLES = 25
#: Generated examples under ``--due-work-explore=deep``.
EXTENDED_EXAMPLES = 200

#: Above this many state combinations, each value is a fixed example on its own and Hypothesis draws combinations.
_PRODUCT_LIMIT = 64

#: How far from now drawn time fields reach.
_TIME_SPAN = timedelta(days=730)

#: Horizons past now at which a skipped row may still become selected: work not yet due is not skipped work.
#: The last is past every drawn time, so a row due at a drawn future instant is selected at it.
_HORIZONS = (timedelta(hours=1), timedelta(days=1), timedelta(days=30), _TIME_SPAN + timedelta(days=1))

#: Generated examples the running case spends; the suite's budget fixture sets it from ``--due-work-explore``.
EXAMPLES: ContextVar[int] = ContextVar("due_work_selection_completeness_examples", default=PR_EXAMPLES)


class SelectionIncomplete(AssertionError):
    """
    The invariant failed: the selection skips a row its worker acts on, or returns one declared excluded.

    A declared per-combination gap expects exactly this (or
    :class:`OwedRowNotHandled` for a selected row), so a broken binding still fails.
    """


class CompletenessBinding(RowExecution):
    """
    What one example reads: the production selection, the loop behind it, and the declared states.

    ``DueWorkContract`` projects it from its sweep and :class:`Lifecycle`;
    ``ScheduledSelection`` from its ``OwedRows`` and its own ``state_fields``
    and ``excluded_states``; a work-table discovery from its candidate query and
    per-owner derivation step.
    """

    name: str
    #: REAL PRODUCTION: the unbounded selection the tick pages through.
    selection: Callable[[], Iterable[Any]]
    #: REAL PRODUCTION: one tick; with ``dispatched_ids``, a selected row must be one the tick dispatches.
    run_tick: Callable[[], Any] | None = None
    #: Lifecycle state paths of the selected model, related paths allowed.
    state_fields: tuple[str, ...] = ()
    #: Lifecycle key syntax; a combination joins ``path:value`` conditions with ``,`` (``|`` between values).
    excluded_states: Mapping[str, str] = Field(default_factory=dict)
    #: Compared, non-state columns held at the producer's value, with a reason.
    #: Use for routing ownership (for example a worker's configured backend),
    #: never to claim completeness across values this proof does not exercise.
    fixed_fields: Mapping[str, str] = Field(default_factory=dict)
    #: What ends a selected row whose chain raised after moving it out of the selection (owed-row
    #: admissibility's rule); projected by the contract, never declared by the adopter.
    ends: FailureEnds = NOTHING_ENDS_A_FAILURE

    @classmethod
    def of_rows(
        cls,
        name: str,
        selection: Callable[[], Iterable[Any]],
        rows: OwedRows,
        *,
        state_fields: tuple[str, ...],
        excluded_states: Mapping[str, str],
        fixed_fields: Mapping[str, str] | None = None,
    ) -> CompletenessBinding:
        """The owed-row loop both contracts already bind, with the states its selection decides on."""
        return cls(
            name=name,
            selection=selection,
            make_owed=rows.make_owed,
            execute=rows.execute,
            identity_of=rows.identity_of,
            deliver=rows.deliver,
            effect_calls_for=rows.effect_calls_for,
            dispatched_ids=rows.dispatched_ids,
            run_tick=rows.run_tick,
            state_fields=state_fields,
            excluded_states=excluded_states,
            fixed_fields=fixed_fields or {},
        )


def completeness_of_sweep(
    sweep: DueWorkSweep, model: type[Model] | None, *, retries_bounded: bool
) -> CompletenessBinding:
    """A profile-A sweep with its :class:`Lifecycle`, as owed-row admissibility projects it."""
    rows = owed_rows_of_sweep(sweep, model)
    assert sweep.lifecycle is not None  # owed_rows_of_sweep requires it
    return CompletenessBinding.of_rows(
        sweep.name,
        sweep.due_work,
        rows,
        state_fields=sweep.lifecycle.state_fields,
        excluded_states=sweep.lifecycle.excluded_states,
    ).model_copy(update={"ends": failure_ends_of_sweep(sweep, retries_bounded=retries_bounded)})


@dataclass(frozen=True)
class StateCombination:
    """
    The rows one ``excluded_states`` key or gap covers: every condition holds.

    A condition is ``(path, values)``; ``path`` ``None`` is a bare value, which
    holds when any state path has it (the :class:`Lifecycle` meaning).
    """

    key: str
    conditions: tuple[tuple[str | None, frozenset[str]], ...]

    def matches(self, states: Mapping[str, str | None]) -> bool:
        return all(
            (path is None and any(value in allowed for value in states.values()))
            or (path is not None and states.get(path) in allowed)
            for path, allowed in self.conditions
        )

    def assignment(self) -> dict[str, str]:
        """The one row a gap names: each path at its one value (validated by :func:`gap_combination`)."""
        return {path: next(iter(allowed)) for path, allowed in self.conditions if path is not None}


def parse_combination(key: str, paths: Mapping[str, StatePath]) -> StateCombination:
    """Resolve declared choices and exact ``path:@edge_kind`` catalog aliases.

    Aliases name database-legal values that cannot be written literally in the
    grammar (for example blank and whitespace). They never waive an edge family;
    each resolves to the same single concrete value the edge catalog generates.
    A real model choice takes precedence over an alias with the same spelling.
    """
    conditions: list[tuple[str | None, frozenset[str]]] = []
    for part in key.split(","):
        path, _, values = part.strip().rpartition(":")
        allowed = frozenset(value.strip() for value in values.split("|"))
        if path:
            assert path in paths, f"{key!r} names {path!r}, which is not a declared state path {sorted(paths)}"
            state = paths[path]
            aliases = {f"@{edge.kind}": str(edge.value) for edge in database_legal_edges(state.field)}
            unknown = allowed - set(state.choices) - aliases.keys()
            assert not unknown, (
                f"{key!r}: {sorted(unknown)} are not values of {path} {state.choices} or its edge aliases"
            )
            allowed = frozenset(value if value in state.choices else aliases[value] for value in allowed)
        else:
            assert len(allowed) == 1 and any(next(iter(allowed)) in state.choices for state in paths.values()), (
                f"{key!r} names no value of any declared state path"
            )
        conditions.append((path or None, allowed))
    return StateCombination(key=key, conditions=tuple(conditions))


def gap_key(combination: Mapping[str, str]) -> str:
    """``assert_selection_is_complete[path:value,...]``, the paths in sorted order."""
    return f"{PROOF_NAME}[{','.join(f'{path}:{value}' for path, value in sorted(combination.items()))}]"


def gap_combination(gap: str) -> str | None:
    """The combination inside a gap key, or None when ``gap`` is not a selection-completeness gap."""
    prefix = f"{PROOF_NAME}["
    if not (gap.startswith(prefix) and gap.endswith("]")):
        return None
    inner = gap[len(prefix) : -1]
    parts = [part.partition(":") for part in inner.split(",")]
    assert inner and all(path and value and "|" not in value for path, _, value in parts), (
        f"{gap!r}: a selection-completeness gap names one value per state path, "
        f"'{PROOF_NAME}[path:value,path:value]'; a gap on the whole proof would hide every combination"
    )
    return inner


@dataclass(frozen=True)
class _Declaration:
    """The binding's declaration, resolved against the selected model once per case."""

    model: type[Model]
    paths: dict[str, StatePath]
    fields: tuple[models.Field[Any, Any], ...]
    exclusions: tuple[tuple[StateCombination, str], ...]


def _declaration(binding: CompletenessBinding) -> _Declaration:
    selection = binding.selection()
    assert isinstance(selection, QuerySet), "selection completeness requires a Django QuerySet"
    model = selection.model
    paths = lifecycle_paths(selection, binding.state_fields, name=binding.name)
    thin = sorted(key for key, reason in binding.excluded_states.items() if not is_real_reason(reason))
    assert not thin, f"{binding.name}: excluded_states {thin} carry no real reason"
    compared = filtered_fields(selection.query.where, model)
    own_states = {state.field.name for state in paths.values() if not state.relations}
    fixed = set(binding.fixed_fields)
    valid_fixed = {
        field.name
        for field in model._meta.concrete_fields
        if field.name in compared and field.name not in own_states and not field.primary_key and not field.is_relation
    }
    assert fixed <= valid_fixed, (
        f"{binding.name}: fixed_fields must name compared non-state columns: {sorted(fixed - valid_fixed)}"
    )
    assert all(is_real_reason(reason) for reason in binding.fixed_fields.values()), (
        f"{binding.name}: fixed_fields require substantive reasons"
    )
    drawn = tuple(
        model_field
        for model_field in model._meta.concrete_fields
        if model_field.name in compared
        and model_field.name not in own_states
        and model_field.name not in fixed
        and not model_field.primary_key
        and not model_field.is_relation
        and _strategy(model_field, timezone.now()) is not None
    )
    exclusions = tuple((parse_combination(key, paths), reason) for key, reason in binding.excluded_states.items())
    return _Declaration(model=model, paths=paths, fields=drawn, exclusions=exclusions)


def _strategy(model_field: models.Field[Any, Any], anchor: datetime) -> st.SearchStrategy[Any] | None:
    """
    Values the column can hold; ``None`` for a field Hypothesis cannot draw.

    A time is drawn as an offset from ``anchor`` (the case's start, whole
    seconds): what a selection compares is the distance from now, and an
    offset keeps the draws the same from one run to the next.
    """
    if isinstance(model_field, (models.DateTimeField, models.DateField)):
        moments = st.timedeltas(min_value=-_TIME_SPAN, max_value=_TIME_SPAN).map(lambda offset: anchor + offset)
        values: st.SearchStrategy[Any] = (
            moments if isinstance(model_field, models.DateTimeField) else moments.map(lambda moment: moment.date())
        )
        return st.none() | values if model_field.null else values
    try:
        values = from_field(model_field)
    except (InvalidArgument, ResolutionFailed):
        if not isinstance(model_field, models.FileField):
            return None
        values = st.text(max_size=model_field.max_length or 100)
    # PostgreSQL text cannot hold NUL, and the driver refuses it before the database could.
    return values.filter(lambda value: not (isinstance(value, str) and "\x00" in value))


#: One drawn row: state path or field attname -> the value written into it.
Assignment = dict[str, Any]


def _fixed_examples(declaration: _Declaration, gaps: tuple[StateCombination, ...]) -> list[Assignment]:
    """Every state combination (or each state value), then each catalog edge of a drawn field or own state."""
    paths = list(declaration.paths.values())
    if not paths:
        states: list[Assignment] = []
    elif _product_size(paths) <= _PRODUCT_LIMIT:
        states = [
            dict(zip((state.path for state in paths), values, strict=True))
            for values in product(*(state.choices for state in paths))
        ]
    else:
        states = [{state.path: value} for state in paths for value in state.choices]
    states = [assignment for assignment in states if not any(gap.matches(assignment) for gap in gaps)]
    edge_fields = {model_field.attname for model_field in declaration.fields} | {
        state.field.attname for state in paths if not state.relations
    }
    edges: list[Assignment] = [
        {_edge_key(declaration, edge): edge.value}
        for edge in model_edges(declaration.model)
        if edge.field in edge_fields
    ]
    return states + edges


def _edge_key(declaration: _Declaration, edge: CandidateEdge) -> str:
    """A catalog edge on an own state field is written through its state path, so states read it back."""
    for state in declaration.paths.values():
        if not state.relations and state.field.attname == edge.field:
            return state.path
    return edge.field


def _product_size(paths: list[StatePath]) -> int:
    size = 1
    for state in paths:
        size *= len(state.choices)
    return size


def _assignments(declaration: _Declaration) -> st.SearchStrategy[Assignment]:
    """A value of every state path's choices, and values for some of the compared fields."""

    # Built once per case: a strategy whose bounds moved between examples would draw a different row.
    anchor = timezone.now().astimezone(UTC).replace(microsecond=0)
    strategies = {model_field.attname: _strategy(model_field, anchor) for model_field in declaration.fields}

    @st.composite
    def draw(draw_: st.DrawFn) -> Assignment:
        assignment: Assignment = {}
        for state in declaration.paths.values():
            assignment[state.path] = draw_(st.sampled_from(state.choices))
        for attname, strategy in strategies.items():
            if strategy is not None and draw_(st.booleans()):
                assignment[attname] = draw_(strategy)
        return assignment

    return draw()


def _write(binding: CompletenessBinding, declaration: _Declaration, row: Model, assignment: Assignment) -> bool:
    """ARRANGE: the assignment written without validation; False when the database refuses it."""
    writes: dict[tuple[type[Model], Any], dict[str, Any]] = {}
    for key, value in assignment.items():
        state = declaration.paths.get(key)
        holder = state.holder(row) if state is not None else row
        column = state.field.attname if state is not None else key
        writes.setdefault((type(holder), holder.pk), {})[column] = value
    try:
        with transaction.atomic():
            for (model, pk), values in writes.items():
                updated = model._base_manager.filter(pk=pk).update(**values)
                assert updated == 1, f"{binding.name}: {model._meta.label_lower} {pk} vanished before the write"
    except (DataError, IntegrityError):
        return False
    row.refresh_from_db()
    return True


def _states(declaration: _Declaration, row: Model) -> dict[str, str | None]:
    """Each declared state as the database holds it; None for every path once the row is gone."""
    values = type(row)._base_manager.filter(pk=row.pk).values(*declaration.paths).first()
    return {path: None if values is None or values[path] is None else str(values[path]) for path in declaration.paths}


def _describe(assignment: Assignment) -> str:
    return "with " + (", ".join(f"{key}={value!r}" for key, value in sorted(assignment.items())) or "nothing changed")


def _selected(binding: CompletenessBinding) -> set[Any]:
    return {binding.identity_of(row) for row in binding.selection()}


def _selected_later(binding: CompletenessBinding, identity: Any) -> bool:
    """Whether the selection returns the row at some recovery horizon: aged work is not skipped work."""
    base = timezone.now()
    for horizon in _HORIZONS:
        with frozen_scheduler_clock(base + horizon):
            if identity in _selected(binding):
                return True
    return False


def _acts_on(binding: CompletenessBinding, declaration: _Declaration, row: Model) -> list[str]:
    """
    Deliver a skipped row to the production worker and the chain it hands off to; what they did that owes work.

    Invariant 2c's obligations, judged on the whole chain: a publication the
    chain then delivers is judged by what its task did, not counted itself.
    """
    identity = binding.identity_of(row)
    delivery = binding.deliver(row) if binding.deliver is not None else identity
    states_before = _states(declaration, row)
    calls_before = binding.effect_calls_for(row) if binding.effect_calls_for is not None else 0
    selected_before = _selected(binding)
    acted: list[str] = []
    try:
        served = serve_row(binding.execute, delivery, dispatched_ids=None)
    except HandoffsNeverStop as endless:
        return [f"started a handoff chain that {endless}"]
    if served.failure is not None:
        acted.append(f"{served.ran_in} raised {served.failure!r}")
    if served.created:
        acted.append(f"created rows {list(served.created)}")
    states_after = _states(declaration, row)
    if states_after != states_before:
        acted.append(f"moved its states from {states_before} to {states_after}")
    if binding.effect_calls_for is not None and binding.effect_calls_for(row) > calls_before:
        acted.append("made an external call for it")
    if newly := sorted(_selected(binding) - selected_before, key=repr):
        acted.append(f"made rows newly selected {newly}")
    return acted


def _assert_the_tick_dispatches(binding: CompletenessBinding, identity: Any, describe: str) -> None:
    """
    A selected row is one production tick dispatches: the tick walks the selection, not a narrower copy.

    The tick's commit callbacks run, so a dispatch published after commit is
    recorded; a raise is allowed (a loud tick), a skipped row is not.
    """
    if binding.run_tick is None or binding.dispatched_ids is None:
        return
    before = list(binding.dispatched_ids())
    error: Exception | None = None
    try:
        with TestCase.captureOnCommitCallbacks(execute=True), worker_transaction():
            binding.run_tick()
    except Exception as raised:  # noqa: BLE001 - a loud tick is allowed; leaving the row behind is not
        error = raised
    # INVARIANT ENFORCEMENT: what the selection returns, the tick dispatches.
    if identity not in new_entries(before, list(binding.dispatched_ids())):
        raise SelectionIncomplete(
            f"{binding.name}: the production selection returns a row {describe}, and one production tick did not "
            f"dispatch it{f' (the tick raised {error!r})' if error is not None else ''}. The tick reads another "
            f"query than the one this contract binds, so the branch the selection adds is recovered by nobody"
        ) from error


def _judge(binding: CompletenessBinding, declaration: _Declaration, row: Model, assignment: Assignment) -> str:
    """Selected rows are served, skipped rows are left alone, excluded rows are skipped; returns the verdict."""
    identity = binding.identity_of(row)
    states = _states(declaration, row)
    describe = _describe(assignment)
    selected = identity in _selected(binding)
    for combination, reason in declaration.exclusions:
        if combination.matches(states):
            # INVARIANT ENFORCEMENT: an excluded combination is one the selection never returns.
            if selected or _selected_later(binding, identity):
                raise SelectionIncomplete(
                    f"{binding.name}: the production selection returns a row {describe} (states {states}), which "
                    f"excluded_states[{combination.key!r}] declares owes nothing ({reason}). A row the selection "
                    f"recovers owes work: drop the exclusion and let the worker serve it, or exclude it in the "
                    f"selection"
                )
            return "excluded"
    if selected:
        _assert_the_tick_dispatches(binding, identity, f"{describe} (states {states})")
        if identity in _selected(binding):  # an inline tick has served it already
            assert_selected_owed_row_is_handled(
                name=binding.name,
                row=row,
                related=tuple(state.holder(row) for state in declaration.paths.values() if state.relations),
                describe=f"{describe} (states {states})",
                selection=binding.selection,
                rows=binding,
                ends=binding.ends,
            )
        return "selected"
    if _selected_later(binding, identity):
        return "selected later"
    # INVARIANT ENFORCEMENT: a row the selection never returns must owe nothing to its worker.
    if acted := _acts_on(binding, declaration, row):
        raise SelectionIncomplete(
            f"{binding.name}: the production selection skips a row {describe} (states {states}), and the "
            f"production worker, delivered it, {'; '.join(acted)}. Nothing recovers that work after a lost "
            f"message, so the selection is missing an owed branch. Select the row, or, when it owes nothing, make "
            f"the worker leave it alone; if the combination is unreachable or another recovery owns it, declare it "
            f"in excluded_states with the reason"
        )
    return "skipped"


@contextmanager
def _example(*, commits: bool) -> Iterator[None]:
    """
    One example's database writes, undone when it ends however it ends.

    A binding whose tick or worker requires autocommit (a transactional
    contract) cannot run inside a transaction: its examples commit, and the
    test's teardown removes them. Each such example deletes the rows of the
    selected model it created (:func:`_new_rows_deleted`), so a row an earlier
    example left selected cannot fill the page a later one's tick reads.
    """
    if commits:
        yield
        return
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


@contextmanager
def _new_rows_deleted(model: type[Model], *, commits: bool) -> Iterator[None]:
    """A committing example's rows of the selected model, deleted when it ends; nothing to do when it rolls back."""
    if not commits:
        yield
        return
    before = set(model._base_manager.values_list("pk", flat=True))
    try:
        yield
    finally:
        model._base_manager.exclude(pk__in=before).delete()


def _run_one(
    enter: Callable[[], AbstractContextManager[CompletenessBinding]],
    assignment: Assignment,
    gaps: tuple[StateCombination, ...],
    *,
    commits: bool,
) -> str:
    with _example(commits=commits), enter() as binding:
        declaration = _declaration(binding)
        with _new_rows_deleted(declaration.model, commits=commits):
            return _run_declared(binding, declaration, assignment, gaps)


def _run_declared(
    binding: CompletenessBinding,
    declaration: _Declaration,
    assignment: Assignment,
    gaps: tuple[StateCombination, ...],
) -> str:
    row = binding.make_owed()
    if not _write(binding, declaration, row, assignment):
        return "rejected"
    if any(gap.matches(_states(declaration, row)) for gap in gaps):
        # A declared gap runs as its own strict xfail; the search leaves its rows alone.
        return "declared gap"
    return _judge(binding, declaration, row, assignment)


def assert_selection_is_complete(
    enter: Callable[[], AbstractContextManager[CompletenessBinding]],
    *,
    gaps: tuple[str, ...] = (),
    commits: bool = False,
) -> Mapping[str, int]:
    """
    INVARIANT: every database-legal row is served when selected, left alone when skipped, skipped when excluded.

    ``enter`` yields a fresh :class:`CompletenessBinding` per example; each
    example runs in its own rolled-back transaction, or commits when
    ``commits`` says the binding needs autocommit. ``gaps`` are declared
    per-combination gap keys, which the search assumes away (each runs as its
    own strict xfail through :func:`assert_declared_gap_still_fails`).
    Returns how many examples ended each way (``selected``, ``skipped``,
    ``selected later``, ``excluded``, ``rejected``, ``declared gap``).
    """
    with _example(commits=commits), enter() as binding:
        declaration = _declaration(binding)
        name = binding.name
        # POSITIVE CONTROL: the unmodified owed example is selected and served,
        # so a skipped row below is skipped by the selection, not by a broken example.
        with _new_rows_deleted(declaration.model, commits=commits):
            row = binding.make_owed()
            assert binding.identity_of(row) in _selected(binding), (
                f"{name}: the owed example is not selected before anything is written into it, so nothing below "
                f"would be measured"
            )
    gap_combinations = tuple(
        parse_combination(combination, declaration.paths)
        for combination in (gap_combination(gap) for gap in gaps)
        if combination is not None
    )
    # The unmodified example first: selected, so it must be served.
    fixed = [{}, *_fixed_examples(declaration, gap_combinations)]
    verdicts: dict[str, int] = {}

    def check(assignment: Assignment) -> None:
        note(f"{name}: {_describe(assignment)}")
        verdict = _run_one(enter, assignment, gap_combinations, commits=commits)
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        # A row the database refuses cannot exist; a declared gap is its own case.
        assume(verdict not in ("rejected", "declared gap"))

    budget = settings(
        max_examples=EXAMPLES.get(),
        derandomize=True,
        database=None,
        deadline=None,
        phases=(Phase.explicit, Phase.generate, Phase.shrink),
        report_multiple_bugs=False,
        suppress_health_check=(HealthCheck.too_slow, HealthCheck.filter_too_much),
        print_blob=False,
    )
    search = given(_assignments(declaration))(check)
    for assignment in reversed(fixed):
        search = example(assignment)(search)
    budget(search)()
    assert verdicts.get("skipped", 0) + verdicts.get("excluded", 0) > 0 or not declaration.paths, (
        f"{name}: no drawn row was skipped by the selection ({verdicts}), so the missed-branch half measured "
        f"nothing; the declared states cannot leave the selection"
    )
    return verdicts


def assert_declared_gap_still_fails(
    enter: Callable[[], AbstractContextManager[CompletenessBinding]], gap: str, *, commits: bool = False
) -> None:
    """A declared per-combination gap: that exact row must still fail the invariant (run as a strict xfail)."""
    combination = gap_combination(gap)
    assert combination is not None, f"{gap!r} is not a selection-completeness gap"
    with _example(commits=commits), enter() as binding:
        declaration = _declaration(binding)
        assignment = parse_combination(combination, declaration.paths).assignment()
        with _new_rows_deleted(declaration.model, commits=commits):
            row = binding.make_owed()
            assert _write(binding, declaration, row, assignment), (
                f"{binding.name}: the database refuses {gap}, so no row can be in it; drop the gap"
            )
            _judge(binding, declaration, row, assignment)


#: What a declared per-combination gap may raise; anything else (a broken binding) still fails it.
GAP_FAILURES: tuple[type[AssertionError], ...] = (SelectionIncomplete, OwedRowNotHandled)
