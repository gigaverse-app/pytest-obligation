"""The provider ledger is independent of the application's billing decisions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pytest_obligation.integrations.shopify import BillingEvent, BillingWindow, ShopifyBillingSimulator

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW = BillingWindow(start=NOW, end=NOW + timedelta(days=30))


def event(key="one", *, shop_id="shop-a", event_handle="usage", timestamp=NOW, quantity="10"):
    return BillingEvent(
        shop_id=shop_id, event_handle=event_handle, timestamp=timestamp, idempotency_key=key, quantity=quantity
    )


def total(provider, shop="shop-a", meter="usage", window=WINDOW):
    return provider.total(shop_id=shop, event_handle=meter, window=window)


def test_acceptance_does_not_apply_or_make_usage_visible():
    provider = ShopifyBillingSimulator()
    receipt = provider.accept(event())
    assert receipt.status_code == 202
    assert receipt.outcome == "accepted"
    assert total(provider) == 0
    assert provider.records[0].state == "accepted"
    provider.apply("one", visible=False)
    assert provider.records[0].state == "applied"
    assert total(provider) == 0
    provider.make_visible("one")
    assert total(provider) == 10


@pytest.mark.parametrize("rejection", [None, "NO_SUBSCRIPTION", "PERIOD_CLOSED"])
def test_replay_never_reapplies_or_repairs_a_burned_key(rejection):
    provider = ShopifyBillingSimulator()
    first = provider.send(event(), rejection=rejection)
    replay = provider.send(event())
    assert (first.status_code, replay.status_code) == (202, 202)
    assert replay.outcome == "replayed"
    assert len(provider.attempts) == 2
    assert len(provider.records) == 1
    assert total(provider) == (10 if rejection is None else 0)
    assert provider.records[0].rejection == rejection
    if rejection is not None:
        with pytest.raises(ValueError, match="rejected"):
            provider.apply("one")
        with pytest.raises(ValueError, match="applied"):
            provider.make_visible("one")


def test_duplicate_acceptance_does_not_complete_an_unresolved_event():
    provider = ShopifyBillingSimulator()
    provider.accept(event())
    assert provider.send(event()).outcome == "replayed"
    assert provider.records[0].state == "accepted"
    assert total(provider) == 0


def test_identity_conflict_is_a_simulator_error_and_keeps_original_evidence():
    provider = ShopifyBillingSimulator()
    provider.send(event())
    with pytest.raises(ValueError, match="different input"):
        provider.send(event(quantity="11"))
    assert total(provider) == 10
    assert len(provider.records) == 1


def test_meter_is_scoped_and_half_open_with_signed_exact_quantities():
    provider = ShopifyBillingSimulator()
    for value in (
        event(quantity="0.1"),
        event("refund", quantity="-0.3"),
        event("another-shop", shop_id="shop-b", quantity="90"),
        event("another-meter", event_handle="other", quantity="80"),
        event("before", timestamp=NOW - timedelta(microseconds=1), quantity="70"),
        event("end", timestamp=WINDOW.end, quantity="60"),
    ):
        provider.send(value)
    assert total(provider) == Decimal("-0.2")
    assert total(provider, "shop-b") == 90
    assert total(provider, meter="other") == 80


def test_provider_records_cannot_be_rewritten_through_observations():
    provider = ShopifyBillingSimulator()
    provider.send(event())
    with pytest.raises(ValidationError):
        provider.records[0].event.quantity = Decimal(99)  # pyrefly: ignore [read-only] -- runtime mutation control
    assert total(provider) == 10
    provider.reset()
    assert provider.attempts == provider.records == ()
    assert total(provider) == 0


@pytest.mark.parametrize("quantity", ["0", "NaN", "Infinity", "-Infinity", "bad"])
def test_invalid_quantities_are_rejected_as_outside_the_simulated_contract(quantity):
    with pytest.raises(ValidationError):
        event(quantity=quantity)


def test_naive_timestamps_and_invalid_windows_fail_at_construction():
    with pytest.raises(ValidationError):
        event(timestamp=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        BillingWindow(start=NOW, end=NOW)


def test_settled_provider_decisions_cannot_be_rewritten():
    provider = ShopifyBillingSimulator()
    provider.send(event())
    provider.apply("one")  # Idempotent control-plane command, never a second effect.
    with pytest.raises(ValueError, match="applied"):
        provider.reject("one", "NO_SUBSCRIPTION")
    with pytest.raises(KeyError):
        provider.apply("unknown")
