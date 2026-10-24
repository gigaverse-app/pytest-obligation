"""Observe native PyMongo reads and inspect their real MongoDB selection plans.

Motor uses the same synchronous cursors in its executor. No predicate, sort or
limit is reconstructed here. Unsupported plan shapes and SQL-only metrics stay
explicit; the inspector never converts missing evidence into a passing proof.
"""

import json
from collections.abc import Callable, Iterable, Iterator
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from pymongo import ReadPreference
from pymongo.synchronous.aggregation import _CollectionAggregationCommand
from pymongo.synchronous.collection import Collection
from pymongo.synchronous.cursor import Cursor
from pymongo.synchronous.pool import Connection

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
    _, cursors, _ = _observed_read(read, collection)
    assert cursors, f"the production read executed no find on {collection.full_name}"
    return cursors[0]


@dataclass(frozen=True)
class _ObservedCommand:
    collection: Collection[Any]
    command: dict[str, Any]
    preference: Any

    def explain(self) -> dict[str, Any]:
        # These stages only consume the selected collection. Foreign reads and
        # writes need separate evidence; never certify just their first scan.
        for stage in self.command.get("pipeline", []):
            if next(iter(stage)) not in {
                "$match",
                "$unwind",
                "$sort",
                "$limit",
                "$skip",
                "$project",
                "$replaceWith",
                "$replaceRoot",
                "$group",
                "$set",
                "$addFields",
                "$unset",
                "$count",
            }:
                raise ObligationContractDesignError(f"MongoDB pipeline stage {next(iter(stage))!r} is not supported")
        return self.collection.database.command(
            {"explain": self.command, "verbosity": "queryPlanner"},
            read_preference=self.preference,
        )

    def _get_read_preference(self) -> Any:
        return self.preference


@dataclass(frozen=True)
class MongoSelection:
    """Actual production results beside the native reads executed to obtain them."""

    rows: tuple[Any, ...]
    cursors: tuple[Cursor[Any], ...]
    commands: tuple[_ObservedCommand, ...] = ()

    def __iter__(self) -> Iterator[Any]:
        return iter(self.rows)


def observe_selection(read: Callable[[], Iterable[Any]], collection: Collection[Any]) -> MongoSelection:
    """Observe a complete production read, including every page it executes.

    The callback owns all selection, pagination and result conversion. Its
    iterator is exhausted inside the observation scope; no query is rebuilt,
    limited or expanded by the harness. For async code, finish the read on its
    owning loop and return its results through the callback.
    """
    rows, cursors, commands = _observed_read(lambda: tuple(read()), collection)
    return MongoSelection(rows, cursors, commands)


def _observed_read(
    read: Callable[[], Any], collection: Collection[Any]
) -> tuple[Any, tuple[Cursor[Any], ...], tuple[_ObservedCommand, ...]]:
    if not isinstance(collection, Collection):
        raise ObligationContractDesignError("pass a synchronous PyMongo collection, or Motor collection.delegate")
    captured: list[Cursor[Any]] = []
    commands: list[_ObservedCommand] = []
    target: ContextVar[Collection[Any] | None] = ContextVar("mongo_read_collection", default=None)
    command_call = Connection.command
    send_message = Cursor._send_message

    def observed(cursor: Cursor[Any], operation: Any) -> None:
        if (
            cursor._id is None
            and not cursor._explain
            and cursor.collection.database.client is collection.database.client
            and cursor.collection.full_name == collection.full_name
        ):
            captured.append(cursor.clone())
        send_message(cursor, operation)

    def observed_command(connection: Any, database: str, command: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            kwargs.get("client") is collection.database.client
            and database == collection.database.name
            and (command.get("aggregate") == collection.name or command.get("distinct") == collection.name)
        ):
            copied = deepcopy(command)
            if kwargs.get("collation"):
                copied["collation"] = deepcopy(kwargs["collation"])
            native = target.get()
            if native is None:
                raise ObligationContractDesignError("MongoDB read command has no collection routing evidence")
            # Direct connections rewrite PRIMARY to PRIMARY_PREFERRED on the
            # wire. Inspect the native collection/session policy before that
            # transport adaptation, just as find cursors do.
            preference = native._read_preference_for(kwargs.get("session"))
            commands.append(_ObservedCommand(native, copied, preference))
        return command_call(connection, database, command, *args, **kwargs)

    def scoped(original: Callable[..., Any], collection_of: Callable[[Any], Collection[Any]]) -> Callable[..., Any]:
        def run(owner: Any, *args: Any, **kwargs: Any) -> Any:
            token = target.set(collection_of(owner))
            try:
                return original(owner, *args, **kwargs)
            finally:
                target.reset(token)

        return run

    with (
        patch.object(Cursor, "_send_message", observed),
        patch.object(Connection, "command", observed_command),
        patch.object(Collection, "_command", scoped(Collection._command, lambda owner: owner)),
        patch.object(
            _CollectionAggregationCommand,
            "get_cursor",
            scoped(_CollectionAggregationCommand.get_cursor, lambda owner: owner._target),
        ),
    ):
        result = read()
    assert captured or commands, f"the production read executed no find or supported command on {collection.full_name}"
    return result, tuple(captured), tuple(commands)


class MongoDBSelectionInspector:
    """Index/routing evidence for native reads belonging to one synchronous client.

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
        cursors = (*selection.cursors, *selection.commands) if isinstance(selection, MongoSelection) else (selection,)
        return bool(cursors) and all(
            isinstance(cursor, (Cursor, _ObservedCommand)) and cursor.collection.database.client is self.client
            for cursor in cursors
        )

    def _cursors(self, selection: object) -> tuple[Cursor[Any] | _ObservedCommand, ...]:
        assert self.understands(selection), (
            "MongoDB selection evidence needs native reads on the configured synchronous client"
        )
        if isinstance(selection, MongoSelection):
            return (*selection.cursors, *selection.commands)
        assert isinstance(selection, Cursor)
        return (selection,)

    def index_served(self, selection: object) -> tuple[bool, str]:
        evidence = []
        for cursor in self._cursors(selection):
            served, plan = self._index_served(cursor)
            if not served:
                return served, plan
            evidence.append(plan)
        return True, "\n".join(evidence)

    def _index_served(self, cursor: Cursor[Any] | _ObservedCommand) -> tuple[bool, str]:
        explained = cursor.explain()
        planner = explained.get("queryPlanner")
        if planner is None:
            native = [stage["$cursor"]["queryPlanner"] for stage in explained.get("stages", []) if "$cursor" in stage]
            if len(native) != 1:
                raise ObligationContractDesignError("MongoDB read explain has no single supported collection scan plan")
            planner = native[0]
        plan = planner["winningPlan"]
        plan = plan.get("queryPlan", plan)
        catalog = {index["name"]: index for index in cursor.collection.list_indexes()}
        partial = [index for index in catalog.values() if index.get("partialFilterExpression")]
        if partial:
            total = cursor.collection.count_documents({})
            for index in partial:
                # A partial flag can still cover every historical document
                # (for example _id exists). The fixture must exhibit narrowing.
                index["narrows_representative_collection"] = (
                    cursor.collection.count_documents(index["partialFilterExpression"]) < total
                )
        reason = _unserved(plan, catalog)
        evidence = json.dumps(plan, default=str, indent=2)
        return reason is None, f"{reason}\n{evidence}" if reason else evidence

    def replica_read(self, selection: object) -> str | None:
        # Use the driver's effective preference (including an explicit session),
        # not whichever server a one-node test deployment happened to choose.
        for cursor in self._cursors(selection):
            preference = cursor._get_read_preference()
            if preference != ReadPreference.PRIMARY:
                return repr(preference)
        return None

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
    if stage in {"IXSCAN", "DISTINCT_SCAN"}:
        key_pattern = plan.get("keyPattern", {})
        leading = next(iter(key_pattern), None)
        bounds = plan.get("indexBounds", {}).get(leading, [])
        if not bounds:
            raise ObligationContractDesignError("MongoDB IXSCAN has no leading-key bounds to inspect")
        if "[MinKey, MaxKey]" not in bounds and "[MaxKey, MinKey]" not in bounds:
            return None
        index = catalog.get(plan.get("indexName", ""), {})
        if index.get("partialFilterExpression"):
            if index.get("narrows_representative_collection"):
                return None
            return f"partial index {plan.get('indexName')!r} spans the entire representative collection"
        return f"index {plan.get('indexName')!r} has an unbounded leading key {leading!r}"
    if stage in {
        "FETCH",
        "GROUP",
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
