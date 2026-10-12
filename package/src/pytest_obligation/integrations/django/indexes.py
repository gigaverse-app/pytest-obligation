"""PostgreSQL catalog evidence shared by selection and work-table schema proofs."""

from collections.abc import Sequence
from typing import Any

from django.db.backends.base.base import BaseDatabaseWrapper

from pytest_obligation.integrations.postgres_plans import CATALOG_INDEX, iter_plan_nodes
from pytest_obligation.models import HarnessModel


class InstalledIndex(HarnessModel):
    """
    One index as PostgreSQL's catalog defines it: what a plan's ``Index Name`` cannot say.

    Columns are ``pg_get_indexdef``'s text, so an expression key reads as its
    expression and a quoted name keeps its quotes.
    """

    table: str
    name: str
    access_method: str
    key_columns: tuple[str, ...]
    included_columns: tuple[str, ...]
    #: ``pg_get_expr(indpred)``: ``None`` unless the index is partial.
    predicate: str | None
    #: ``indisvalid AND indisready``: an interrupted concurrent build is neither.
    usable: bool
    #: ``indisunique``: no two rows share the key (rows with a NULL key column excepted).
    unique: bool = False


def installed_indexes(database: BaseDatabaseWrapper, tables: Sequence[str]) -> list[InstalledIndex]:
    """Every index on ``tables``, read from the catalog rather than ``Meta``: the one catalog read the plan proofs share."""
    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.relname, c.relname, am.amname, i.indnkeyatts,
                   ARRAY(SELECT pg_get_indexdef(i.indexrelid, n, true)
                         FROM generate_series(1, i.indnatts) n),
                   pg_get_expr(i.indpred, i.indrelid), i.indisvalid AND i.indisready, i.indisunique
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_am am ON am.oid = c.relam
            WHERE i.indrelid = ANY(%s::regclass[])
            ORDER BY c.relname
            """,
            [list(tables)],
        )
        rows = cursor.fetchall()
    return [
        InstalledIndex(
            table=table,
            name=name,
            access_method=method,
            key_columns=tuple(columns[:key_count]),
            included_columns=tuple(columns[key_count:]),
            predicate=predicate,
            usable=usable,
            unique=unique,
        )
        for table, name, method, key_count, columns, predicate, usable, unique in rows
    ]


#: The key under which :func:`explain_index_eligibility` records, on each node naming an index,
#: the catalog facts the plan JSON lacks: whether a condition narrows depends on key order.


def attach_catalog_facts(database: BaseDatabaseWrapper, plan: dict[str, Any]) -> None:
    tables = sorted({str(node["Relation Name"]) for node in iter_plan_nodes(plan) if "Relation Name" in node})
    catalog = {index.name: index for index in installed_indexes(database, tables)} if tables else {}
    for node in iter_plan_nodes(plan):
        if (index := catalog.get(node.get("Index Name", ""))) is not None:
            node[CATALOG_INDEX] = {
                "Access Method": index.access_method,
                "Key Columns": list(index.key_columns),
                "Predicate": index.predicate,
                "Unique": index.unique,
            }
