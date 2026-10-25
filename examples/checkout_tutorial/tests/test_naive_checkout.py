"""The naive checkout's two findings, kept as tests that pass only while the harness still detects them."""

import pytest
from checkout.naive import NaiveCheckout
from checkout_bindings import delivery, place_order_history, send_receipt_history

from pytest_obligation import HistoriesDiverged, assert_crash_at_every_commit_converges


def test_a_death_after_the_charge_leaves_a_charge_and_no_order():
    with pytest.raises(HistoriesDiverged, match=r"'worker died after external call 1': \(None, 1, 0, None\)"):
        assert_crash_at_every_commit_converges(delivery(NaiveCheckout), place_order_history(NaiveCheckout))


def test_a_death_after_the_email_sends_the_receipt_twice():
    with pytest.raises(HistoriesDiverged, match=r"'worker died after external call 2': \('paid', 1, 2, 'paid'\)"):
        assert_crash_at_every_commit_converges(delivery(NaiveCheckout), send_receipt_history(NaiveCheckout))
