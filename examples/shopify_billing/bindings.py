"""One evidence binding; the harness owns permutations, duplication and batching."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from functools import partial

from pytest_obligation.host import Host, hosted
from pytest_obligation.integrations.shopify import BillingEvent, BillingWindow, ShopifyBillingSimulator
from pytest_obligation.interleavings import EvidenceArrival, EvidenceConfluence, EvidenceExpectation, EvidenceSession

from .application import BillingApplication

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW = BillingWindow(start=NOW, end=NOW + timedelta(days=30))
EVENTS = tuple(
    BillingEvent(shop_id="shop-a", event_handle="usage", timestamp=NOW, idempotency_key=key, quantity=quantity)
    for key, quantity in (("a", "10"), ("b", "20"))
)


@contextmanager
def billing_evidence() -> Iterator[EvidenceSession[tuple[str, ...]]]:
    # ARRANGE: two durable marks, one provider application and one rejection.
    # REAL PRODUCTION: BillingApplication.submit and reconcile own SQL decisions.
    # EXTERNAL SEAM: receipt, aggregate meter and separately delivered rejection evidence.
    # OBSERVE: committed usage states and the provider's complete accepted-key ledger.
    with (
        closing(sqlite3.connect(":memory:")) as db,
        hosted(Host(production_packages=frozenset({"shopify_billing"}))),
    ):
        provider = ShopifyBillingSimulator()
        dashboard: dict[str, str] = {}

        def send(event: BillingEvent):
            return provider.send(
                event, rejection="NO_SUBSCRIPTION" if event.idempotency_key == "b" else None, visible=False
            )

        app = BillingApplication(
            db, send, partial(provider.total, shop_id="shop-a", event_handle="usage", window=WINDOW), lambda: dashboard
        )

        def dashboard_arrives() -> None:
            dashboard["b"] = "NO_SUBSCRIPTION"

        # Review the oracle before execution. The run under test never supplies expected state.
        outcomes = {
            frozenset(): ("sent", "sent"),
            frozenset({"meter"}): ("sent", "sent"),
            frozenset({"dashboard"}): ("sent", "rejected"),
            frozenset({"meter", "dashboard"}): ("confirmed", "rejected"),
        }
        yield EvidenceSession(
            prepare=partial(app.submit, EVENTS),
            facts={
                "meter": EvidenceArrival(publish=partial(provider.make_visible, "a"), consume=app.reconcile),
                "dashboard": EvidenceArrival(publish=dashboard_arrives, consume=app.reconcile),
            },
            observe=app.states,
            expectations={
                facts: EvidenceExpectation(observation=state, effects={"a": 1, "b": 1})
                for facts, state in outcomes.items()
            },
            recover=app.reconcile,
            advance=lambda seconds: None,
            effects=lambda: {record.event.idempotency_key: 1 for record in provider.records},
            actor_scope=nullcontext,
        )


EVIDENCE = EvidenceConfluence(
    name="shopify-meter-and-rejection",
    bind=billing_evidence,
    facts=("meter", "dashboard"),
    batchable=True,
    no_ordered_pair_because="This focused example has one SQLite connection and serial evidence consumers.",
    no_retry_because="Evidence consumption does not resend billing; provider replay is separately controlled.",
)
