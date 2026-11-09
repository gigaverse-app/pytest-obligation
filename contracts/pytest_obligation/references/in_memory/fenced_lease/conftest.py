"""The fenced-lease driver: applies each step of model.qnt to the real InMemoryOwner.

The generated base (fenced_lease_driver.py) has one method per model action, typed from the
model, so a renamed action or parameter breaks this class loudly instead of silently. This
file is the trusted part of the contract: it decides which real call each action makes and how
the row is read back. The planted bugs below are what check that it is not too lenient.
"""

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fenced_lease_driver import FencedLeaseDriver, View
from pytest_quint_connect import HistoryContext

from pytest_obligation.references.in_memory import REFERENCE_LEASE_SECONDS, InMemoryOwner

HISTORY = Path(__file__).with_name("history")
SHIPPED_9AA6FF2_SHA256 = "5011bfb636a17d7a12e7983faaf3b9511c6d45f85353dbc82d73b709a8724c22"


def _shipped_9aa6ff2() -> type[InMemoryOwner]:
    """InMemoryOwner with the three re-arm methods exactly as shipped at 9aa6ff2, before #217."""
    shipped = HISTORY / "rearm-9aa6ff2.py.txt"
    text = shipped.read_bytes()
    assert hashlib.sha256(text).hexdigest() == SHIPPED_9AA6FF2_SHA256, f"{shipped} was edited"
    namespace: dict[str, Any] = {"UUID": UUID}
    exec(compile(text, str(shipped), "exec"), namespace)
    methods = {name: namespace[name] for name in ("fenced_retry", "reclaim_stalled", "release_unchanged")}
    return type("ShippedOwner", (InMemoryOwner,), methods)


class _ReaperIgnoresLease(InMemoryOwner):
    """The reaper re-arms any claimed row, taking it from an owner whose lease is still live."""

    def reclaim_stalled(self, row_id: int) -> str | None:
        row = self.rows[row_id]
        if row.state != "CLAIMED":
            return None
        self._rearm(row)
        return "REARMED"


class _UnfencedRenewal(InMemoryOwner):
    """renew_lease ignores the token, so a dead owner can keep a lease alive."""

    def renew_lease(self, row_id: int, token: UUID) -> bool:
        self.rows[row_id].lease_expires_at = self.clock + REFERENCE_LEASE_SECONDS
        return True


PLANTED_BUGS: dict[str, Any] = {
    "shipped-9aa6ff2": _shipped_9aa6ff2,
    "reaper-ignores-lease": lambda: _ReaperIgnoresLease,
    "unfenced-renewal": lambda: _UnfencedRenewal,
}


class OwnerDriver(FencedLeaseDriver):
    """One InMemoryOwner with one row. Tokens are kept in issue order so "last" and "previous" resolve."""

    def __init__(self, owner_type: type[InMemoryOwner]) -> None:
        self.owner_type = owner_type
        self.accepted = False

    def _token(self, age: str) -> UUID:
        # A token that was never issued stands in when there is no such token; nothing accepts it.
        index = -1 if age == "last" else -2
        return self.tokens[index] if len(self.tokens) >= -index else uuid4()

    def init(self) -> None:
        self.owner = self.owner_type()
        self.row = self.owner.make_claimable()
        self.tokens: list[UUID] = []
        self.accepted = False

    def claim(self) -> None:
        claimed = self.owner.claim()
        if claimed is not None:
            self.tokens.append(claimed[1])
        self.accepted = claimed is not None

    def expire(self) -> None:
        self.owner.expire_lease(self.row)
        self.accepted = False

    def reclaim(self) -> None:
        self.accepted = self.owner.reclaim_stalled(self.row) is not None

    def write(self, token: str) -> None:
        self.accepted = self.owner.fenced_write(self.row, self._token(token)) is True

    def retry(self, token: str) -> None:
        self.accepted = self.owner.fenced_retry(self.row, self._token(token)) is True

    def release(self, token: str) -> None:
        self.accepted = self.owner.release_unchanged(self.row, self._token(token)) is True

    def renew(self, token: str) -> None:
        self.accepted = self.owner.renew_lease(self.row, self._token(token)) is True

    def inspect(self) -> None:
        pass

    def observe(self) -> View:
        state, deadline = self.owner.observe(self.row)
        if deadline is None:
            lease = "none"
        elif deadline < self.owner.clock:
            lease = "expired"
        else:
            lease = "live"
        return {"state": state, "lease": lease, "accepted": self.accepted}


@pytest.fixture
def fenced_lease_driver():
    def start(context: HistoryContext) -> OwnerDriver:
        owner_type = InMemoryOwner if context.mutant is None else PLANTED_BUGS[context.mutant]()
        return OwnerDriver(owner_type)

    return start
