# 4. Make it a generated suite

[Previous: 3. Fix it, and watch the tests grow](many-systems-3-fix.md) · [All chapters](tutorial-many-systems.md#chapters) · [Vocabulary](vocabulary.md)

So far each test called the harness directly. A contract declares the same
descriptions once, and pytest generates the test cases from it, with a report.

## The contract

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

## Recording a finding you cannot fix today

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


[Next: 5. Trust the result, and use your real systems](many-systems-5-real-systems.md)
