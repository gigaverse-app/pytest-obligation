"""Observe PyMongo find cursors and inspect their real MongoDB selection plans.

Motor uses the same synchronous cursors in its executor. No predicate, sort or
limit is reconstructed here. Unsupported plan shapes and SQL-only metrics stay
explicit; the inspector never converts missing evidence into a passing proof.
"""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from pymongo import ReadPreference
from pymongo.synchronous.collection import Collection
from pymongo.synchronous.cursor import Cursor

from pytest_obligation.host import ReadCosts
from pytest_obligation.models import ObligationContractDesignError


def selection_built_by(read: Callable[[], object], collection: Collection[Any]) -> Cursor[Any]:
    """Return a fresh clone of the first find that ``read`` executes on ``collection``.

    Pass a read-only production entry point; it runs to completion. For Motor,
    finish the async read on its owning loop and pass ``collection.delegate``.
    Construction alone does not count. Other clients and collections are ignored.
    The first query's projection, sort, limit, hint and routing are preserved,
    including a pagination limit: this does not pretend a page is a whole sweep.
    """
    if not isinstance(collection, Collection):
        raise ObligationContractDesignError("pass a synchronous PyMongo collection, or Motor collection.delegate")
    captured: list[Cursor[Any]] = []
    send_message = Cursor._send_message

    def observed(cursor: Cursor[Any], operation: Any) -> None:
        if (
            not captured
            and cursor._id is None
            and not cursor._explain
            and cursor.collection.database.client is collection.database.client
            and cursor.collection.full_name == collection.full_name
        ):
            captured.append(cursor.clone())
        send_message(cursor, operation)

    with patch.object(Cursor, "_send_message", observed):
        read()
    assert captured, f"the production read executed no find on {collection.full_name}, so no selection was observed"
    return captured[0]


class MongoDBSelectionInspector:
    """Index/routing evidence for find cursors belonging to one synchronous client.

    Inspect the normal winning plan without changing hints or query options.
    An IXSCAN must narrow its leading key, or use a catalog-verified partial
    index. This is structural evidence, not a bound on examined documents or
    keys; a representative collection and separate cost proofs remain useful.
    Classic and SBE find plans are supported. Unknown/sharded/express/EOF plans
    fail with a capability explanation instead of claiming index coverage.
    """

    def __init__(self, client: Any) -> None:
        self.client = client

    def understands(self, selection: object) -> bool:
        return isinstance(selection, Cursor) and selection.collection.database.client is self.client

    def _cursor(self, selection: object) -> Cursor[Any]:
        assert isinstance(selection, Cursor) and self.understands(selection), (
            "MongoDB selection evidence needs a find cursor on the configured synchronous client"
        )
        return selection

    def index_served(self, selection: object) -> tuple[bool, str]:
        cursor = self._cursor(selection)
        explained = cursor.explain()
        plan = explained["queryPlanner"]["winningPlan"]
        plan = plan.get("queryPlan", plan)
        catalog = {index["name"]: index for index in cursor.collection.list_indexes()}
        reason = _unserved(plan, catalog)
        evidence = json.dumps(plan, default=str, indent=2)
        return reason is None, f"{reason}\n{evidence}" if reason else evidence

    def replica_read(self, selection: object) -> str | None:
        # Use the driver's effective preference (including an explicit session),
        # not whichever server a one-node test deployment happened to choose.
        preference = self._cursor(selection)._get_read_preference()
        return None if preference == ReadPreference.PRIMARY else repr(preference)

    def scan_counts(self, selection: object) -> tuple[float, float]:
        raise AssertionError(
            "MongoDB document/key counts are not SQL row-scan metrics; this inspector does not supply them"
        )

    def read_costs(self, selection: object) -> ReadCosts:
        raise AssertionError(
            "PostgreSQL buffer costs are unavailable for MongoDB; no synthetic block counts are supplied"
        )

    def statements_during(self, run: Callable[[], object]) -> list[str]:
        raise AssertionError("MongoDB does not execute SQL statements; SQL statement-count proofs are unavailable")


def _unserved(plan: dict[str, Any], catalog: dict[str, Any]) -> str | None:
    stage = plan.get("stage")
    if stage == "COLLSCAN":
        return "the selection performs a collection scan"
    if stage == "EOF":
        raise ObligationContractDesignError(
            "MongoDB returned EOF without a scan; seed representative data for index evidence"
        )
    if stage == "IXSCAN":
        key_pattern = plan.get("keyPattern", {})
        leading = next(iter(key_pattern), None)
        bounds = plan.get("indexBounds", {}).get(leading, [])
        if not bounds:
            raise ObligationContractDesignError("MongoDB IXSCAN has no leading-key bounds to inspect")
        if "[MinKey, MaxKey]" not in bounds and "[MaxKey, MinKey]" not in bounds:
            return None
        index = catalog.get(plan.get("indexName", ""), {})
        if index.get("partialFilterExpression"):
            return None
        return f"index {plan.get('indexName')!r} has an unbounded leading key {leading!r}"
    if stage in {
        "FETCH",
        "SUBPLAN",
        "LIMIT",
        "SKIP",
        "SORT",
        "SORT_MERGE",
        "OR",
        "PROJECTION_SIMPLE",
        "PROJECTION_DEFAULT",
        "PROJECTION_COVERED",
    }:
        children = plan.get("inputStages", []) or ([plan["inputStage"]] if "inputStage" in plan else [])
        if children:
            # Inspect all branches: one bounded index cannot excuse another scan.
            reasons = [_unserved(child, catalog) for child in children]
            return next((reason for reason in reasons if reason is not None), None)
    raise ObligationContractDesignError(
        f"MongoDB find plan stage {stage!r} is not supported by the selection inspector"
    )
