"""The reliable checkout's contract: every generated case must pass."""

from checkout.reliable import ReliableCheckout
from checkout_bindings import CART, delivery, new_shop, place_order_history, send_receipt_history

from pytest_obligation import (
    Claim,
    Decline,
    NotApplicable,
    NotAssessed,
    ObligationContract,
    Profile,
    ReplaySafeEffect,
    due_work_contract_suite,
)


def a_shop_with_an_undelivered_event():
    shop = new_shop(ReliableCheckout)
    ReliableCheckout.place_order(shop.app, CART, 30)
    shop.broker.lose_all()
    return shop


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
