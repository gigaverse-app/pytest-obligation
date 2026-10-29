# Cost contracts

A recovery tick that runs every few seconds, or a delivery that runs for every
message, pays its database round trips forever. A cost contract names every
statement such a path sends and holds the path to a committed baseline, so an
added statement fails in the PR that adds it and a removed one is kept.

pytest-obligation has no stack of its own. The proofs take plain callables, and
the host's `SelectionInspector` captures the statements. A Celery beat sweep, an
RQ or procrastinate job, a DBOS step or a plain Django view can each be held to
a contract, provided its database has an inspector. The Django integration's
host supplies one.

## Shapes, not counts

A count hides a swap. Remove a clock read, add a per-row lookup, and the count
is unchanged while the path got slower. So each statement is named by its
*shape*: what it does to which table.

| SQL | Shape |
| --- | --- |
| `SELECT ... FROM "work" ... FOR UPDATE OF "work"` | `lock work` |
| `SELECT "state", COUNT(*) FROM "work" GROUP BY 1` | `count work` |
| `SELECT 1 AS "a" FROM "work" WHERE ...` | `read work` |
| `UPDATE "work" SET ...` | `update work` |
| `SELECT clock_timestamp()` | `select clock_timestamp()` |
| `BEGIN`, `COMMIT`, `SAVEPOINT ...` | `begin`, `commit`, `savepoint` |

Only the outermost statement is named; a join or subquery is part of its
statement, not a round trip. Transaction control is included because commits are
often the quantity a change is about. Shapes stay the same when an ORM changes
its quoting, aliases or column order, so a baseline does not churn with the ORM
or database version.

## The three measurements

```python
from pytest_obligation import (
    assert_statement_cost,
    marginal_statement_shapes,
    statement_shapes,
)


def test_recovery_costs(request):
    root = request.config.rootpath
    # Everything one idle tick sends.
    assert_statement_cost("orders: idle tick", statement_shapes(sweep.run_tick), root=root)
    # Exactly what one more owed row adds to a tick.
    per_row = marginal_statement_shapes(make_owed=make_owed, run_tick=sweep.run_tick)
    assert_statement_cost("orders: per owed row", per_row, root=root)
    # One delivery, from claim to settlement.
    assert_statement_cost("orders: one delivery", statement_shapes(deliver_one), root=root)
```

`marginal_statement_shapes` makes `small` rows owed and ticks, then `large` rows
and ticks, and divides the difference. Each tick must take the rows it finds, and
`large` must fit in one page. Pass `remaining=` (how many rows made owed still
wait) so a tick that took nothing fails instead of recording an empty cost. A per-row query (the N+1 that a bounded page hides,
because the damage per tick is capped) shows up here and nowhere else. The proof
fails when the two ticks did different work rather than more of the same: the
difference is not a whole per-row cost, or the larger backlog skipped a statement.

## The baseline ratchets

`obligation_cost_baseline.yaml`, at the pytest root, records each contract as
shape → count. A test fails on any difference:

* **More** than recorded is a regression. Remove the statement, or re-record
  and justify the cost in the PR.
* **Less** than recorded is a saving. Re-record so the saving is kept; otherwise
  a later change could spend it unnoticed.
* **No entry** fails too, so a new contract cannot pass by being absent.

Record or lower entries with:

```sh
OBLIGATION_COST_BASELINE=update pytest -p no:xdist <tests>
```

Updates refuse xdist workers, because they rewrite one file. The file is written
with LF endings and sorted by contract, so regenerating it on any platform
changes only the entries that changed. The baseline diff in a PR is that PR's
cost change, reviewable without running anything.

Reading the baseline needs `pytest-obligation[debt]`, which provides YAML, like
the [debt baseline](debt-baseline.md).

## What a pass means

A pass means the path sent exactly the recorded statements, in this run, against
this database. It says nothing about how long they took, what plans they used, or
how much the application computed around them. Statement counts are
deterministic, so they gate CI cheaply; time and CPU still need a benchmark. An
entry whose contract no longer runs is not detected; delete it when its test
goes away.
