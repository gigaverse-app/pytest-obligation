"""External-expiry reference used by the library's production-binding controls."""


class Cache:
    def __init__(self, ttl: float = 60, *, expires: bool = True, loses_update: bool = True) -> None:
        self.ttl = ttl
        self.expires = expires
        self.loses_update = loses_update
        self.now = 0.0
        self.deadline: float | None = None
        self.stale = False
        self.lost = 0

    def publish(self) -> None:
        self.deadline = self.now + self.ttl
        self.stale = False

    def invalidate(self) -> None:
        self.stale = True
        if self.loses_update:
            self.lost += 1
        else:
            self.deadline = None

    def present(self) -> bool:
        return self.deadline is not None and (not self.expires or self.now < self.deadline)

    def advance(self, seconds: float) -> None:
        self.now += seconds
