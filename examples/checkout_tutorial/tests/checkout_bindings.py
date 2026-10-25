"""Connect the checkout to pytest-obligation: arrange a fresh shop, run real code, observe every system."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from checkout.naive import NaiveCheckout
from checkout.reliable import ReliableCheckout
from providers import FakeBroker, FakeCache, FakeMailer, FakePayments
from sqlite_host import CountedConnection

from pytest_obligation import CallableDelivery, ExternalCall, HandoffHistory

CART = "cart-1"


@dataclass
class Shop:
    app: NaiveCheckout | ReliableCheckout
    payments: FakePayments
    broker: FakeBroker
    cache: FakeCache
    mailer: FakeMailer


# The shop the current history is running; the delivery below reaches it through here.
current: list[Shop] = []


def new_shop(checkout: type[NaiveCheckout | ReliableCheckout]) -> Shop:
    """A checkout on an empty in-memory database, wired to fresh fake providers."""
    payments, broker, cache, mailer = FakePayments(), FakeBroker(), FakeCache(), FakeMailer()
    db = sqlite3.connect(":memory:", factory=CountedConnection)
    app = checkout(db, payments=payments, broker=broker, cache=cache, mailer=mailer)
    broker.consumer = app.on_order_placed
    return Shop(app, payments, broker, cache, mailer)


@contextmanager
def fresh_shop(checkout: type[NaiveCheckout | ReliableCheckout]) -> Iterator[Shop]:
    """A new shop for one history, reachable by the delivery while the history runs."""
    shop = new_shop(checkout)
    current.append(shop)
    try:
        yield shop
    finally:
        current.remove(shop)
        shop.app.db.close()


def everything_the_customer_sees(shop: Shop) -> tuple[str | None, int, int, str | None]:
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


def delivery(checkout: type[NaiveCheckout | ReliableCheckout]) -> CallableDelivery:
    """How published events reach the consumer, how they get lost, and how production recovers."""
    return CallableDelivery(
        name=f"{checkout.__name__} queue",
        deliver=lambda: current[-1].broker.deliver_all(),  # what a running consumer does
        lose=lambda: current[-1].broker.lose_all(),  # what a broker outage does
        # REAL PRODUCTION: the sweep the application schedules, run after every history.
        recover=lambda: checkout.recover(current[-1].app),
    )


def place_order_history(checkout: type[NaiveCheckout | ReliableCheckout]) -> HandoffHistory:
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


@contextmanager
def shop_with_an_undelivered_event(checkout: type[NaiveCheckout | ReliableCheckout]) -> Iterator[Shop]:
    with fresh_shop(checkout) as shop:
        shop.app.place_order(CART, 30)
        shop.broker.lose_all()
        yield shop


def send_receipt_history(checkout: type[NaiveCheckout | ReliableCheckout]) -> HandoffHistory:
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
