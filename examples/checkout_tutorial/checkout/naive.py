"""The checkout most applications start with: correct whenever nothing fails.

It charges the card, saves the order, and publishes an event; a consumer then
updates the order cache and emails the receipt. Every line is reasonable. The
tutorial's first chapter shows what happens to it when a worker dies or a message
is lost between those lines.
"""

import sqlite3

from checkout.ports import Broker, Cache, Mailer, Payments

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, cart TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL,
    status TEXT NOT NULL, charge TEXT, receipt_sent INTEGER NOT NULL DEFAULT 0
);
"""


class NaiveCheckout:
    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        payments: Payments,
        broker: Broker,
        cache: Cache,
        mailer: Mailer,
    ) -> None:
        self.db, self.payments, self.broker, self.cache, self.mailer = db, payments, broker, cache, mailer
        self.db.executescript(SCHEMA)

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
