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

pytest-obligation has no stack of its own. Its core works with plain Python
callables, so the same approach applies whether your work moves through a
message broker, a job table, a workflow engine or a chain of database
transactions. Integrations for tools such as Django, Celery, RQ, procrastinate,
django-tasks-db, DBOS, Prefect, Kafka, MongoDB and Redis save you some wiring;
none of them is required.

## Chapters

Each chapter is one short page and ends with a link to the next.

| Chapter | You will |
| --- | --- |
| [1. Describe the workflow once](many-systems-1-describe.md) | Write the happy-path test most teams write, then describe the same workflow to pytest-obligation |
| [2. Find what breaks](many-systems-2-findings.md) | Watch it find a charge with no order, and a receipt sent twice |
| [3. Fix it, and watch the tests grow](many-systems-3-fix.md) | Fix both, and see the generated histories grow with no test changes |
| [4. Make it a generated suite](many-systems-4-suite.md) | Turn the description into a test suite with a report, and record a finding you cannot fix today |
| [5. Trust the result, and use your real systems](many-systems-5-real-systems.md) | See why a green result is honest, and map the stand-ins to your databases, brokers, queues and workflow engines |

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

[Start: 1. Describe the workflow once](many-systems-1-describe.md)
