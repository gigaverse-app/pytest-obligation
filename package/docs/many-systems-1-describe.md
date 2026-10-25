# 1. Describe the workflow once

[Overview](tutorial-many-systems.md) · [All chapters](tutorial-many-systems.md#chapters) · [Vocabulary](vocabulary.md)

In this chapter you write the test most teams write first, then describe the
same workflow to pytest-obligation. Nothing runs against the harness yet; that
is [chapter 2](many-systems-2-findings.md). The checkout's code is on the
[overview page](tutorial-many-systems.md#the-workflow).

## The test you would normally write

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
[chapter 3](many-systems-3-fix.md). **The happy path cannot tell them apart**, because the difference
between them only shows when something fails between two lines.

How many such points are there? In `place_order` alone: after the charge, after
the commit, after the publish, and the case where the published event is lost.
Four tests, each with its own setup, fault and five-system assertion. The
consumer adds four more. Change one line of either function and the list
changes. Nobody keeps that list up to date by hand.

## Describe the same workflow to pytest-obligation

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
check that your bindings call that code rather than re-implement it ([chapter 5](many-systems-5-real-systems.md)).

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


[Next: 2. Find what breaks](many-systems-2-findings.md)
