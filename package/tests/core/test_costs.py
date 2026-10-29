"""Cost contracts name each statement by its shape and hold a path to its committed baseline."""

from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pytest_obligation.costs import (
    COST_BASELINE,
    COST_UPDATE_ENVIRONMENT,
    assert_statement_cost,
    load_cost_baseline,
    marginal_statement_shapes,
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
    ],
)
def test_each_statement_is_named_by_what_it_does_to_which_table(sql: str, shape: str) -> None:
    assert statement_shape(sql) == shape


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
    assert marginal_statement_shapes(make_owed=sweep.make_owed, run_tick=sweep.run_tick) == Counter(
        {"lock work": 1, "update work": 1}
    )


def test_a_per_row_lookup_appears_in_the_marginal_cost(database: _ScriptedDatabase) -> None:
    sweep = _Sweep(database, per_row=('SELECT "id" FROM "order" WHERE "id" = %s',))
    assert marginal_statement_shapes(make_owed=sweep.make_owed, run_tick=sweep.run_tick)["read order"] == 1


def test_ticks_doing_different_work_have_no_marginal_cost(database: _ScriptedDatabase) -> None:
    uneven = _Sweep(database, uneven=True)
    with pytest.raises(AssertionError, match="not a whole per-row cost"):
        marginal_statement_shapes(make_owed=uneven.make_owed, run_tick=uneven.run_tick)

    skipping = _Sweep(database)
    first = skipping.run_tick

    def tick_that_stops_reading() -> None:
        before = len(database.statements)
        first()
        if skipping.ticks == 2:
            del database.statements[before]

    with pytest.raises(AssertionError, match="skipped statements"):
        marginal_statement_shapes(make_owed=skipping.make_owed, run_tick=tick_that_stops_reading)


def test_a_marginal_cost_is_compared_with_its_counts(
    database: _ScriptedDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _Sweep(database, per_row=('UPDATE "work" SET "y" = 1',))
    per_row = marginal_statement_shapes(make_owed=sweep.make_owed, run_tick=sweep.run_tick)
    assert per_row["update work"] == 2
    _record(tmp_path, "per owed row", ["lock work", "update work"], monkeypatch)
    # One update per row is recorded; the counter carries two, which must not collapse to one shape.
    with pytest.raises(AssertionError, match="sends more than recorded: 1 × update work"):
        assert_statement_cost("per owed row", per_row, root=tmp_path)
