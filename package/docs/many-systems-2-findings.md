# 2. Find what breaks

[Previous: 1. Describe the workflow once](many-systems-1-describe.md) · [All chapters](tutorial-many-systems.md#chapters) · [Vocabulary](vocabulary.md)

Chapter 1 described the checkout's two steps: placing the order, and the queue
consumer that sends the receipt. Now run each description against the naive
checkout.

## Find the charge with no order

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

## Find the receipt sent twice

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


[Next: 3. Fix it, and watch the tests grow](many-systems-3-fix.md)
