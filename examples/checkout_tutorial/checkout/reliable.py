"""The same checkout after the fixes the tutorial's generated tests ask for.

Three changes, each closing a gap a crash history found:

1. The order is saved as `pending` *before* the card is charged, so a charge can
   never exist without an order that recovery can find.
2. Every external call carries an idempotency key, so recovery can safely repeat it.
3. Marking the order paid and recording the event to publish commit together
   (a transactional outbox), so a lost message is republished from the database.
"""

import sqlite3

from checkout.ports import Broker, Cache, Mailer, Payments

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, cart TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL,
    status TEXT NOT NULL, charge TEXT, receipt_sent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY, topic TEXT NOT NULL, cart TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0
);
"""


class ReliableCheckout:
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

    def _relay(self) -> None:
        """Publish recorded events; a crash before marking one published only republishes it."""
        for event_id, topic, cart in self.db.execute(
            "SELECT id, topic, cart FROM outbox WHERE published = 0 ORDER BY id"
        ).fetchall():
            self.broker.publish(topic, cart)
            with self.db:
                self.db.execute("UPDATE outbox SET published = 1 WHERE id = ?", (event_id,))

    def on_order_placed(self, cart: str) -> None:
        """The queue consumer. It may receive the same event twice, so every step is safe to repeat."""
        status, receipt_sent = self.db.execute(
            "SELECT status, receipt_sent FROM orders WHERE cart = ?", (cart,)
        ).fetchone()
        self.cache.set(f"order:{cart}", status)
        if not receipt_sent:
            self.mailer.send(cart, key=f"receipt:{cart}")
            with self.db:
                self.db.execute("UPDATE orders SET receipt_sent = 1 WHERE cart = ?", (cart,))

    def recover(self) -> None:
        """The scheduled sweep: finish every step the database says is still owed."""
        for cart, amount in self.db.execute("SELECT cart, amount FROM orders WHERE status = 'pending'").fetchall():
            self._finish_payment(cart, amount)
        self._relay()
        for (cart,) in self.db.execute("SELECT cart FROM orders WHERE status = 'paid' AND receipt_sent = 0").fetchall():
            self.on_order_placed(cart)
