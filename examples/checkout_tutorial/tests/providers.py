"""In-process stand-ins for the payment provider, broker, cache and mailer.

Each fake models only what the provider does with a request, and records every
effect so a test can count it. None of them contains checkout logic.
"""

from collections.abc import Callable


class FakePayments:
    """A card processor: every call is a new charge, unless it repeats a key the processor has seen."""

    def __init__(self) -> None:
        self.charges: list[str] = []
        self._by_key: dict[str, str] = {}

    def charge(self, amount: int, *, key: str | None) -> str:
        if key is not None and key in self._by_key:
            return self._by_key[key]
        charge_id = f"ch_{len(self.charges) + 1}"
        self.charges.append(charge_id)
        if key is not None:
            self._by_key[key] = charge_id
        return charge_id


class FakeBroker:
    """A message queue: published events wait until delivered to the consumer, or are lost."""

    def __init__(self) -> None:
        self.waiting: list[tuple[str, str]] = []
        self.consumer: Callable[[str], None] | None = None

    def publish(self, topic: str, cart: str) -> None:
        self.waiting.append((topic, cart))

    def deliver_all(self) -> None:
        assert self.consumer is not None
        while self.waiting:
            _topic, cart = self.waiting.pop(0)
            self.consumer(cart)

    def lose_all(self) -> None:
        self.waiting.clear()


class FakeCache:
    """A key-value cache such as Redis."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.writes: list[tuple[str, str]] = []

    def set(self, key: str, value: str) -> None:
        self.values[key] = value
        self.writes.append((key, value))


class FakeMailer:
    """An email service: every call delivers a message, unless it repeats a key the service has seen."""

    def __init__(self) -> None:
        self.delivered: list[str] = []
        self._keys: set[str] = set()

    def send(self, cart: str, *, key: str | None) -> None:
        if key is not None:
            if key in self._keys:
                return
            self._keys.add(key)
        self.delivered.append(cart)
