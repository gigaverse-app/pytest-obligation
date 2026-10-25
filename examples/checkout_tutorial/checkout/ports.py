"""The external systems a checkout talks to, as the application sees them.

Production passes real clients (a payment API, a broker, Redis, an email service);
the tutorial's tests pass small fakes with the same methods.
"""

from typing import Protocol


class Payments(Protocol):
    def charge(self, amount: int, *, key: str | None) -> str:
        """Charge the card and return the charge id. A provider that honours `key` charges once per key."""
        ...


class Broker(Protocol):
    def publish(self, topic: str, cart: str) -> None: ...


class Cache(Protocol):
    def set(self, key: str, value: str) -> None: ...


class Mailer(Protocol):
    def send(self, cart: str, *, key: str | None) -> None:
        """Email the receipt. A provider that honours `key` delivers once per key."""
        ...
