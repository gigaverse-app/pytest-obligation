"""Cost contracts name each statement by its shape and hold a path to its committed baseline."""

from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pytest_obligation.costs import (
    COST_BASELINE,
    COST_UPDATE_ENVIRONMENT,
    CostEntry,
    UnclassifiedStatement,
    assert_statement_cost,
    load_cost_baseline,
    marginal_statement_shapes,
    prune_cost_entries,
    stale_cost_entries,
    statement_shape,
    statement_shapes,
)
from pytest_obligation.host import Host, hosted


class _ScriptedDatabase:
    """Statements are whatever the path appends; the inspector returns the ones a call appended."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def statements_during(self, run: Callable[[], object]) -> list[str]:
        start = len(self.statements)
        run()
        return self.statements[start:]


@pytest.fixture
def database() -> Iterator[_ScriptedDatabase]:
    scripted = _ScriptedDatabase()
    with hosted(Host(selection_inspectors=(scripted,))):  # pyrefly: ignore [bad-argument-type]
        yield scripted


@pytest.mark.parametrize(
    ("sql", "shape"),
    [
        ("SELECT clock_timestamp()", "select clock_timestamp()"),
        (
            'SELECT clock_timestamp(), EXISTS (SELECT 1 AS "a" FROM "attempt" WHERE "x" = %s)',
            "select clock_timestamp(), exists (…)",
        ),
        ("BEGIN", "begin"),
        ("COMMIT", "commit"),
        ('SAVEPOINT "s1_x4"', "savepoint"),
        ('RELEASE SAVEPOINT "s1_x4"', "release savepoint"),
        ('ROLLBACK TO SAVEPOINT "s1_x4"', "rollback to savepoint"),
        (
            'SELECT "work"."id", "work"."state" FROM "work" INNER JOIN "order" ON ("work"."owner_id" = "order"."id") '
            'WHERE ("work"."id" = %s AND "work"."available_at" <= STATEMENT_TIMESTAMP()) LIMIT 1 FOR UPDATE OF "work"',
            "lock work",
        ),
        (
            'SELECT "order"."id" FROM "order" WHERE "order"."id" IN (SELECT U0."owner_id" FROM "work" U0 '
            'WHERE U0."id" = %s) FOR UPDATE',
            "lock order",
        ),
        ('SELECT "work"."state", COUNT("work"."id") AS "count" FROM "work" GROUP BY 1', "count work"),
        ('SELECT 1 AS "a" FROM "work" WHERE "work"."id" = %s LIMIT 1', "read work"),
        (
            'SELECT $2 FROM ONLY "public"."product" x WHERE "id" OPERATOR(pg_catalog.=) $1 FOR KEY SHARE OF x',
            "lock product",
        ),
        ('UPDATE "work" SET "state" = %s WHERE "work"."id" = %s', "update work"),
        ('INSERT INTO "order" ("key") VALUES (%s) RETURNING "order"."id"', "insert order"),
        ('DELETE FROM "work" WHERE "work"."id" IN (%s)', "delete work"),
        (
            'WITH due AS (SELECT "id" FROM "work" WHERE "state" = %s) SELECT "id" FROM "work" WHERE "id" IN (SELECT "id" FROM due)',
            "read work",
        ),
        # Captured SQL carries the values a client-binding driver spliced in: data is never SQL.
        ("""SELECT "id" FROM "orders" WHERE "note" = 'waiting for update'""", "read orders"),
        ("""SELECT 'a FROM b' AS "label" FROM "orders\"""", "read orders"),
        ("""SELECT "id" FROM "orders" WHERE "x" IN (SELECT 1 FROM "t" WHERE "n" = ')') FOR UPDATE""", "lock orders"),
        ("""SELECT "id" FROM "orders" WHERE "note" = 'it''s (' FOR UPDATE""", "lock orders"),
        ("""SELECT $$ it's ( $$ AS "x" FROM "orders" FOR UPDATE""", "lock orders"),
        ("""SELECT "id" FROM "orders" WHERE "note" = E'a\\'b (' LIMIT 1""", "read orders"),
        ("""SELECT '2026-11-04T10:00:00+00:00'::timestamptz""", "select ?::timestamptz"),
        ('SELECT "id" FROM "orders" /* FOR UPDATE */', "read orders"),
        ('SELECT "id" FROM "orders" -- FOR UPDATE\n', "read orders"),
        # The main statement of a WITH, whatever its CTEs are named.
        (
            'WITH "picked" AS (SELECT "id" FROM "work" WHERE "due" <= now() LIMIT 10 FOR UPDATE SKIP LOCKED) '
            'UPDATE "work" SET "state" = 1 FROM "picked" WHERE "work"."id" = "picked"."id" RETURNING "work"."id"',
            "update work",
        ),
        ('WITH s AS (SELECT "id" FROM "src") INSERT INTO "dst" ("id") SELECT "id" FROM s', "insert dst"),
        ('WITH w AS (SELECT "id" FROM "work" FOR UPDATE) SELECT * FROM w', "lock work"),
        ('WITH w ("id") AS (SELECT "id" FROM "work" FOR UPDATE SKIP LOCKED) SELECT "id" FROM w', "lock work"),
        ('WITH done AS (UPDATE "work" SET "x" = 1 RETURNING "id") SELECT count(*) FROM done', "update work"),
        # Only the outermost statement decides; a subquery's count or lock is part of it.
        (
            'SELECT "o"."id", (SELECT COUNT(*) FROM "lines" WHERE "o_id" = "o"."id") AS "n" FROM "orders" "o"',
            "read orders",
        ),
        ('SELECT "id" FROM "orders" WHERE "id" IN (SELECT "id" FROM "work" FOR UPDATE SKIP LOCKED)', "read orders"),
        ('SELECT COUNT(*) FROM (SELECT DISTINCT "a"."id" AS "col1" FROM "orders" "a") subquery', "count orders"),
        ('(SELECT "id" FROM "a" ORDER BY "id" LIMIT 1) UNION (SELECT "id" FROM "b" LIMIT 1)', "read a"),
        ('SELECT "x" FROM "my.schema.table"', "read my.schema.table"),
        ('SELECT "x" FROM "order items"', "read order items"),
        ('SELECT "x" FROM "public"."orders"', "read orders"),
        ('UPDATE ONLY "public"."work" SET "x" = 1', "update work"),
        ('INSERT INTO "dst" ("id") VALUES (1) ON CONFLICT ("id") DO NOTHING', "insert dst"),
        ('SELECT "valid_from" FROM "orders"', "read orders"),
        ("SELECT EXTRACT(EPOCH FROM now())", "select extract(…)"),
    ],
)
def test_each_statement_is_named_by_what_it_does_to_which_table(sql: str, shape: str) -> None:
    assert statement_shape(sql) == shape


@pytest.mark.parametrize("sql", ["VALUES (1)", "SET TIME ZONE 'UTC'", "NOTIFY due_work, 'x'", "SELECT 1 FROM"])
def test_strict_naming_refuses_a_statement_without_verb_and_table(sql: str) -> None:
    with pytest.raises(UnclassifiedStatement):
        statement_shape(sql, strict=True)
    assert statement_shape(sql)


def test_strict_shapes_refuse_an_unclassified_statement_on_the_path(database: _ScriptedDatabase) -> None:
    with pytest.raises(UnclassifiedStatement, match="NOTIFY"):
        statement_shapes(_path(database, 'SELECT "id" FROM "work"', "NOTIFY due_work"), strict=True)


def _path(database: _ScriptedDatabase, *statements: str) -> Callable[[], None]:
    return lambda: database.statements.extend(statements)


def _record(root: Path, contract: str, shapes: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as update:
        update.setenv(COST_UPDATE_ENVIRONMENT, "update")
        # Each test writes its own temporary baseline, so the xdist single-writer guard does not apply.
        update.delenv("PYTEST_XDIST_WORKER", raising=False)
        assert_statement_cost(contract, shapes, root=root)


def test_a_swap_with_the_same_count_fails_where_a_count_would_pass(
    database: _ScriptedDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = statement_shapes(_path(database, "SELECT clock_timestamp()", 'SELECT "id" FROM "work" FOR UPDATE'))
    _record(tmp_path, "stage", before, monkeypatch)
    # The clock read is gone, but a per-row owner read took its place: one for one.
    after = statement_shapes(_path(database, 'SELECT "id" FROM "order"', 'SELECT "id" FROM "work" FOR UPDATE'))
    assert len(after) == len(before)
    with pytest.raises(AssertionError) as failure:
        assert_statement_cost("stage", after, root=tmp_path)
    message = str(failure.value)
    assert "sends more than recorded: 1 × read order" in message
    assert "sends less than recorded" in message and "1 × select clock_timestamp()" in message


def test_a_saving_fails_until_the_baseline_keeps_it(
    database: _ScriptedDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(tmp_path, "stage", ["select clock_timestamp()", "lock work", "update work"], monkeypatch)
    cheaper = statement_shapes(_path(database, 'SELECT "id" FROM "work" FOR UPDATE', 'UPDATE "work" SET "x" = 1'))
    with pytest.raises(AssertionError, match=r"keep the saving.*1 × select clock_timestamp\(\)"):
        assert_statement_cost("stage", cheaper, root=tmp_path)
    _record(tmp_path, "stage", cheaper, monkeypatch)
    assert_statement_cost("stage", cheaper, root=tmp_path)


def test_a_plain_mapping_is_compared_with_its_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _record(tmp_path, "per row", ["lock work", "update work"], monkeypatch)
    with pytest.raises(AssertionError, match="sends more than recorded: 1 × update work"):
        assert_statement_cost("per row", {"lock work": 1, "update work": 2}, root=tmp_path)
    assert_statement_cost("per row", {"lock work": 1, "update work": 1, "read work": 0}, root=tmp_path)


def test_a_recorded_count_is_positive() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        CostEntry(contract="path", statements={"read work": 0})


def test_entries_no_test_measured_are_stale_and_can_be_pruned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _record(tmp_path, "kept", ["read work"], monkeypatch)
    _record(tmp_path, "renamed away", ["read work"], monkeypatch)
    assert stale_cost_entries(tmp_path, ["kept"]) == ["renamed away"]
    prune_cost_entries(tmp_path, ["renamed away"])
    assert [entry.contract for entry in load_cost_baseline(tmp_path).costs] == ["kept"]


_COST_TEST = """
from pathlib import Path
from pytest_obligation import assert_statement_cost

def test_kept(request):
    assert_statement_cost("kept", ["read work"], root=Path(request.config.rootpath))
"""
_STALE_BASELINE = (
    "costs:\n- contract: kept\n  statements:\n    read work: 1\n- contract: retired\n  statements:\n    read work: 1\n"
)


@pytest.mark.parametrize("workers", [0, 2], ids=["serial", "xdist"])
def test_a_full_run_fails_on_an_entry_no_test_measured(pytester: pytest.Pytester, workers: int) -> None:
    pytester.makepyfile(test_kept=_COST_TEST)
    (pytester.path / COST_BASELINE).write_text(_STALE_BASELINE, encoding="utf-8")
    xdist = ["-n", str(workers)] if workers else []
    assert pytester.runpytest_subprocess(*xdist).ret == 0, "without the flag, a stale entry is tolerated"
    result = pytester.runpytest_subprocess("--obligation-cost-baseline-complete", *xdist)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*baseline entries no test measured*", "*- retired*"])


def test_a_full_update_run_prunes_entries_no_test_measured(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makepyfile(test_kept=_COST_TEST)
    (pytester.path / COST_BASELINE).write_text(_STALE_BASELINE, encoding="utf-8")
    monkeypatch.setenv(COST_UPDATE_ENVIRONMENT, "update")
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert pytester.runpytest_subprocess("--obligation-cost-baseline-complete", "-p", "no:xdist").ret == 0
    assert [entry.contract for entry in load_cost_baseline(pytester.path).costs] == ["kept"]


def test_an_unrecorded_contract_cannot_pass_by_being_absent(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match=f"no recorded cost.*{COST_UPDATE_ENVIRONMENT}=update"):
        assert_statement_cost("new path", ["read work"], root=tmp_path)


def test_recording_writes_one_sorted_lf_entry_per_contract_and_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(tmp_path, "b: delivery", ["update work", "lock work", "update work"], monkeypatch)
    _record(tmp_path, "a: idle tick", ["read work"], monkeypatch)
    _record(tmp_path, "b: delivery", ["update work", "lock work"], monkeypatch)
    raw = (tmp_path / COST_BASELINE).read_bytes()
    assert b"\r\n" not in raw
    assert raw.startswith(b"# Cost contracts")
    recorded = load_cost_baseline(tmp_path)
    assert [entry.contract for entry in recorded.costs] == ["a: idle tick", "b: delivery"]
    assert recorded.of("b: delivery") == Counter({"lock work": 1, "update work": 1})
    _record(tmp_path, "b: delivery", ["update work", "lock work"], monkeypatch)
    assert (tmp_path / COST_BASELINE).read_bytes() == raw


def test_recording_refuses_concurrent_xdist_writers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(COST_UPDATE_ENVIRONMENT, "update")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    with pytest.raises(AssertionError, match="-p no:xdist"):
        assert_statement_cost("path", ["read work"], root=tmp_path)
    assert not (tmp_path / COST_BASELINE).exists()


class _Sweep:
    """A tick that pages owed rows and claims each; ``per_row`` adds a statement per row."""

    def __init__(self, database: _ScriptedDatabase, *, per_row: tuple[str, ...] = (), uneven: bool = False) -> None:
        self.database = database
        self.owed = 0
        self.per_row = per_row
        self.uneven = uneven
        self.ticks = 0

    def make_owed(self) -> None:
        self.owed += 1

    def run_tick(self) -> None:
        self.ticks += 1
        self.database.statements.append('SELECT "id" FROM "work" WHERE "state" = %s')
        for _ in range(self.owed):
            self.database.statements.extend(['SELECT "id" FROM "work" FOR UPDATE', 'UPDATE "work" SET "x" = 1'])
            self.database.statements.extend(self.per_row)
        if self.uneven and self.ticks == 2:
            self.database.statements.append('SELECT "id" FROM "metrics"')
        self.owed = 0


def test_one_more_owed_row_costs_exactly_its_claim(database: _ScriptedDatabase) -> None:
    sweep = _Sweep(database)
    assert marginal_statement_shapes(
        make_owed=sweep.make_owed, run_tick=sweep.run_tick, remaining=lambda: sweep.owed
    ) == Counter({"lock work": 1, "update work": 1})


def test_a_per_row_lookup_appears_in_the_marginal_cost(database: _ScriptedDatabase) -> None:
    sweep = _Sweep(database, per_row=('SELECT "id" FROM "order" WHERE "id" = %s',))
    assert (
        marginal_statement_shapes(make_owed=sweep.make_owed, run_tick=sweep.run_tick, remaining=lambda: sweep.owed)[
            "read order"
        ]
        == 1
    )


def test_ticks_doing_different_work_have_no_marginal_cost(database: _ScriptedDatabase) -> None:
    uneven = _Sweep(database, uneven=True)
    with pytest.raises(AssertionError, match="not a whole per-row cost"):
        marginal_statement_shapes(make_owed=uneven.make_owed, run_tick=uneven.run_tick, remaining=lambda: uneven.owed)

    skipping = _Sweep(database)
    first = skipping.run_tick

    def tick_that_stops_reading() -> None:
        before = len(database.statements)
        first()
        if skipping.ticks == 2:
            del database.statements[before]

    with pytest.raises(AssertionError, match="skipped statements"):
        marginal_statement_shapes(
            make_owed=skipping.make_owed, run_tick=tick_that_stops_reading, remaining=lambda: skipping.owed
        )


def test_a_marginal_cost_is_compared_with_its_counts(
    database: _ScriptedDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _Sweep(database, per_row=('UPDATE "work" SET "y" = 1',))
    per_row = marginal_statement_shapes(
        make_owed=sweep.make_owed, run_tick=sweep.run_tick, remaining=lambda: sweep.owed
    )
    assert per_row["update work"] == 2
    _record(tmp_path, "per owed row", ["lock work", "update work"], monkeypatch)
    # One update per row is recorded; the counter carries two, which must not collapse to one shape.
    with pytest.raises(AssertionError, match="sends more than recorded: 1 × update work"):
        assert_statement_cost("per owed row", per_row, root=tmp_path)


def test_a_tick_that_takes_nothing_cannot_pass_with_an_empty_marginal_cost(database: _ScriptedDatabase) -> None:
    sweep = _Sweep(database)
    waiting: list[None] = []

    def make_owed_but_not_due() -> None:
        waiting.append(None)

    # Declining the guard is explicit; then a tick that takes nothing reports an empty marginal cost.
    assert (
        marginal_statement_shapes(make_owed=make_owed_but_not_due, run_tick=sweep.run_tick, remaining=None) == Counter()
    )
    waiting.clear()
    with pytest.raises(AssertionError, match="left 1 waiting"):
        marginal_statement_shapes(
            make_owed=make_owed_but_not_due, run_tick=sweep.run_tick, remaining=lambda: len(waiting)
        )


def test_the_guard_is_required() -> None:
    with pytest.raises(TypeError, match="remaining"):
        marginal_statement_shapes(make_owed=lambda: None, run_tick=lambda: None)  # pyrefly: ignore [missing-argument]
