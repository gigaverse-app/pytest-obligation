"""Durable usage marks with explicit reconciliation, independent of provider test controls.

This example owns one isolated shop/meter/cycle's complete event population.
That assumption is necessary: an aggregate cannot identify arbitrary missing
events. Production adapters must establish their own evidence policy.
"""

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal

from pytest_obligation.integrations.shopify import BillingEvent, BillingReceipt


class BillingApplication:
    def __init__(
        self,
        db: sqlite3.Connection,
        send: Callable[[BillingEvent], BillingReceipt],
        meter: Callable[[], Decimal],
        rejections: Callable[[], Mapping[str, str]],
    ) -> None:
        self.db, self.send, self.meter, self.rejections = db, send, meter, rejections
        self.db.execute("CREATE TABLE IF NOT EXISTS usage (key TEXT PRIMARY KEY, quantity TEXT, state TEXT)")

    def submit(self, events: Sequence[BillingEvent]) -> None:
        for event in events:
            with self.db:
                self.db.execute(
                    "INSERT OR IGNORE INTO usage VALUES (?, ?, 'pending')",
                    (event.idempotency_key, str(event.quantity)),
                )
            self.send(event)
            # A receipt establishes only acceptance. Replays cannot overwrite
            # a verdict already established by independent evidence.
            with self.db:
                self.db.execute(
                    "UPDATE usage SET state='sent' WHERE key=? AND state='pending'", (event.idempotency_key,)
                )

    def reconcile(self) -> None:
        with self.db:
            for key in self.rejections():
                self.db.execute("UPDATE usage SET state='rejected' WHERE key=? AND state='sent'", (key,))
            rows = self.db.execute("SELECT quantity FROM usage WHERE state IN ('sent', 'confirmed')").fetchall()
            expected = sum((Decimal(row[0]) for row in rows), Decimal(0))
            if rows and expected == self.meter():
                self.db.execute("UPDATE usage SET state='confirmed' WHERE state='sent'")

    def states(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.db.execute("SELECT state FROM usage ORDER BY key"))
