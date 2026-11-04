"""
Cost contracts: the database round trips a path sends, named by what each does, held to a baseline.

A count of statements hides a swap. Removing a clock read and adding a per-row
lookup leaves the count unchanged and makes the path slower. So each statement
is named by its *shape*: what it does (read, count, lock, update, insert, delete,
transaction control) to which table. A contract is the multiset of those
shapes. Shapes, unlike SQL text, stay the same across database and ORM
versions, so a committed baseline does not churn when the ORM changes its
quoting or aliases.

Three measurements cover a polling or delivery path:

* :func:`statement_shapes` — everything one call sends, for example an idle
  recovery tick or one delivery from claim to settlement.
* :func:`marginal_statement_shapes` — what one more owed row adds to a tick,
  exactly: ``(cost(large) - cost(small)) / (large - small)``. A per-row query
  (the N+1 a bounded page hides) appears here and nowhere else.
* :func:`assert_statement_cost` — compare a measurement with the committed
  baseline. Any difference fails: more statements is a regression, fewer is a
  saving the baseline must keep, so it ratchets. Record or lower an entry with
  ``OBLIGATION_COST_BASELINE=update`` (without xdist workers).

The host's :class:`~pytest_obligation.host.SelectionInspector` captures the
statements, so the core stays framework-free. Celery beat sweeps, RQ or
procrastinate jobs, DBOS steps and plain Django views all have a cost a
contract can hold, as long as the database they use has an inspector.

Canonical doc: docs/cost-contracts.md
"""

import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from pytest_obligation._internal.baselines import refuse_concurrent_update, write_baseline, yaml_module
from pytest_obligation._internal.sql_shapes import UnclassifiedStatement as UnclassifiedStatement
from pytest_obligation._internal.sql_shapes import statement_shape as statement_shape
from pytest_obligation.host import SelectionInspector, current_host

#: Where the cost baseline lives, relative to the pytest root.
COST_BASELINE = Path("obligation_cost_baseline.yaml")

#: Set to ``update`` to record each measured contract instead of checking it.
COST_UPDATE_ENVIRONMENT = "OBLIGATION_COST_BASELINE"

# Absolute, because the header is written into adopters' repositories.
_DOC = "https://github.com/gigaverse-app/pytest-obligation/blob/main/package/docs/cost-contracts.md"
_HEADER = f"""\
# Cost contracts: the database statements each named path sends, by shape.
#
# A test fails when a path sends a statement its entry does not list (a regression) or no
# longer sends one it does (a saving the entry must keep). Record or lower entries with
# `{COST_UPDATE_ENVIRONMENT}=update pytest -p no:xdist <tests>` and review the diff: it is
# the cost change of the PR.
#
# Canonical doc: {_DOC}
"""


def statement_inspector(capability: str, selection: object | None = None) -> SelectionInspector:
    """
    The inspector that captures a path's statements.

    Statements are a property of the connection rather than of one selection,
    so a proof without a selection uses the host's only inspector; with
    several configured, the caller names the selection whose database is meant.
    """
    if selection is not None:
        return current_host().inspector_for(selection, capability=capability)
    inspectors = current_host().selection_inspectors
    assert len(inspectors) == 1, (
        f"{capability} counts database statements and needs exactly one SelectionInspector to ask, "
        f"and the configured host has {len(inspectors)}. "
        + (
            "Pass `selection=` to choose the database whose statements are counted"
            if inspectors
            else "Use an integration's host (for example pytest_obligation.integrations.django.django_host) "
            "or add an inspector"
        )
    )
    return inspectors[0]


def statement_shapes(run: Callable[[], object], *, selection: object | None = None, strict: bool = False) -> list[str]:
    """
    The shape of every statement ``run`` sends, in order, transaction control included.

    ``strict`` raises :class:`UnclassifiedStatement` for a statement that has no
    verb-and-table shape, instead of naming it by its first words.
    """
    inspector = statement_inspector("statement_shapes", selection)
    return [statement_shape(sql, strict=strict) for sql in inspector.statements_during(run)]


def marginal_statement_shapes(
    *,
    make_owed: Callable[[], Any],
    run_tick: Callable[[], Any],
    remaining: Callable[[], int] | None,
    small: int = 1,
    large: int = 3,
    selection: object | None = None,
    strict: bool = False,
) -> Counter[str]:
    """
    The statements one more owed row adds to a tick, as the difference of two backlog sizes.

    Makes ``small`` rows owed and ticks, then ``large`` rows and ticks, so each
    tick must take what it finds (claim, dispatch or settle it); ``large`` must
    fit in one page. Fails when the difference is not a whole per-row cost or
    the larger backlog skips a statement the smaller one sends, either of which
    means the two ticks did different work rather than more of the same.

    A result can legitimately be empty: a set-based tick costs the same for
    any backlog. So can a tick that took nothing, which proves nothing, so
    ``remaining`` is required: how many rows made owed are still waiting, and
    every tick must leave none. Pass ``None`` only when another proof already
    shows the tick takes its rows. Two sizes measure a linear per-row cost; a
    cost that grows faster than the backlog reads as a larger per-row cost.
    """
    assert 0 <= small < large, f"need 0 <= small < large, got small={small}, large={large}"
    costs: list[Counter[str]] = []
    for size in (small, large):
        for _ in range(size):
            make_owed()
        costs.append(Counter(statement_shapes(run_tick, selection=selection, strict=strict)))
        left = remaining() if remaining is not None else 0
        assert left == 0, (
            f"a tick over {size} owed rows left {left} waiting, so its cost is not the cost of taking them; "
            "make each owed row dispatchable now and fit the rows in one page"
        )
    skipped = costs[0] - costs[1]
    assert not skipped, f"a tick over {large} rows skipped statements a tick over {small} sent: {dict(skipped)}"
    rows = large - small
    extra = costs[1] - costs[0]
    uneven = {shape: count for shape, count in extra.items() if count % rows}
    assert not uneven, (
        f"{dict(extra)} more statements for {rows} more rows is not a whole per-row cost "
        f"(uneven: {uneven}); each tick must take exactly the rows made owed before it"
    )
    return Counter({shape: count // rows for shape, count in extra.items()})


class CostEntry(BaseModel):
    """One contract's recorded statements: shape -> how many."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    contract: str = Field(min_length=1)
    statements: dict[str, PositiveInt]


class CostBaseline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    costs: list[CostEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_entry_per_contract(self) -> Self:
        names = [entry.contract for entry in self.costs]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ValueError(f"cost contracts recorded more than once: {duplicated}")
        return self

    def of(self, contract: str) -> Counter[str] | None:
        return next((Counter(entry.statements) for entry in self.costs if entry.contract == contract), None)


def load_cost_baseline(root: Path, *, baseline: Path = COST_BASELINE) -> CostBaseline:
    path = root / baseline
    if not path.exists():
        return CostBaseline()
    document = yaml_module("YAML cost baselines").safe_load(path.read_text(encoding="utf-8")) or {}
    return CostBaseline.model_validate(document)


def assert_statement_cost(
    contract: str,
    statements: Iterable[str] | Mapping[str, int],
    *,
    root: Path,
    baseline: Path = COST_BASELINE,
) -> None:
    """
    Hold ``contract`` to exactly the statements its baseline entry records.

    ``statements`` are shapes, one per statement as :func:`statement_shapes`
    returns them, or a shape -> count mapping such as the ``Counter``
    :func:`marginal_statement_shapes` returns. A missing entry fails until it
    is recorded, so a new contract cannot pass by being absent.
    """
    # Iterating a mapping yields each shape once; take its counts as they are.
    measured = +Counter(dict(statements)) if isinstance(statements, Mapping) else Counter(statements)
    _VISITED.append(contract)
    if os.environ.get(COST_UPDATE_ENVIRONMENT) == "update":
        refused = refuse_concurrent_update(COST_UPDATE_ENVIRONMENT)
        assert refused is None, refused
        _record(contract, measured, root, baseline=baseline)
        return
    recorded = load_cost_baseline(root, baseline=baseline).of(contract)
    record = f"{COST_UPDATE_ENVIRONMENT}=update pytest -p no:xdist <this test>"
    assert recorded is not None, (
        f"{contract}: no recorded cost in {baseline.as_posix()}. Record it with `{record}`; measured "
        f"{_listing(measured)}. See {_DOC}."
    )
    added, removed = measured - recorded, recorded - measured
    sections = []
    if added:
        sections.append(f"sends more than recorded: {_listing(added)}")
    if removed:
        sections.append(f"sends less than recorded (keep the saving: re-record with `{record}`): {_listing(removed)}")
    assert not sections, f"{contract}: " + "; ".join(sections) + f". Measured {_listing(measured)}. See {_DOC}."


#: Contracts checked or recorded in this process since the plugin last drained them.
_VISITED: list[str] = []


def visited_contracts() -> list[str]:
    """Drain the contracts measured since the last call; the plugin attaches them to each test's report."""
    drained = list(_VISITED)
    _VISITED.clear()
    return drained


def stale_cost_entries(root: Path, visited: Iterable[str], *, baseline: Path = COST_BASELINE) -> list[str]:
    """Recorded contracts that no test measured: a renamed or retired path's leftover entry."""
    seen = set(visited)
    return sorted(
        entry.contract for entry in load_cost_baseline(root, baseline=baseline).costs if entry.contract not in seen
    )


def prune_cost_entries(root: Path, stale: Iterable[str], *, baseline: Path = COST_BASELINE) -> None:
    """Remove ``stale`` entries, as an update run that measured every contract does."""
    removed = set(stale)
    _write(
        root,
        [entry for entry in load_cost_baseline(root, baseline=baseline).costs if entry.contract not in removed],
        baseline=baseline,
    )


def _listing(statements: Counter[str]) -> str:
    return ", ".join(f"{count} × {shape}" for shape, count in sorted(statements.items())) or "nothing"


def _record(contract: str, measured: Counter[str], root: Path, *, baseline: Path) -> None:
    entries = [entry for entry in load_cost_baseline(root, baseline=baseline).costs if entry.contract != contract]
    entries.append(CostEntry(contract=contract, statements=dict(sorted(measured.items()))))
    _write(root, entries, baseline=baseline)


def _write(root: Path, entries: list[CostEntry], *, baseline: Path) -> None:
    document = {"costs": [entry.model_dump() for entry in sorted(entries, key=lambda entry: entry.contract)]}
    dumped = yaml_module("YAML cost baselines").safe_dump(document, sort_keys=False, allow_unicode=True, width=110)
    write_baseline(root / baseline, _HEADER + "\n" + dumped)
