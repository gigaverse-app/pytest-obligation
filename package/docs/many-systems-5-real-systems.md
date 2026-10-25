# 5. Trust the result, and use your real systems

[Previous: 4. Make it a generated suite](many-systems-4-suite.md) · [All chapters](tutorial-many-systems.md#chapters) · [Vocabulary](vocabulary.md)

Two questions remain: can you trust a green result, and how does the example
map to the systems you actually run?

## Why you can trust a green result

A test suite that passes because it measured the wrong thing is worse than no
suite. pytest-obligation checks the experiment itself, and you will meet these
checks while writing bindings.

**Your binding must call your code.** The first draft of this tutorial's
bindings wrote the steps as `lambda shop: shop.app.place_order(CART, 30)` and
`lambda shop: shop.app.on_order_placed(CART)`. The harness refused them before
running anything:

```text
AssertionError: checkout queue: handoff[send receipt].transition is test code that references no
production callable, class, or module, so the proofs would measure a test-defined implementation
rather than the runtime. Bind the production command ... — the production function itself, or a
thin closure that calls it.
```

The fix was to name the production class in the closure, as in
`lambda shop: checkout.place_order(shop.app, CART, 30)`. The check is strict
because the most common way to get a false green is to bind a copy of
production logic in the test, which then stays green forever after production
changes.

**The experiment must be able to fail.** Before comparing any histories, the
harness checks that:

- normal operation changes what you observe (an observation that cannot see the
  work would make every history agree);
- normal operation gives the same result when run twice;
- the step actually commits;
- every interrupted history was really interrupted;
- recovery changed something in at least one history (a recovery that does
  nothing would agree with an equally unfinished normal run);
- every declared external call was actually called.

These are [positive controls](vocabulary.md#positive-control). The full list of
refused shortcuts is in [false greens](false-greens.md).

**What a pass does not mean.** A pass means the specific histories generated
here reached the required outcome against these bindings. It does not prove
the application correct in general. Two limits matter for multi-system work:

- Commits are counted on the one connection the host watches. A write made on
  another connection, or to another database, is neither counted nor
  interrupted; model that system as an external call instead.
- Deaths happen inside the step under test. A consumer that recovery delivers
  is not killed after its own calls; test it with its own history, as chapter 2
  did, or with a replay binding, as chapter 4 did.

[What a green result means](what-a-green-result-means.md) covers the rest.

## Your real systems

The example's stand-ins map to the systems you run like this. The integrations
named here are shortcuts; anything not listed takes part the way this
tutorial's stand-ins did, through an `ExternalCall` and a delivery you write.

| In the example | In your application | How pytest-obligation takes part |
| --- | --- | --- |
| SQLite + `sqlite_worker_killer` | PostgreSQL through Django | `django_host()` counts commits and kills the worker after each; add `celery_publication_breaker` to refuse each Celery publish, and `django_receiver_breaker` to fail each signal receiver. [Integrations](integrations.md) |
| SQLite + `sqlite_worker_killer` | MongoDB | `mongodb_host(client, ...)` counts acknowledged writes and transaction commits, and loses replies after a write lands. [MongoDB](mongodb.md) |
| SQLite + `sqlite_worker_killer` | Redis as the store of record | `redis_host(client, ...)` counts writes and pipelines, and loses write replies. |
| `FakeCache` | Redis as a cache | An `ExternalCall` on your cache client's write method. |
| `FakeBroker` | Kafka | An `ExternalCall` on the producer's `send_and_wait` (the coroutine that does the work). For consumers, the `[aiokafka]` extra injects deaths and lost replies at offset commits. [aiokafka](aiokafka.md) |
| `FakeBroker` + `recover` | Celery or RQ | The real worker as the delivery; the `[celery]` and `[rq]` extras run real workers, refuse publications and fail callbacks. |
| `FakeBroker` + `recover` | procrastinate or django-tasks-db | The job table is the queue, so nothing is lost in transit; the integration runs the library's real worker as the delivery. |
| `recover()` | A Prefect flow | `prefect_flow_call` runs the real flow body as the step or the recovery; `prefect_host` composes with your database's host. [Prefect](prefect.md) |
| `recover()` | A DBOS workflow | [Process histories](how-it-works.md#crash-histories) kill a real child process at named points and restart the application through its own startup. |
| `FakePayments`, `FakeMailer` | Payment and email APIs | An `ExternalCall` on your client method, with a fake that records every effect. For a provider that may reply without applying (an HTTP 202 event API), see `ProviderControl` and the [Shopify billing simulator](shopify.md). |

The pattern stays the same: one host for the database that records what is
owed, one `ExternalCall` per outside system, one delivery that is how your
system really moves work, and one observation that reads every system the
customer would notice.

## What you learned

| Name | Kind | Meaning |
| --- | --- | --- |
| Host, `worker_killer`, `CommitWorker` | pytest-obligation | How the harness finds and interrupts your commits |
| `HandoffHistory` | pytest-obligation | One step to test under every fault, with its setup, observation and required outcome |
| `ExternalCall` | pytest-obligation | An outside system; the worker dies right after each call in one history |
| `CallableDelivery` | pytest-obligation | How published work is delivered, lost and recovered |
| `assert_crash_at_every_commit_converges` | pytest-obligation | Run every history and require them all to match normal operation |
| `HistoriesDiverged` | pytest-obligation | The failure: which history, and what it reached |
| `ObligationContract`, `@due_work_contract_suite` | pytest-obligation | Declare once; pytest generates the cases |
| `Claim`, `Decline`, `NotApplicable`, `NotAssessed`, `handoff_gaps` | pytest-obligation | Honest answers per profile, and findings recorded as strict expected failures |
| `ReplaySafeEffect` | pytest-obligation | Prove that a redelivered event changes nothing the customer sees |

Next: if you maintain a task queue or workflow library rather than an
application, [the framework tutorial](tutorial-framework-authors.md) shows how
to prove your library's own guarantees and hand your users a ready-made
contract. To bind the remaining profiles, read [adopting](adopting.md).
