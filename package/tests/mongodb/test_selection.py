"""Selection evidence comes from actual PyMongo/Motor queries and real server plans."""

import asyncio
import os

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReadPreference

from pytest_obligation.integrations.mongodb import mongodb_host
from pytest_obligation.integrations.mongodb_selection import selection_built_by
from pytest_obligation.models import ObligationContractDesignError


@pytest.fixture
def populated(collection):
    collection.insert_many([{"_id": i, "state": "pending" if i < 3 else "done", "sequence": i} for i in range(2000)])
    return collection


def inspector(client, query):
    return mongodb_host(client, {"tests_support"}).inspector_for(query, capability="selection")


def test_capture_preserves_the_executed_find_and_tracks_production_changes(client, populated):
    populated.create_index([("state", 1), ("sequence", 1)])
    direction = -1

    def read():
        # A constructed but unevaluated decoy must not replace the actual query.
        populated.find({"state": "done"})
        return list(populated.find({"state": "pending"}).sort("sequence", direction).limit(2))

    query = selection_built_by(read, populated)
    assert [row["_id"] for row in query] == [2, 1]
    assert inspector(client, query).index_served(query)[0]
    assert inspector(client, query).replica_read(query) is None
    direction = 1
    assert [row["_id"] for row in selection_built_by(read, populated)] == [0, 1]
    # Inspecting a plan must not consume or change the captured query.
    assert [row["_id"] for row in query.clone()] == [2, 1]


@pytest.mark.parametrize("bad_plan", ["collection", "unrelated_index", "trailing_bound"])
def test_index_verdict_rejects_history_scans(client, populated, bad_plan):
    if bad_plan == "collection":
        query = populated.find({"state": "pending"})
    elif bad_plan == "unrelated_index":
        populated.create_index("sequence")
        query = populated.find({"state": "pending"}).hint("sequence_1")
    else:
        populated.create_index([("sequence", 1), ("state", 1)])
        query = populated.find({"state": "pending"}).hint("sequence_1_state_1")
    served, reason = inspector(client, query).index_served(query)
    assert not served
    assert "collection scan" in reason or "unbounded leading" in reason


def test_partial_index_is_verified_from_the_server_catalog(client, populated):
    populated.create_index("sequence", name="pending_only", partialFilterExpression={"state": "pending"})
    query = populated.find({"state": "pending"}).sort("sequence").hint("pending_only")
    assert inspector(client, query).index_served(query)[0]
    populated.drop_index("pending_only")
    populated.create_index("sequence", name="pending_only")
    served, reason = inspector(client, query).index_served(query)
    assert not served, "a reassuring index name cannot excuse a full index walk"
    assert "unbounded leading" in reason


@pytest.mark.parametrize(
    "preference", [ReadPreference.PRIMARY_PREFERRED, ReadPreference.SECONDARY_PREFERRED, ReadPreference.NEAREST]
)
def test_replica_capable_preferences_are_not_certified_by_a_single_primary(client, populated, preference):
    query = populated.with_options(read_preference=preference).find({"state": "pending"})
    assert inspector(client, query).replica_read(query) is not None


def test_capture_requires_an_executed_find_on_the_named_collection(populated):
    with pytest.raises(AssertionError, match="executed no find"):
        selection_built_by(lambda: populated.find({}), populated)
    other = populated.database.other
    with pytest.raises(AssertionError, match="executed no find"):
        selection_built_by(lambda: list(other.find()), populated)

    # A callback failure is propagated and the capture patch is released.
    def broken():
        list(populated.find())
        raise ValueError("callback failed")

    with pytest.raises(ValueError, match="callback failed"):
        selection_built_by(broken, populated)
    assert populated.count_documents({}) == 2000


def test_empty_collection_is_not_index_evidence(client, collection):
    # A nonexistent namespace produces EOF: no scan is not a useful index proof.
    query = collection.find({"state": "pending"})
    with pytest.raises(ObligationContractDesignError, match="representative data"):
        inspector(client, query).index_served(query)


def test_motor_query_is_captured_on_its_delegate_without_copying_its_filter(collection):
    async def exercise():
        client = AsyncIOMotorClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27028/?directConnection=true"))
        try:
            coll = client[collection.database.name].work
            await coll.insert_one({"state": "pending"})
            await coll.create_index("state")
            return coll
        except BaseException:
            client.close()
            raise

    with asyncio.Runner() as runner:
        coll = runner.run(exercise())
        try:

            async def read():
                return await coll.find({"state": "pending"}).to_list(length=None)

            query = selection_built_by(lambda: runner.run(read()), coll.delegate)
            assert list(query)[0]["state"] == "pending"
            assert inspector(coll.database.client.delegate, query).index_served(query)[0]
        finally:
            coll.database.client.close()


def test_unavailable_sql_buffer_metrics_do_not_invent_mongodb_units(client, populated):
    query = populated.find({})
    with pytest.raises(AssertionError, match="PostgreSQL buffer"):
        inspector(client, query).read_costs(query)


def test_a_healthy_or_branch_does_not_hide_an_unindexed_branch(client, populated):
    populated.create_index("state")
    query = populated.find({"$or": [{"state": "pending"}, {"sequence": 1000}]})
    served, reason = inspector(client, query).index_served(query)
    assert not served
    assert "collection scan" in reason
    populated.create_index("sequence")
    assert inspector(client, query).index_served(query)[0]


def test_other_clients_are_outside_the_capture_and_host_scope(client, populated):
    from pymongo import MongoClient

    with MongoClient(os.environ.get("MONGODB_URI", "mongodb://localhost:27028/?directConnection=true")) as other:
        other_collection = other[populated.database.name][populated.name]
        with pytest.raises(AssertionError, match="executed no find"):
            selection_built_by(lambda: list(other_collection.find()), populated)
        with pytest.raises(AssertionError, match="none"):
            inspector(client, other_collection.find())


def test_captured_collation_and_projection_are_not_retyped(client, populated):
    from pymongo.collation import Collation

    populated.insert_one({"_id": "uppercase", "state": "PENDING", "sequence": -1})
    collation = Collation(locale="en", strength=2)
    populated.create_index([("state", 1), ("sequence", 1)], collation=collation)

    def read():
        return list(populated.find({"state": "pending"}, {"_id": 1}).collation(collation).sort("sequence", 1).limit(1))

    query = selection_built_by(read, populated)
    assert list(query) == [{"_id": "uppercase"}]
    assert inspector(client, query).index_served(query)[0]


def test_existing_shared_selection_proofs_use_the_mongodb_host(client, collection):
    from pytest_obligation import ScheduledSelection
    from pytest_obligation.host import hosted
    from pytest_obligation.profiles.automatic_recovery import SELECTION_PROOFS, assert_selection_is_index_served
    from tests_support.mongodb_app import MongoDBOutbox

    collection.insert_many([{"_id": i, "done": i >= 3} for i in range(2000)])
    collection.create_index([("done", 1), ("_id", 1)])
    app = MongoDBOutbox(collection, lambda _identity: None)

    def pending():
        # ARRANGE: the real collection above contains owed and settled work.
        # REAL PRODUCTION: delegate to the outbox's own selection.
        # EXTERNAL SEAM: no provider or query replacement is needed for this read.
        # OBSERVE: the real cursor supplies both selected rows and database evidence.
        return app.pending()

    selection = ScheduledSelection(
        name="real MongoDB outbox selection",
        due_work=pending,
        unscheduled_because="The integration fixture is driven directly by its contract tests.",
    )
    with hosted(mongodb_host(client, {"tests_support"})):
        for proof in SELECTION_PROOFS:
            proof(selection)
        collection.drop_index("done_1__id_1")
        with pytest.raises(AssertionError, match="unbounded leading|collection scan"):
            assert_selection_is_index_served(selection)


def test_a_partial_index_covering_the_whole_collection_is_not_narrowing(client, populated):
    populated.create_index("sequence", name="all_documents", partialFilterExpression={"_id": {"$exists": True}})
    query = populated.find({"state": "pending"}).hint("all_documents")
    served, reason = inspector(client, query).index_served(query)
    assert not served, "the partial-index flag cannot certify a walk of every historical document"
    assert "entire representative collection" in reason


def test_observed_selection_keeps_all_results_and_all_executed_pages(client, populated):
    from pytest_obligation.integrations.mongodb_selection import observe_selection

    populated.create_index([("state", 1), ("sequence", 1)])

    def read_pages():
        for offset in (0, 2):
            for row in populated.find({"state": "pending"}).sort("sequence").skip(offset).limit(2):
                yield (row["_id"], row["state"])

    selection = observe_selection(read_pages, populated)
    assert list(selection) == [(0, "pending"), (1, "pending"), (2, "pending")]
    assert len(selection.cursors) == 2
    assert inspector(client, selection).index_served(selection)[0]
    assert inspector(client, selection).replica_read(selection) is None


def test_observed_selection_inspects_later_pages_too(client, populated):
    from pytest_obligation.integrations.mongodb_selection import observe_selection

    populated.create_index([("state", 1), ("sequence", 1)])
    populated.create_index("sequence")
    replica_capable = populated.with_options(read_preference=ReadPreference.SECONDARY_PREFERRED)

    def read_pages():
        yield from populated.find({"state": "pending"}).limit(1)
        yield from replica_capable.find({"state": "pending"}).hint("sequence_1").skip(1)

    selection = observe_selection(read_pages, populated)
    served, reason = inspector(client, selection).index_served(selection)
    assert not served
    assert "unbounded leading" in reason
    assert inspector(client, selection).replica_read(selection) is not None


@pytest.mark.parametrize("kind", ["aggregate", "distinct"])
def test_complete_selection_inspects_native_read_commands(client, populated, kind):
    from pytest_obligation.integrations.mongodb_selection import observe_selection

    populated.create_index([("state", 1), ("sequence", 1)])

    def read():
        if kind == "distinct":
            return populated.distinct("sequence", {"state": "pending"})
        return populated.aggregate(
            [
                {"$match": {"state": "pending"}},
                {"$group": {"_id": "$state", "total": {"$sum": "$sequence"}}},
            ]
        )

    selection = observe_selection(read, populated)
    assert list(selection) == ([0, 1, 2] if kind == "distinct" else [{"_id": "pending", "total": 3}])
    assert inspector(client, selection).index_served(selection)[0]
    assert inspector(client, selection).replica_read(selection) is None
    populated.drop_indexes()
    served, evidence = inspector(client, selection).index_served(selection)
    assert not served and "collection scan" in evidence


@pytest.mark.parametrize("kind", ["aggregate", "distinct"])
@pytest.mark.parametrize("preference", [ReadPreference.PRIMARY_PREFERRED, ReadPreference.SECONDARY_PREFERRED])
def test_native_read_commands_preserve_routing(client, populated, kind, preference):
    from pytest_obligation.integrations.mongodb_selection import observe_selection

    remote = populated.with_options(read_preference=preference)
    read = (
        (lambda: remote.distinct("state"))
        if kind == "distinct"
        else (lambda: remote.aggregate([{"$match": {"state": "pending"}}]))
    )
    selection = observe_selection(read, populated)
    assert inspector(client, selection).replica_read(selection) is not None


def test_a_foreign_collection_pipeline_cannot_certify_only_its_first_scan(client, populated):
    from pytest_obligation.integrations.mongodb_selection import observe_selection

    selection = observe_selection(
        lambda: populated.aggregate(
            [
                {"$match": {"state": "pending"}},
                {"$lookup": {"from": "other", "localField": "state", "foreignField": "state", "as": "joined"}},
            ]
        ),
        populated,
    )
    with pytest.raises(ObligationContractDesignError, match="pipeline stage"):
        inspector(client, selection).index_served(selection)


@pytest.mark.parametrize("kind", ["aggregate", "distinct"])
def test_native_commands_keep_collation_and_query_options(client, populated, kind):
    from pymongo.collation import Collation

    from pytest_obligation.integrations.mongodb_selection import observe_selection

    fold = Collation("en", strength=2)
    populated.create_index("state", name="state_casefold", collation=fold)
    pipeline = [{"$match": {"state": "PENDING"}}]

    def read():
        if kind == "distinct":
            return populated.distinct("state", {"state": "PENDING"}, collation=fold)
        return populated.aggregate(pipeline, collation=fold, hint="state_casefold")

    selection = observe_selection(read, populated)
    assert len(list(selection)) == (1 if kind == "distinct" else 3)
    assert selection.commands[0].command["collation"] == fold.document
    assert inspector(client, selection).index_served(selection)[0]
    if kind == "aggregate":
        pipeline[0]["$match"]["state"] = "settled"
        assert selection.commands[0].command["pipeline"][0]["$match"]["state"] == "PENDING"
        assert selection.commands[0].command["hint"] == "state_casefold"
