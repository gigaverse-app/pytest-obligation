"""The test most teams write first. Both checkouts pass it."""

import pytest
from checkout.naive import NaiveCheckout
from checkout.reliable import ReliableCheckout
from checkout_bindings import CART, everything_the_customer_sees, fresh_shop


@pytest.mark.parametrize("checkout", [NaiveCheckout, ReliableCheckout])
def test_an_order_is_charged_cached_and_receipted(checkout) -> None:  # noqa: ANN001 - either checkout class
    with fresh_shop(checkout) as shop:
        shop.app.place_order(CART, 30)
        shop.broker.deliver_all()

        assert everything_the_customer_sees(shop) == ("paid", 1, 1, "paid")
