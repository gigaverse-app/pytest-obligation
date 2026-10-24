# MongoDB histories and selection evidence

Install `pytest-obligation[mongodb]` and configure
`mongodb_host(client, production_packages={"your_app"})`. For Motor, pass the
Motor client's `.delegate`; run async application calls to completion on the
same event loop your client uses.

The host counts acknowledged wire writes, including `findAndModify`, bulk
batches, `$out`/`$merge`, and explicit transaction commits. Transactional writes
are not durable boundaries until commit. Reads and aborted transactions do not
count. Each bulk wire batch is one boundary; a batch can contain multiple
documents. A batch that inserts some documents before reporting a duplicate-key
error still exposes its acknowledged boundary. Unknown commands count conservatively. Writes using `w=0` are refused before dispatch, including ordered bulks whose
driver internally converts them into acknowledged commands. `$out` and `$merge`
have real-server controls alongside read-only aggregation.

Death fences subsequent commands on that client, including commands issued
from Motor executor threads and finally blocks. Independent clients remain
available to observe persisted state. Lost replies let the write land and raise
PyMongo `ConnectionFailure`; normal driver and application error handling runs.
Configure driver retries as production does: they are part of that behavior.

The adapter supports PyMongo 4.9 through 4.18, selecting the matching wire
boundaries for each version. The optional dependency stays below 4.19 until
that minor version has been validated.
Native `AsyncMongoClient` is not supported; it is rejected instead of silently
producing empty histories. Other clients, detached tasks and other processes
are outside this host's scope. Server TTL time is not frozen. This host does not supply schedule or transport
evidence; configure those separately. Find-query index and routing evidence is
available through the selection inspector below.

The real-server suite includes a transaction control, Motor thread control,
lost acknowledgements, blocked cleanup and generated outbox histories. Removing
provider deduplication makes the same generated history detect a duplicate effect.

## Required adoption surface

Use this host inside an `ObligationContract` adoption with a collected
`@due_work_contract_suite(CONTRACT)` class. The adapter supplies fault injection;
it does not replace the contract or generate cases on its own. See
[required adoption shape](adopting.md#required-adoption-shape) for declarations
and generated test/report evidence.


## Observe a production find query

The host also inspects native PyMongo `Cursor` selections for the shared
index-served and primary-routing proofs. If production creates its cursor
inside a repository or HTTP endpoint, capture that query rather than copying
its filter into the test:

```python
from pytest_obligation.integrations.mongodb_selection import selection_built_by

# Run the actual read to completion; use your existing async runner for Motor.
query = selection_built_by(read_production_orders, orders_collection)
inspector = mongodb_host(client, {"your_app"}).inspector_for(
    query, capability="order selection"
)
served, evidence = inspector.index_served(query)
assert served, evidence
assert inspector.replica_read(query) is None
```

For Motor, pass `orders_collection.delegate` and the client's `.delegate`.
The callback must finish on the client's event loop. The helper observes the
first **executed** find on that collection and client. An unevaluated cursor,
an unrelated collection, or another client cannot satisfy the observation.
It runs the callback normally, so use a read-only entry point. It preserves
projection, collation, sort, hint and limit. In particular, a captured first
page is still a page; it is not an unbounded recovery selection or evidence
that a whole tick has a page bound.

The inspector explains the captured cursor using MongoDB's normal planner.
Every scan in the winning classic or SBE find plan must narrow a leading
index key, or use a partial index verified in the server catalog. An index
name alone, a trailing-key bound behind an unbounded leading key, or another
healthy branch cannot excuse a full scan. Seed representative data: an EOF
plan supplies no index evidence. Unsupported stages, including sharded and
express plans, raise a capability error rather than passing or accusing the
application of an index defect.

Routing checks the driver's effective read preference, including session
configuration. A preference that can choose a secondary fails even when the
local test server happens to be primary. This does not inspect infrastructure
misrouting behind a connection string.

This is structural selection evidence. It does not establish a cost ceiling,
backlog monitoring, scheduling, in-flight exclusion, or the full automatic
recovery contract. PostgreSQL buffer costs, SQL statement counts, and generic
row-scan metrics are explicitly unavailable; MongoDB documents and index keys
are different units. Existing write/death and lost-reply behavior is unchanged.

References: [PyMongo cursor cloning and explain](https://pymongo.readthedocs.io/en/4.18.0/api/pymongo/cursor.html)
and [MongoDB winning-plan shapes](https://www.mongodb.com/docs/manual/reference/explain-results/).
