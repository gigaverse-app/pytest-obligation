# Test a workflow that spans many systems

[All tutorials](tutorials.md) · [Vocabulary](vocabulary.md)

Your checkout charges a card, saves the order in PostgreSQL, publishes an event
to Kafka, refreshes a Redis cache and emails a receipt. Every line is correct.
And yet, now and then:

- a customer is **charged and gets no order**;
- a customer gets **two receipts**;
- an order is placed and **nothing downstream ever hears about it**.

None of these are bugs in a line of code. They happen *between* lines: the
worker is killed by a deploy right after the charge, the broker drops a message,
recovery re-runs a step whose effect already happened. To test them by hand you
would have to stop the process at each of those points, for each system,
restart recovery, and check all five systems afterwards. Then do it again every
time the code changes, because the list of points changes with it.

pytest-obligation does that for you. You describe the workflow once: how to set
it up, which production function to run, and what the customer should end up
with. It finds the commit boundaries and external calls itself, kills the
worker at each one, loses each message, runs your recovery, and checks that
every one of those histories ends exactly like the normal run.

In this tutorial you will:

1. write the happy-path test most teams write, and see it pass;
2. describe the same workflow to pytest-obligation, and watch it find the
   charge-without-an-order;
3. find the duplicate receipt in the queue consumer;
4. fix both, and watch the tests grow on their own;
5. turn the description into a generated test suite with a report;
6. see why you can trust the green result;
7. map the example's fakes to your real PostgreSQL, MongoDB, Redis, Kafka,
   Celery, Prefect and email providers.

You need Python 3.12+, Git and [uv](https://docs.astral.sh/uv/). Everything runs
in memory: SQLite stands in for the database and small Python classes stand in
for the other four systems, so there is nothing to install or configure.

```bash
git clone https://github.com/gigaverse-app/pytest-obligation.git
cd pytest-obligation
uv sync --all-packages --locked
cd examples/checkout_tutorial
uv run --project ../.. --no-sync pytest
```

The last command runs every test in this tutorial. It should end with
`16 passed, 2 xfailed`.

## How to read the code

Each code block mixes three kinds of names:

| Kind | How to recognise it | What the tutorial does with it |
| --- | --- | --- |
| **Python and pytest** | `sqlite3`, `contextlib`, `pytest.raises` | Assumes you know it |
| **The example application** | Imported from `checkout`, `providers`, `checkout_bindings` | Shows it in full; it is what you replace with your own code |
| **pytest-obligation** | Imported from `pytest_obligation` | Explains it before its first use, with a short comment in the code and a table after the block |

Bindings also carry four labelled comments: `ARRANGE`, `REAL PRODUCTION`,
`EXTERNAL SEAM` and `OBSERVE`. They tell a reviewer which line is test setup,
which is your production code, which is a stand-in for an outside system, and
what proves the work happened. For the profile bindings you meet in step 5,
pytest-obligation refuses to build a contract without them.

## The workflow

The example lives in [`examples/checkout_tutorial`](../../examples/checkout_tutorial).
The application is the `checkout` package; the tests and their stand-ins are in
`tests/`.

```text
place_order (web request)                on_order_placed (queue consumer)
  1. charge the card       -> payments     4. cache the status   -> cache
  2. save the order        -> database     5. email the receipt  -> mailer
  3. publish order_placed  -> broker ---->  6. record "receipt sent" -> database
```

Here is the version most applications start with,
[`checkout/naive.py`](../../examples/checkout_tutorial/checkout/naive.py):

```python
class NaiveCheckout:
    def place_order(self, cart: str, amount: int) -> None:
        """The web request: charge, save, announce."""
        charge = self.payments.charge(amount, key=None)
        with self.db:
            self.db.execute(
                "INSERT INTO orders(cart, amount, status, charge) VALUES (?, ?, 'paid', ?)", (cart, amount, charge)
            )
        self.broker.publish("order_placed", cart)

    def on_order_placed(self, cart: str) -> None:
        """The queue consumer: refresh the cache, send the receipt, remember that it was sent."""
        status, receipt_sent = self.db.execute(
            "SELECT status, receipt_sent FROM orders WHERE cart = ?", (cart,)
        ).fetchone()
        self.cache.set(f"order:{cart}", status)
        if not receipt_sent:
            self.mailer.send(cart, key=None)
            with self.db:
                self.db.execute("UPDATE orders SET receipt_sent = 1 WHERE cart = ?", (cart,))

    def recover(self) -> None:
        """A sweep a careful team adds: re-run the consumer for orders whose receipt is not recorded."""
        for (cart,) in self.db.execute("SELECT cart FROM orders WHERE receipt_sent = 0").fetchall():
            self.on_order_placed(cart)
```

The constructor (not shown) receives the database connection and the four
outside systems: `payments`, `broker`, `cache` and `mailer`. Their methods are
listed in [`checkout/ports.py`](../../examples/checkout_tutorial/checkout/ports.py).
`key=None` means "send no [idempotency key](vocabulary.md#replay-safe-and-idempotency-key)".

Note the `recover()` sweep. This team was careful: if an event is lost, the
sweep finds the order without a receipt and finishes it.

## 1. The test you would normally write

[`tests/test_happy_path.py`](../../examples/checkout_tutorial/tests/test_happy_path.py)
places an order, delivers the event, and checks every system:

```python
@pytest.mark.parametrize("checkout", [NaiveCheckout, ReliableCheckout])
def test_an_order_is_charged_cached_and_receipted(checkout) -> None:  # noqa: ANN001 - either checkout class
    with fresh_shop(checkout) as shop:
        shop.app.place_order(CART, 30)
        shop.broker.deliver_all()

        assert everything_the_customer_sees(shop) == ("paid", 1, 1, "paid")
```

The tuple is `(order status, charges made, receipts delivered, cached status)`.
It passes for the naive checkout, and for the reliable one you will build in
step 4. **The happy path cannot tell them apart**, because the difference
between them only shows when something fails between two lines.

How many such points are there? In `place_order` alone: after the charge, after
the commit, after the publish, and the case where the published event is lost.
Four tests, each with its own setup, fault and five-system assertion. The
consumer adds four more. Change one line of either function and the list
changes. Nobody keeps that list up to date by hand.

## 2. Describe the workflow once

You give pytest-obligation three things: a way to count your commits, your
workflow's moving parts, and what the result must be.

### Tell it where your commits are

pytest-obligation never guesses where a transaction ends. A **host** tells it.
For Django with PostgreSQL, MongoDB or Redis, an
[integration](integrations.md) supplies one. For this plain SQLite application,
[`tests/sqlite_host.py`](../../examples/checkout_tutorial/tests/sqlite_host.py)
supplies a connection class that reports each commit:

```python
from pytest_obligation.worker_death import CommitWorker

# The worker the harness is currently counting, while a history's transition runs.
_current: CommitWorker | None = None


class CountedConnection(sqlite3.Connection):
    """A SQLite connection whose commits the harness can count and interrupt."""

    def execute(self, sql: str, parameters: object = (), /) -> sqlite3.Cursor:
        if _current is not None:
            _current.refuse_if_dead()
        return super().execute(sql, parameters)  # type: ignore[arg-type]

    def commit(self) -> None:
        if _current is not None:
            _current.refuse_if_dead()
        super().commit()
        if _current is not None:
            _current.committed()
```

The full file also routes `with connection:` through `commit()`, and defines
`sqlite_worker_killer`, which creates a `CommitWorker` for each run.

| Name | Comes from | What it does |
| --- | --- | --- |
| `CommitWorker` | pytest-obligation | Counts commits. When the harness asked it to die after commit *k*, `committed()` raises `WorkerDied` at that commit; from then on `refuse_if_dead()` raises too, because a dead process's connection runs nothing more. |
| `sqlite_worker_killer` | This example | The [worker killer](vocabulary.md#host-and-worker-killer): given *k*, it installs a fresh `CommitWorker` while the step runs. |
| `CountedConnection` | This example | Calls the worker on every statement and commit. Your production code is unchanged; only the test passes this class as the connection factory. |

The host is configured once, in [`tests/conftest.py`](../../examples/checkout_tutorial/tests/conftest.py):

```python
# The host: which packages are production code, and how to kill a worker right after each commit.
configure(Host(production_packages=frozenset({"checkout"}), worker_killer=sqlite_worker_killer))
```

`production_packages` names the code under test. pytest-obligation uses it to
check that your bindings call that code rather than re-implement it (step 6).

**A host counts commits on one database connection.** Your other systems take
part as external calls, below. That is the right model for most applications:
one database is the record of what is owed, and everything else is an outside
effect that may or may not have happened.

### Stand-ins for the other systems

[`tests/providers.py`](../../examples/checkout_tutorial/tests/providers.py) has
one small class per outside system. Each models only what the real system does
with a request, and records every effect so a test can count it:

| Class | Models | Records |
| --- | --- | --- |
| `FakePayments` | A card processor: every call is a new charge, unless it repeats a key it has seen | `charges` |
| `FakeBroker` | A queue: events wait until delivered to the consumer, or are lost | `waiting` |
| `FakeCache` | A key-value cache such as Redis | `values`, `writes` |
| `FakeMailer` | An email service: every call delivers a message, unless it repeats a key | `delivered` |

### Describe the step and its required outcome

[`tests/checkout_bindings.py`](../../examples/checkout_tutorial/tests/checkout_bindings.py)
connects the checkout to the harness. First, a fresh shop for every run, and one
observation across all five systems:

```python
@contextmanager
def fresh_shop(checkout: type[CheckoutT]) -> Iterator[Shop[CheckoutT]]:
    """A new shop for one history, reachable by the delivery while the history runs."""
    shop = new_shop(checkout)
    current.append(shop)
    try:
        yield shop
    finally:
        current.remove(shop)
        shop.app.db.close()


def everything_the_customer_sees(shop: Shop[Any]) -> tuple[str | None, int, int, str | None]:
    """Order status, charges made, receipts delivered, cached status: one snapshot across all five systems."""
    row = shop.app.db.execute("SELECT status FROM orders WHERE cart = ?", (CART,)).fetchone()
    return (
        row[0] if row else None,
        len(shop.payments.charges),
        shop.mailer.delivered.count(CART),
        shop.cache.values.get(f"order:{CART}"),
    )


# What one paid order must leave behind, decided before anything runs.
ONE_PAID_ORDER = ("paid", 1, 1, "paid")
```

`new_shop()` (in the same file) wires an in-memory SQLite database with
`CountedConnection` to fresh stand-ins. `CheckoutT` stands for either checkout
class, so the same bindings test both. `current` lets the delivery below reach
whichever shop the current run created.

Next, how events travel in this system. A **delivery** tells the harness how
published work reaches its consumer, how it is lost, and how production
recovers:

```python
def delivery(checkout: type[CheckoutT]) -> CallableDelivery:
    """How published events reach the consumer, how they get lost, and how production recovers."""
    return CallableDelivery(
        name=f"{checkout.__name__} queue",
        deliver=lambda: current[-1].broker.deliver_all(),  # what a running consumer does
        lose=lambda: current[-1].broker.lose_all(),  # what a broker outage does
        # REAL PRODUCTION: the sweep the application schedules, run after every history.
        recover=lambda: checkout.recover(current[-1].app),
    )
```

Finally, the step itself. A **`HandoffHistory`** names one step that commits
state and passes work on, a [handoff](vocabulary.md#handoff):

```python
def place_order_history(checkout: type[CheckoutT]) -> HandoffHistory:
    return HandoffHistory(
        name="place order",
        # ARRANGE: a new shop per history, so no history sees another's leftovers.
        arrange=lambda: fresh_shop(checkout),
        # REAL PRODUCTION: the web request, called exactly as the app calls it.
        transition=lambda shop: checkout.place_order(shop.app, CART, 30),
        # OBSERVE: one snapshot across all five systems; every history must end with this same snapshot.
        observe=everything_the_customer_sees,
        expected=ONE_PAID_ORDER,
        # EXTERNAL SEAM: the systems outside the database; the worker also dies right after each call.
        external_calls=(ExternalCall(FakePayments, "charge"), ExternalCall(FakeBroker, "publish")),
    )
```

| Name | Comes from | What it does |
| --- | --- | --- |
| `HandoffHistory` | pytest-obligation | One step to test under every fault. The harness runs it many times; each run, followed by recovery, is a [history](vocabulary.md#history). |
| `arrange` | Field | Builds a fresh starting point for each history. It may be a context manager; it stays open until the history's last observation. |
| `transition` | Field | Your production step. It must call your code, not a copy of it. |
| `observe` | Field | A comparable snapshot of everything the customer would notice. Every history must end with the same snapshot as the normal run. |
| `expected` | Field | The outcome you decided before running anything. It catches a step that is wrong even when every history agrees. |
| `ExternalCall(owner, "method")` | pytest-obligation | Marks a call into an outside system. While the step runs, the harness wraps that method and, in one history per call, kills the worker right after it returns: the outside system acted, your process did nothing more. |
| `CallableDelivery` | pytest-obligation | The [delivery](vocabulary.md#delivery): `deliver` and `lose` are what happens to published messages; `recover` is what production runs afterwards. |

Notice what you did **not** write: the list of points where things can fail. You
named the outside systems; the harness finds the commits itself.

## 3. Find the charge with no order

Now run the description against the naive checkout.
`assert_crash_at_every_commit_converges` runs every history and compares them:

```python
from pytest_obligation import assert_crash_at_every_commit_converges

assert_crash_at_every_commit_converges(delivery(NaiveCheckout), place_order_history(NaiveCheckout))
```

It fails:

```text
pytest_obligation.HistoriesDiverged: NaiveCheckout queue: handoff 'place order': normal operation
reaches ('paid', 1, 1, 'paid'), but these histories reach something else:
{'worker died after external call 1': (None, 1, 0, None)}. Work was lost or repeated. A loss is
work handed off only by a message, a commit hook or code after a commit that a dead worker never
runs: commit the handoff with the state that owes it, or make that state selectable by recovery. ...
```

Read it like this: in the history where the worker died right after **external
call 1** (the charge), the customer ended with no order, one charge, no receipt
and nothing cached. Recovery could not help: it looks for orders, and there is
no order. The card was charged anyway.

These are the five histories the harness ran, all from that one description:

| History | What happened | Final snapshot |
| --- | --- | --- |
| normal operation | Nothing failed | `('paid', 1, 1, 'paid')` |
| notifications lost | The `order_placed` event was dropped; recovery found the order | `('paid', 1, 1, 'paid')` |
| worker died after commit 1 | Died after saving the order, before publishing | `('paid', 1, 1, 'paid')` |
| worker died after external call 1 | Died right after the charge | `(None, 1, 0, None)` **diverged** |
| worker died after external call 2 | Died right after publishing | `('paid', 1, 1, 'paid')` |

The careful `recover()` sweep handled the lost event and the death after the
commit. Nothing handles a charge that happened before anything was written down.

## 4. Find the receipt sent twice

The consumer is a handoff too: it emails, then records that it emailed. Its
history starts from a paid order whose event has not been consumed:

```python
def send_receipt_history(checkout: type[CheckoutT]) -> HandoffHistory:
    return HandoffHistory(
        name="send receipt",
        # ARRANGE: a paid order whose event has not been consumed yet.
        arrange=lambda: shop_with_an_undelivered_event(checkout),
        # REAL PRODUCTION: the queue consumer.
        transition=lambda shop: checkout.on_order_placed(shop.app, CART),
        # OBSERVE: the same snapshot and the same required outcome as placing the order.
        observe=everything_the_customer_sees,
        expected=ONE_PAID_ORDER,
        # EXTERNAL SEAM: the cache write and the email.
        external_calls=(ExternalCall(FakeCache, "set"), ExternalCall(FakeMailer, "send")),
    )
```

Run against the naive checkout, it diverges in a different way:

```text
pytest_obligation.HistoriesDiverged: NaiveCheckout queue: handoff 'send receipt': normal operation
reaches ('paid', 1, 1, 'paid'), but these histories reach something else:
{'worker died after external call 2': ('paid', 1, 2, 'paid')}. Work was lost or repeated. ...
A repeat is recovery redoing an external call whose effect already exists: make the call
idempotent, or record the attempt before it
```

The worker died right after the email (external call 2) and before recording
it. Recovery saw `receipt_sent = 0` and sent it again: **two receipts**. This is
the sweep doing exactly what it was written to do.

Both findings are kept as tests in
[`tests/test_naive_checkout.py`](../../examples/checkout_tutorial/tests/test_naive_checkout.py),
which pass only while the harness still detects them:

```python
def test_a_death_after_the_charge_leaves_a_charge_and_no_order():
    with pytest.raises(HistoriesDiverged, match=r"'worker died after external call 1': \(None, 1, 0, None\)"):
        assert_crash_at_every_commit_converges(delivery(NaiveCheckout), place_order_history(NaiveCheckout))
```

## 5. Fix it, and watch the tests grow

[`checkout/reliable.py`](../../examples/checkout_tutorial/checkout/reliable.py)
makes three changes, one per gap:

```python
    def place_order(self, cart: str, amount: int) -> None:
        """The web request: record the intent, then finish it the same way recovery would."""
        with self.db:
            self.db.execute("INSERT INTO orders(cart, amount, status) VALUES (?, ?, 'pending')", (cart, amount))
        self._finish_payment(cart, amount)
        self._relay()

    def _finish_payment(self, cart: str, amount: int) -> None:
        charge = self.payments.charge(amount, key=f"charge:{cart}")
        with self.db:
            self.db.execute("UPDATE orders SET status = 'paid', charge = ? WHERE cart = ?", (charge, cart))
            self.db.execute("INSERT INTO outbox(topic, cart) VALUES ('order_placed', ?)", (cart,))
```

1. **The order is saved as `pending` before the charge.** A charge can no longer
   exist without an order that recovery can find; recovery finishes `pending`
   orders.
2. **Every outside call carries an idempotency key.** Recovery can repeat the
   charge (`charge:cart-1`) or the email (`receipt:cart-1`), and the provider
   acts once.
3. **Marking the order paid and recording the event commit together**, in an
   `outbox` table. A separate relay publishes outbox rows and marks them
   published, so a lost event is republished from the database. This pattern is
   called a *transactional outbox*.

The tests do not change. Run the same two descriptions against
`ReliableCheckout` and both pass. And look at what the harness ran for
`place order` this time:

| History | Final snapshot |
| --- | --- |
| normal operation | `('paid', 1, 1, 'paid')` |
| notifications lost | `('paid', 1, 1, 'paid')` |
| worker died after commit 1 | `('paid', 1, 1, 'paid')` |
| worker died after commit 2 | `('paid', 1, 1, 'paid')` |
| worker died after commit 3 | `('paid', 1, 1, 'paid')` |
| worker died after external call 1 | `('paid', 1, 1, 'paid')` |
| worker died after external call 2 | `('paid', 1, 1, 'paid')` |

**Seven histories instead of five, and you changed no test.** The fix added two
commits (the pending order, and the relay marking an event published), the
harness counted them, and it killed the worker after each. A hand-written suite
would have kept testing the old list.

### What it would take by hand

For each handoff, the harness runs: normal operation (twice, to check the
observation is stable), one history with messages lost, one per commit, one per
external call, and one per occurrence of each extra fault your host supports
(a failing after-commit callback, a broker refusing a publish, a lost reply to a
commit). That grows with your code, one history per boundary, and every history
checks all the systems you observe.

Real numbers from the repository: the [Saleor checkout demo](../../demos/README.md)
pins 27 interrupted histories of one checkout, across 22 commits, two
after-commit callbacks and three broker publications, in a single generated
test case. And when the question is about *ordering* rather than crashes
(receipts arriving out of order, a late write overtaking a newer one), the
generated orderings grow factorially: four independent pieces of evidence
already give between 504 and 761 distinct histories, depending on what the
provider allows. See [interleavings](interleavings.md).

## 6. Make it a generated suite

A contract declares everything there is to test about one piece of work, once.
pytest then generates the test cases. Here is
[`tests/test_reliable_checkout.py`](../../examples/checkout_tutorial/tests/test_reliable_checkout.py):

```python
CHECKOUT = ObligationContract(
    name="reliable checkout",
    profiles={
        Profile.A: Decline("recover() is the sweep; this example ships no scheduler to prove it runs"),
        Profile.B: NotApplicable("one worker; no lease changes hands"),
        Profile.C: NotApplicable("every provider call carries an idempotency key, so a repeat is safe"),
        Profile.D: NotApplicable("nothing prunes orders or outbox rows"),
        Profile.E: NotApplicable("one order per cart; no two results race to write the same row"),
        Profile.F: NotApplicable("orders and outbox rows record every obligation explicitly"),
        Profile.G: NotApplicable("no order waits on another decision before it may run"),
        Profile.H: Claim(),
        Profile.I: NotAssessed(because="bind AdmissionAtomicity for place_order"),
        Profile.J: NotAssessed(because="bind PersistentRetry: recovery retries a failing provider forever"),
    },
    handoffs=(place_order_history(ReliableCheckout), send_receipt_history(ReliableCheckout)),
    handoff_delivery=delivery(ReliableCheckout),
    replay=receipt_replay,
)


@due_work_contract_suite(CHECKOUT)
class TestReliableCheckout:
    pass
```

| Name | Comes from | What it does |
| --- | --- | --- |
| `ObligationContract` | pytest-obligation | The declaration: handoffs, their delivery, and a disposition for each of the ten [profiles](vocabulary.md#profiles-a-to-j). |
| `profiles` | Field | One answer per profile. The ten profiles are standard questions, for example A "does a scheduled sweep find work after a lost message?" or H "does repeating one operation leave one visible effect?". Every profile needs an answer; silence is refused. |
| `Claim()` | pytest-obligation | "This applies; prove it." A claim needs a binding, here `replay`. |
| `Decline(...)` / `NotApplicable(...)` | pytest-obligation | Deliberately absent, or cannot arise here, with the reason. The reason is printed in every report. |
| `NotAssessed(because=...)` | pytest-obligation | Nobody has bound this yet. It becomes a [strict expected failure](vocabulary.md#strict-expected-failure): visible debt, never a pass. |
| `handoffs`, `handoff_delivery` | Fields | The two histories from steps 2–4, and how their events travel. Each handoff becomes one generated case. |
| `@due_work_contract_suite(...)` | pytest-obligation | Turns the empty class into a suite: pytest collects one case per proof the contract implies. |

The claimed profile H needs one binding, `receipt_replay`. It runs the consumer
twice on the same event, as Kafka does when it redelivers, and checks that the
second run reached the cache again but changed nothing the customer sees:

```python
def receipt_replay() -> ReplaySafeEffect:
    # ARRANGE: a paid order whose event was never consumed.
    # REAL PRODUCTION: the consumer, ReliableCheckout.on_order_placed, run twice as a redelivered event would.
    # EXTERNAL SEAM: the fake cache and mailer record every write and delivery.
    # OBSERVE: cached status and receipts delivered.
    return ReplaySafeEffect(
        name="order_placed redelivered",
        expected=("paid", 1),
        prepare=a_shop_with_an_undelivered_event,
        execute=lambda shop: ReliableCheckout.on_order_placed(shop.app, CART),
        observe=lambda shop: (shop.cache.values.get(f"order:{CART}"), shop.mailer.delivered.count(CART)),
        execution_count_for=lambda shop: len(shop.cache.writes),
    )
```

`execution_count_for` counts how often the run reached an outside system. The
harness requires it to go 0, then 1, then 2: a replay whose second run did
nothing at all would prove nothing, so it is refused.

Run it with a report:

```bash
uv run --project ../.. --no-sync pytest tests/test_reliable_checkout.py --due-work-summary
```

```text
tests/test_reliable_checkout.py::TestReliableCheckout: 12 passed, 2 xfailed
  PASSED  A-declined
  ...
  PASSED  REPLAY_SAFE_EXECUTION-assert_replay_transition_is_production_bound
  PASSED  REPLAY_SAFE_EXECUTION-assert_first_execution_has_visible_effect
  PASSED  REPLAY_SAFE_EXECUTION-assert_replay_converges
  XFAIL   I-not_assessed  (Not assessed: bind AdmissionAtomicity for place_order ...)
  XFAIL   BOUNDED_RETRY-not_assessed  (Not assessed: bind PersistentRetry: recovery retries a failing provider ...)
  PASSED  handoff-place order-assert_crash_at_every_commit_converges
  PASSED  handoff-send receipt-assert_crash_at_every_commit_converges
```

The report's second half lists each profile with its disposition and reason.
The suite reads `UNVERIFIED` overall: a suite is verified only when every
profile is either proven or not applicable, and this one declines A and has two
profiles nobody has looked at yet. That is the honest summary, and it is the
same summary on every run until someone binds them. In CI,
`--due-work-require-assessed` turns unassessed profiles into a failure, and
`--due-work-profile-report=profiles.json` records exactly what ran.

### Recording a finding you cannot fix today

In an existing application, the harness often finds something you cannot fix
in the same change. Record it instead of hiding it:

```python
NAIVE_CHECKOUT = ObligationContract(
    name="naive checkout",
    adoption=Adoption.LEGACY,  # an existing app: findings may be recorded instead of fixed
    profiles={profile: NotApplicable("only the crash histories are bound so far") for profile in Profile},
    handoffs=(place_order_history(NaiveCheckout), send_receipt_history(NaiveCheckout)),
    handoff_delivery=delivery(NaiveCheckout),
    handoff_gaps={
        "place order": "the card is charged before the order exists (ticket SHOP-12)",
        "send receipt": "the receipt is sent before it is recorded (ticket SHOP-13)",
    },
)
```

Each `handoff_gaps` entry becomes a strict expected failure. It passes only
while that history still diverges, and **fails the day someone fixes the
code**, so the entry must be deleted in the fixing change. New features use the
default `Adoption.NEW_FEATURE`, which refuses gaps entirely.

## 7. Why you can trust a green result

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
  is not killed after its own calls; test it with its own history, as step 4
  did, or with a replay binding, as step 6 did.

[What a green result means](what-a-green-result-means.md) covers the rest.

## 8. Your real systems

The example's stand-ins map to your stack like this:

| In the example | In your application | How pytest-obligation takes part |
| --- | --- | --- |
| SQLite + `sqlite_worker_killer` | PostgreSQL through Django | `django_host()` counts commits and kills the worker after each; add `celery_publication_breaker` to refuse each Celery publish, and `django_receiver_breaker` to fail each signal receiver. [Integrations](integrations.md) |
| SQLite + `sqlite_worker_killer` | MongoDB | `mongodb_host(client, ...)` counts acknowledged writes and transaction commits, and loses replies after a write lands. [MongoDB](mongodb.md) |
| SQLite + `sqlite_worker_killer` | Redis as the store of record | `redis_host(client, ...)` counts writes and pipelines, and loses write replies. |
| `FakeCache` | Redis as a cache | An `ExternalCall` on your cache client's write method. |
| `FakeBroker` | Kafka | An `ExternalCall` on the producer's `send_and_wait` (the coroutine that does the work). For consumers, the `[aiokafka]` extra injects deaths and lost replies at offset commits. [aiokafka](aiokafka.md) |
| `FakeBroker` + `recover` | Celery or RQ | The real worker as the delivery; the `[celery]` and `[rq]` extras run real workers, refuse publications and fail callbacks. |
| `recover()` | A Prefect flow | `prefect_flow_call` runs the real flow body as the step or the recovery; `prefect_host` composes with your database's host. [Prefect](prefect.md) |
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
