"""
Invariant 5 against PostgreSQL's own plans for a selection that joins its parent.

The canned plans in ``test_plan_verdict.py`` pin the verdict's rule; these tests
show the planner producing each shape the verdict once accepted, and a plan that
serves the selection. Each test creates both tables and every index inside its
own transaction before any row exists, then seeds a realistic shape (many
parents, few of them active, many settled children, a sliver pending) and runs
``ANALYZE``: on an empty or stale table every plan costs about nothing, and the
planner's choice would depend on whichever test ran first. A fresh table per
test is what the ``populate`` hook's TRUNCATE advice buys, with no dead tuples
left by an earlier case. Each test asserts the plan's shape before the verdict,
so a planner that chooses differently fails loudly instead of testing nothing.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection, models
from django.db.models import Exists, OuterRef, QuerySet
from django.db.models.expressions import RawSQL
from django.test.utils import isolate_apps
from django.utils import timezone

from pytest_obligation.contract import ScheduledSelection
from pytest_obligation.integrations.django.selection import DjangoSelectionInspector, explain_index_eligibility
from pytest_obligation.integrations.postgres_plans import index_served_verdict, iter_plan_nodes
from pytest_obligation.profiles.automatic_recovery import assert_selection_is_index_served

with isolate_apps():

    class _Parent(models.Model):
        scope = models.CharField(max_length=8)
        active = models.BooleanField()

        class Meta:
            app_label = "tests"

    class _Child(models.Model):
        parent = models.ForeignKey(_Parent, on_delete=models.CASCADE)
        status = models.CharField(max_length=16)
        due_at = models.DateTimeField()
        padding = models.TextField()

        class Meta:
            app_label = "tests"


_CHILD = _Child._meta.db_table
_PARENT = _Parent._meta.db_table
_PARENTS = 1000
_CHILDREN = 20000
_PENDING_EVERY = 50


@pytest.fixture(name="tables")
def tables_fixture(db: None) -> Iterator[None]:
    with connection.schema_editor() as editor:
        editor.create_model(_Parent)
        editor.create_model(_Child)
    yield


def _seed(*indexes: str) -> None:
    """Create ``indexes`` on the empty tables, then the rows, then fresh planner statistics."""
    with connection.cursor() as cursor:
        for definition in indexes:
            cursor.execute(definition)
    parents = _Parent.objects.bulk_create(_Parent(scope=f"s{row % 7}", active=row % 10 == 0) for row in range(_PARENTS))
    now = timezone.now()
    _Child.objects.bulk_create(
        _Child(
            parent=parents[row % _PARENTS],
            status="pending" if row % _PENDING_EVERY == 0 else "done",
            # A sliver is overdue; the rest falls due later, as a live schedule's rows do.
            due_at=now + timedelta(minutes=-row if row % _PENDING_EVERY == 1 else row),
            padding="x" * 300,
        )
        for row in range(_CHILDREN)
    )
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {_PARENT}")
        cursor.execute(f"ANALYZE {_CHILD}")


def _scheduled(due_work: Callable[[], QuerySet[Any]]) -> ScheduledSelection:
    return ScheduledSelection(name="child selection", due_work=due_work, unscheduled_because="self-test of the plan")


def _child_scan(queryset: QuerySet[Any]) -> dict[str, Any]:
    [scan] = [
        node for node in iter_plan_nodes(explain_index_eligibility(queryset)) if node.get("Relation Name") == _CHILD
    ]
    return scan


def _due_in_scope() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the shape of a sweep that scopes by its parent and filters by time.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Child.objects.filter(parent__scope="s1", due_at__lte=timezone.now() - timedelta(days=1))


_SCOPE_INDEX = f"CREATE INDEX proof_parent_scope_ix ON {_PARENT} (scope)"


def test_a_join_key_does_not_serve_the_selections_time_condition(tables: None) -> None:
    _seed(_SCOPE_INDEX)

    # The shape the verdict once accepted: the foreign-key index positions the child scan
    # once per parent in scope, and the time condition the selection asks for is only filtered.
    child = _child_scan(_due_in_scope())
    assert child["Index Cond"] == f"(parent_id = {_PARENT}.id)" and "due_at" in child["Filter"]
    with pytest.raises(AssertionError, match="only a join key"):
        assert_selection_is_index_served(_scheduled(_due_in_scope))


@pytest.mark.parametrize(
    "own_index",
    [
        f"CREATE INDEX proof_child_due_ix ON {_CHILD} (due_at)",
        f"CREATE INDEX proof_child_due_ix ON {_CHILD} (parent_id, due_at)",
    ],
    ids=["due-time-index", "join-key-then-due-time"],
)
def test_an_index_on_the_selections_own_condition_serves_it(tables: None, own_index: str) -> None:
    # POSITIVE CONTROL: the same selection once its own time condition is indexed, alone or after the join key.
    _seed(_SCOPE_INDEX, own_index)

    # A plain scan or a bitmap, whichever the statistics favour: the composite index carries both clauses.
    [access] = [node for node in iter_plan_nodes(_child_scan(_due_in_scope())) if "Index Name" in node]
    assert access["Index Name"] == "proof_child_due_ix" and "due_at" in access["Index Cond"]
    assert_selection_is_index_served(_scheduled(_due_in_scope))


def _pending_of_active_parents() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the shape of a sweep narrowed by its own state and its parent's.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Child.objects.filter(status="pending", parent__active=True)


def _pending() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the same sweep without its parent condition.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Child.objects.filter(status="pending")


_PENDING_INDEX = "proof_child_pending_ix"


def test_a_partial_index_read_whole_does_not_serve_a_join_that_discards(tables: None) -> None:
    _seed(f"CREATE INDEX {_PENDING_INDEX} ON {_CHILD} (id) WHERE status = 'pending'")

    # The shape the verdict once accepted: the partial index is read whole, nothing is
    # filtered on the child, and the join on inactive parents throws most of it away.
    child = _child_scan(_pending_of_active_parents())
    assert child["Index Name"] == _PENDING_INDEX and "Index Cond" not in child and "Filter" not in child
    with pytest.raises(AssertionError, match="narrowing is in the join"):
        assert_selection_is_index_served(_scheduled(_pending_of_active_parents))

    # POSITIVE CONTROLS: alone, the predicate is the whole narrowing; named, what the join discards is declared.
    assert_selection_is_index_served(_scheduled(_pending))
    inspector = DjangoSelectionInspector(partial_indexes={_PENDING_INDEX})
    served, evidence = inspector.index_served(_pending_of_active_parents())
    assert served, evidence


def _children_of_active_parents() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the shape of a sweep narrowed only through its parent, in id order.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Child.objects.filter(parent__active=True).order_by("id")


def _children_of_active_parents_by_parent() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the same sweep in the order the join reaches its rows.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Child.objects.filter(parent__active=True).order_by("parent_id", "id")


_ACTIVE_INDEX = f"CREATE INDEX proof_parent_active_ix ON {_PARENT} (id) WHERE active"


@pytest.mark.parametrize("parent_index", [(), (_ACTIVE_INDEX,)], ids=["no-parent-index", "parent-index"])
def test_a_full_index_read_with_no_condition_does_not_serve_the_selection(
    tables: None, parent_index: tuple[str, ...]
) -> None:
    _seed(*parent_index)

    # The shape the verdict once accepted: the child's primary key walked end to end, with
    # no condition and no Filter, while a hash join on the active parents discards most rows.
    child = _child_scan(_children_of_active_parents())
    assert child["Index Name"] == f"{_CHILD}_pkey" and "Index Cond" not in child and "Filter" not in child
    with pytest.raises(AssertionError, match="not a partial index"):
        assert_selection_is_index_served(_scheduled(_children_of_active_parents))


def test_a_join_key_driven_by_an_indexed_parent_serves_the_selection(tables: None) -> None:
    # POSITIVE CONTROL: the active parents drive the join, and the foreign-key index reads only their
    # children, with nothing filtered here: no row of the child table is read to be thrown away.
    _seed(_ACTIVE_INDEX)

    child = _child_scan(_children_of_active_parents_by_parent())
    assert child["Index Cond"] == f"(parent_id = {_PARENT}.id)" and "Filter" not in child
    assert_selection_is_index_served(_scheduled(_children_of_active_parents_by_parent))


@pytest.mark.usefixtures("tables")
def test_a_schema_qualified_clock_narrows_the_due_index() -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA tenant_clock")
        cursor.execute(
            "CREATE FUNCTION tenant_clock.cutoff() RETURNS timestamptz LANGUAGE plpgsql STABLE "
            "AS $$ BEGIN RETURN now(); END $$"
        )
    _seed(f"CREATE INDEX child_due_ix ON {_CHILD} (due_at)")
    selection = _Child.objects.filter(due_at__lte=RawSQL("tenant_clock.cutoff()", []), status="pending")
    plan = explain_index_eligibility(selection)
    assert any("tenant_clock.cutoff()" in node.get("Index Cond", "") for node in iter_plan_nodes(plan))
    assert index_served_verdict(plan, table=_CHILD) is None


def _pending_without_an_active_parent() -> QuerySet[_Child]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; a batch whose eligibility is the absence of a dependency row.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return (
        _Child.objects.filter(status="pending")
        .exclude(Exists(_Parent.objects.filter(pk=OuterRef("parent_id"), active=True)))
        .order_by("id")[:10]
    )


def _parents_without_a_pending_child() -> QuerySet[_Parent]:
    # ARRANGE: the tables, indexes and rows each test creates.
    # REAL PRODUCTION: none; the same absence test probed through a key that is not unique.
    # EXTERNAL SEAM: none; the selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return (
        _Parent.objects.filter(active=True)
        .exclude(Exists(_Child.objects.filter(parent=OuterRef("pk"), status="pending")))
        .order_by("id")[:10]
    )


def test_an_identity_probe_through_a_unique_key_reads_one_row(tables: None) -> None:
    # Only the primary keys and the foreign-key index: each probe below is a join-key-only index condition.
    _seed()

    # The dependency probe reaches the parent by its primary key and filters its state: one row per child.
    plan = explain_index_eligibility(_pending_without_an_active_parent())
    [probe] = [node for node in iter_plan_nodes(plan) if node.get("Relation Name") == _PARENT]
    assert probe["Index Name"] == f"{_PARENT}_pkey" and "Filter" in probe
    assert probe["Index Cond"] == f"(id = {_CHILD}.parent_id)" and probe["Catalog Index"]["Unique"] is True
    assert index_served_verdict(plan, table=_PARENT) is None

    # NEGATIVE CONTROL: the same absence test through the foreign-key index reads every child of each parent.
    plan = explain_index_eligibility(_parents_without_a_pending_child())
    [probe] = [node for node in iter_plan_nodes(plan) if node.get("Relation Name") == _CHILD]
    assert probe["Index Cond"] == f"(parent_id = {_PARENT}.id)" and probe["Catalog Index"]["Unique"] is False
    assert "only a join key" in (index_served_verdict(plan, table=_CHILD) or "")
