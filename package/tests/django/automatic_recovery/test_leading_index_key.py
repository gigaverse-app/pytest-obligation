"""
Invariant 5 against PostgreSQL's own plans: an index condition narrows only when it constrains the leading key.

The canned plans in ``test_sweep.py`` pin the verdict's rule; these tests show
the planner producing each shape. One table, seeded so its statistics make the
planner's choice deterministic: wide rows, so walking the heap through the
primary key costs more than any index, and few UNKNOWN rows among many SENT ones.
Each test creates the table and its indexes inside its own transaction, before
any row exists, so no earlier history can leave an index the planner may not use.
"""

from collections.abc import Callable, Iterator

import pytest
from django.db import connection, models
from django.db.models import QuerySet
from django.test.utils import isolate_apps

from pytest_obligation.contract import ScheduledSelection
from pytest_obligation.integrations.django.selection import DjangoSelectionInspector, explain_index_eligibility
from pytest_obligation.integrations.postgres_plans import assert_plan_is_index_served, iter_plan_nodes
from pytest_obligation.profiles.automatic_recovery import assert_selection_is_index_served

with isolate_apps():

    class _Chunk(models.Model):
        campaign_id = models.IntegerField()
        state = models.CharField(max_length=16)
        padding = models.TextField()

        class Meta:
            app_label = "tests"


_TABLE = _Chunk._meta.db_table
_ROWS = 4000
_UNKNOWN_EVERY = 100
#: The email engine's (campaign, state) accounting index: ``state`` is its second key.
_SECOND_KEY_INDEX = "proof_chunk_campaign_state_ix"


@pytest.fixture(name="chunk_table")
def chunk_table_fixture(db: None) -> Iterator[None]:
    with connection.schema_editor() as editor:
        editor.create_model(_Chunk)
    yield


def _index(definition: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(definition)


def _seed() -> None:
    """Many settled rows and a few owed ones, then fresh planner statistics."""
    _Chunk.objects.bulk_create(
        _Chunk(
            campaign_id=row % 97,
            state="UNKNOWN" if row % _UNKNOWN_EVERY == 0 else "SENT",
            padding="x" * 400,
        )
        for row in range(_ROWS)
    )
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {_TABLE}")


def _unknown_chunks() -> QuerySet[_Chunk]:
    # ARRANGE: the table and indexes each test creates.
    # REAL PRODUCTION: none; the email unknown-chunk selection's shape on a test table.
    # EXTERNAL SEAM: none; selection is database-only.
    # OBSERVE: PostgreSQL's plan for it.
    return _Chunk.objects.filter(state="UNKNOWN").order_by("id")


_SELECTION = ScheduledSelection(
    name="unknown chunks", due_work=_unknown_chunks, unscheduled_because="self-test of the plan verdict"
)


def _accesses(index: str) -> list[dict]:
    return [
        node
        for node in iter_plan_nodes(explain_index_eligibility(_unknown_chunks()))
        if node.get("Index Name") == index
    ]


def test_a_condition_on_the_second_key_is_rejected(chunk_table: None) -> None:
    _index(f"CREATE INDEX {_SECOND_KEY_INDEX} ON {_TABLE} (campaign_id, state)")
    _seed()

    # The shape the verdict once accepted: the planner reads the composite index with an
    # Index Cond on its second key and nothing left to Filter.
    [access] = _accesses(_SECOND_KEY_INDEX)
    assert "state" in access["Index Cond"] and "Filter" not in access
    with pytest.raises(AssertionError, match="leading key column 'campaign_id'"):
        assert_selection_is_index_served(_SELECTION)


@pytest.mark.parametrize(
    "narrowing",
    [
        f"CREATE INDEX proof_chunk_state_ix ON {_TABLE} (state, campaign_id)",
        f"CREATE INDEX proof_chunk_unknown_ix ON {_TABLE} (id) WHERE state = 'UNKNOWN'",
    ],
    ids=["an-index-leading-with-state", "a-partial-index-the-selection-implies"],
)
def test_an_index_that_narrows_passes_beside_the_second_key_one(chunk_table: None, narrowing: str) -> None:
    _index(f"CREATE INDEX {_SECOND_KEY_INDEX} ON {_TABLE} (campaign_id, state)")
    _index(narrowing)
    _seed()

    assert not _accesses(_SECOND_KEY_INDEX), "the planner should prefer the narrowing index"
    assert_selection_is_index_served(_SELECTION)


_PARTIAL_INDEX = "proof_chunk_unknown_ix"


def test_retained_partial_index_remains_eligible_beside_a_small_wrong_key_index(chunk_table: None) -> None:
    # A reused test DB can retain a large, valid index after its rows are gone,
    # while a newly created accounting index is tiny. Eligibility must not be
    # confused with the cheapest plan for that empty-table history.
    _Chunk.objects.bulk_create(_Chunk(campaign_id=i, state="UNKNOWN", padding="x" * 1500) for i in range(_ROWS))
    _index(f"CREATE INDEX {_PARTIAL_INDEX} ON {_TABLE} (id) INCLUDE (padding) WHERE state = 'UNKNOWN'")
    _Chunk.objects.all().delete()
    _index(f"CREATE INDEX {_SECOND_KEY_INDEX} ON {_TABLE} (campaign_id, state) INCLUDE (id)")
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {_TABLE}")
    inspector = DjangoSelectionInspector(partial_indexes=(_PARTIAL_INDEX,))
    selection = _unknown_chunks().values("id").order_by("campaign_id", "state")
    bitmap = explain_index_eligibility(selection, bitmap_only=True)
    assert any(node.get("Index Name") == _PARTIAL_INDEX for node in iter_plan_nodes(bitmap))
    assert_plan_is_index_served(name="eligible alternative", plan=bitmap, table=_TABLE)
    served, evidence = inspector.index_served(selection)
    assert served, evidence

    # Removing the real narrowing index must still fail on the accounting
    # index's unconstrained leading key; never accept its state condition alone.
    _index(f"DROP INDEX {_PARTIAL_INDEX}")
    served, evidence = DjangoSelectionInspector().index_served(selection)
    assert not served, evidence


@pytest.mark.parametrize(
    ("selection", "passes"),
    [
        (_unknown_chunks, True),
        (lambda: _unknown_chunks().filter(campaign_id__lt=50), False),
    ],
    ids=["the-whole-selection", "a-heap-filter-after-the-predicate"],
)
def test_a_bitmap_of_the_partial_index_passes_only_as_the_whole_selection(
    chunk_table: None, selection: Callable[[], QuerySet[_Chunk]], passes: bool
) -> None:
    """The bitmap the planner picks once plain index scans are off: no Index Cond, the predicate does the narrowing."""
    _index(f"CREATE INDEX {_PARTIAL_INDEX} ON {_TABLE} (id) WHERE state = 'UNKNOWN'")
    _seed()

    plan = explain_index_eligibility(selection(), bitmap_only=True)
    [arm] = [node for node in iter_plan_nodes(plan) if node.get("Index Name") == _PARTIAL_INDEX]
    assert arm["Node Type"] == "Bitmap Index Scan" and "Index Cond" not in arm
    if passes:
        assert_plan_is_index_served(name="partial bitmap", plan=plan, table=_TABLE)
    else:
        with pytest.raises(AssertionError, match="Recheck Cond .* is not evidence"):
            assert_plan_is_index_served(name="partial bitmap", plan=plan, table=_TABLE)
