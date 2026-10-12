"""A later B-tree key must not masquerade as a bounded scheduled selection."""

from contextlib import nullcontext

import pytest

from pytest_obligation.integrations.postgres_plans import assert_plan_is_index_served


@pytest.mark.parametrize("bitmap", [False, True])
@pytest.mark.parametrize(
    "condition", ["(state = 'UNKNOWN')", "(campaign_id = 7)", "(campaign_id IS NULL)", '("campaign_id" >= 7)']
)
def test_index_condition_must_constrain_the_leading_key(bitmap: bool, condition: str) -> None:
    arm = {
        "Node Type": "Bitmap Index Scan" if bitmap else "Index Scan",
        "Index Name": "campaign_state",
        "Index Cond": condition,
        "Catalog Index": {"Access Method": "btree", "Key Columns": ["campaign_id", "state"], "Predicate": None},
    }
    plan = (
        {"Node Type": "Bitmap Heap Scan", "Relation Name": "work", "Plans": [arm]}
        if bitmap
        else {**arm, "Relation Name": "work"}
    )
    if "campaign_id" in condition:
        assert_plan_is_index_served(name="leading key", plan=plan, table="work")
    else:
        with pytest.raises(AssertionError, match="leading key column 'campaign_id'"):
            assert_plan_is_index_served(name="leading key", plan=plan, table="work")


def test_an_index_condition_without_catalog_evidence_is_not_verified() -> None:
    with pytest.raises(AssertionError, match="without its catalog definition"):
        assert_plan_is_index_served(
            name="bare plan",
            table="work",
            plan={
                "Node Type": "Index Scan",
                "Relation Name": "work",
                "Index Name": "ix",
                "Index Cond": "(state = 'UNKNOWN')",
            },
        )


@pytest.mark.parametrize(
    ("keys", "condition", "predicate", "method"),
    [
        (["state"], "((state)::text = 'UNKNOWN'::text)", None, "btree"),
        (["state"], "(state IS NOT NULL)", None, "btree"),
        (["state"], "(state ~>=~ 'A' AND state ~<~ 'B')", None, "btree"),
        (['"State"'], '("State" = $1)', None, "btree"),
        (["campaign_id", "state"], "(state = 'UNKNOWN')", "state = 'UNKNOWN'", "btree"),
        (["campaign_id", "state"], "(state = 'UNKNOWN')", None, "gin"),
        (["lower(state)"], "(lower(state) = 'unknown')", None, "btree"),
    ],
)
def test_valid_catalog_shapes(keys: list[str], condition: str, predicate: str | None, method: str) -> None:
    assert_plan_is_index_served(
        name="catalog shapes",
        table="work",
        plan={
            "Node Type": "Index Scan",
            "Relation Name": "work",
            "Index Name": "ix",
            "Index Cond": condition,
            "Catalog Index": {"Access Method": method, "Key Columns": keys, "Predicate": predicate},
        },
    )


@pytest.mark.parametrize(
    "condition",
    [
        "(state = 'campaign_id = 1')",
        r"(state = E'escaped\' campaign_id = 1')",
        "(state = $$campaign_id = 1$$)",
        "(state = $body$campaign_id = 1$body$)",
        "(state = $tag1$campaign_id = 1$tag1$)",
        '("campaign_id"" suffix" = 1)',
        '("other campaign_id" = 1)',
        "(state = 'UNKNOWN') /* campaign_id = 1 */",
        "(state = 'UNKNOWN') -- campaign_id = 1",
    ],
)
@pytest.mark.parametrize("constrain_key", [False, True])
def test_a_column_named_only_in_sql_text_does_not_constrain_the_leading_key(
    condition: str, constrain_key: bool
) -> None:
    if constrain_key:
        condition += "\n AND campaign_id = 7"
    with nullcontext() if constrain_key else pytest.raises(AssertionError, match="leading key column 'campaign_id'"):
        assert_plan_is_index_served(
            name="literal",
            table="work",
            plan={
                "Node Type": "Index Scan",
                "Relation Name": "work",
                "Index Name": "ix",
                "Index Cond": condition,
                "Catalog Index": {"Access Method": "btree", "Key Columns": ["campaign_id", "state"], "Predicate": None},
            },
        )


@pytest.mark.parametrize("fault", [None, "filter", "join", "not_partial"])
def test_partial_bitmap_must_cover_the_whole_selection(fault: str | None) -> None:
    arm = {
        "Node Type": "Bitmap Index Scan",
        "Index Name": "ix",
        "Catalog Index": {
            "Access Method": "btree",
            "Key Columns": ["id"],
            "Predicate": None if fault == "not_partial" else "state = 'UNKNOWN'",
        },
    }
    plan = {"Node Type": "Bitmap Heap Scan", "Relation Name": "work", "Plans": [arm]}
    if fault == "filter":
        plan["Filter"] = "campaign_id < 50"
    if fault == "join":
        plan = {"Node Type": "Nested Loop", "Plans": [plan, {"Node Type": "Index Scan", "Relation Name": "campaign"}]}
    if fault:
        with pytest.raises(AssertionError, match="Recheck Cond .* is not evidence"):
            assert_plan_is_index_served(name="partial bitmap", table="work", plan=plan)
    else:
        assert_plan_is_index_served(name="partial bitmap", table="work", plan=plan)


@pytest.mark.parametrize("leading", ["available_at", "owner_id"])
def test_a_range_on_a_later_key_needs_a_truly_narrowing_bitmap(leading: str) -> None:
    from pytest_obligation.integrations.postgres_plans import bitmap_overturns_the_walk

    scan = {
        "Node Type": "Index Scan",
        "Relation Name": "work",
        "Index Name": "ix",
        "Index Cond": "available_at <= $1",
        "Catalog Index": {"Access Method": "btree", "Key Columns": ["owner_id", "available_at"], "Predicate": None},
    }
    arm = {
        **scan,
        "Node Type": "Bitmap Index Scan",
        "Catalog Index": {"Access Method": "btree", "Key Columns": [leading], "Predicate": None},
    }
    del arm["Relation Name"]
    bitmap = {"Node Type": "Bitmap Heap Scan", "Relation Name": "work", "Plans": [arm]}
    assert bitmap_overturns_the_walk(scan, bitmap, table="work") is (leading == "available_at")
