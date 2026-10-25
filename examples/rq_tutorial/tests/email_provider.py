"""A stand-in for the welcome app's email provider."""


class FakeMailer:
    """An email service: every call delivers a message, unless it repeats a key the service has seen."""

    def __init__(self) -> None:
        self.delivered: list[str] = []
        self.failed_calls = 0
        self.down = False
        self._keys: set[str] = set()

    def send(self, to: str, *, key: str | None) -> None:
        if self.down:
            self.failed_calls += 1
            raise ConnectionError("the email provider is down")
        if key is not None:
            if key in self._keys:
                return
            self._keys.add(key)
        self.delivered.append(to)


# The one email provider the welcome app talks to in the tests.
MAILER = FakeMailer()
