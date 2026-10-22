"""Generated provider-evidence histories and controls against wrong application decisions."""

import sqlite3
from contextlib import closing

import pytest

from examples.shopify_billing.application import BillingApplication
from examples.shopify_billing.bindings import EVENTS, EVIDENCE, WINDOW
from pytest_obligation.integrations.shopify import ShopifyBillingSimulator
from pytest_obligation.interleavings import InterleavingFailure


@pytest.mark.parametrize("history", EVIDENCE.histories(), ids=lambda history: history.id)
def test_generated_evidence_histories(history):
    EVIDENCE.run(history)


@pytest.mark.parametrize("counterfeit", ["receipt_confirms", "meter_confirms_everything"])
def test_histories_reject_false_confirmation(monkeypatch, counterfeit):
    if counterfeit == "receipt_confirms":
        original = BillingApplication.submit

        def submit(app, events):
            original(app, events)
            with app.db:
                app.db.execute("UPDATE usage SET state='confirmed'")

        monkeypatch.setattr(BillingApplication, "submit", submit)
    else:
        original_reconcile = BillingApplication.reconcile

        def reconcile(app):
            original_reconcile(app)
            if app.meter():
                with app.db:
                    app.db.execute("UPDATE usage SET state='confirmed'")

        monkeypatch.setattr(BillingApplication, "reconcile", reconcile)
    with pytest.raises(InterleavingFailure, match="reviewed recipient/attempt outcome"):
        EVIDENCE.run(EVIDENCE.histories()[0])


def test_lost_reply_reuses_persisted_identity_after_application_restart(tmp_path):
    provider = ShopifyBillingSimulator()

    def lost_reply(event):
        provider.send(event)
        raise TimeoutError("provider applied; caller received no reply")

    path = tmp_path / "billing.sqlite"
    with closing(sqlite3.connect(path)) as db:
        first = BillingApplication(
            db, lost_reply, lambda: provider.total(shop_id="shop-a", event_handle="usage", window=WINDOW), dict
        )
        with pytest.raises(TimeoutError):
            first.submit(EVENTS[:1])
        assert first.states() == ("pending",)
    with closing(sqlite3.connect(path)) as db:
        restarted = BillingApplication(
            db, provider.send, lambda: provider.total(shop_id="shop-a", event_handle="usage", window=WINDOW), dict
        )
        restarted.submit(EVENTS[:1])
        assert restarted.states() == ("sent",)
        restarted.reconcile()
        assert restarted.states() == ("confirmed",)
    assert len(provider.attempts) == 2
    assert len(provider.records) == 1
