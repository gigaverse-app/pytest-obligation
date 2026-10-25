# 3. Fix it, and watch the tests grow

[Previous: 2. Find what breaks](many-systems-2-findings.md) · [All chapters](tutorial-many-systems.md#chapters) · [Vocabulary](vocabulary.md)

Chapter 2 found two problems in the naive checkout. This chapter fixes them,
and shows what happens to the tests when the code changes.

## Three changes

[`checkout/reliable.py`](../../examples/checkout_tutorial/checkout/reliable.py)
makes three changes, one per gap:

<!-- fmt:off -->
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
<!-- fmt:on -->

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

## The tests grow on their own

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

## What it would take by hand

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


[Next: 4. Make it a generated suite](many-systems-4-suite.md)
