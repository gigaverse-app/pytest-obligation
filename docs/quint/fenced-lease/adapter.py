"""pytest-quint-connect driver: apply Quint events to profile B's reference owner, InMemoryOwner."""

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pytest_obligation.references.in_memory import InMemoryOwner

SHIPPED_9AA6FF2_SHA256 = "5011bfb636a17d7a12e7983faaf3b9511c6d45f85353dbc82d73b709a8724c22"


def _owner_type(mutant: str | None) -> type[InMemoryOwner]:
    if mutant is None:
        return InMemoryOwner
    if mutant == "shipped-9aa6ff2":
        # The exact pre-fix re-arm methods, run on a subclass of today's owner. The hash keeps
        # this frozen evidence from being edited until it agrees with the model.
        shipped = Path(__file__).with_name("rearm-9aa6ff2.py.txt")
        text = shipped.read_bytes()
        assert hashlib.sha256(text).hexdigest() == SHIPPED_9AA6FF2_SHA256, f"{shipped} was edited"
        namespace: dict[str, Any] = {"UUID": UUID}
        exec(compile(text, str(shipped), "exec"), namespace)
        methods = {name: namespace[name] for name in ("fenced_retry", "reclaim_stalled", "release_unchanged")}
        return type("ShippedOwner", (InMemoryOwner,), methods)
    if mutant == "reaper-ignores-lease":

        def reclaim_stalled(self: InMemoryOwner, row_id: int) -> str | None:
            row = self.rows[row_id]
            if row.state != "CLAIMED":
                return None
            self._rearm(row)
            return "REARMED"

        return type("EagerReaper", (InMemoryOwner,), {"reclaim_stalled": reclaim_stalled})
    if mutant == "unfenced-renewal":

        def renew_lease(self: InMemoryOwner, row_id: int, token: UUID) -> bool:
            self.rows[row_id].lease_expires_at = self.clock + 60.0
            return True

        return type("UnfencedRenewal", (InMemoryOwner,), {"renew_lease": renew_lease})
    raise ValueError(f"unknown planted bug: {mutant}")


class Adapter:
    def __init__(self, owner_type: type[InMemoryOwner]) -> None:
        self.owner_type = owner_type
        self.accepted = False

    def token(self, age: str) -> UUID:
        # "last" is the most recently issued token, "previous" the one before it. A token
        # that was never issued stands in when there is none, and nothing accepts it.
        index = -1 if age == "last" else -2
        return self.tokens[index] if len(self.tokens) >= -index else uuid4()

    def step(self, step: Any) -> None:
        op = step.action
        if op == "init":
            self.owner = self.owner_type()
            self.row = self.owner.make_claimable()
            self.tokens: list[UUID] = []
            self.accepted = False
        elif op == "claim":
            claimed = self.owner.claim()
            if claimed is not None:
                self.tokens.append(claimed[1])
            self.accepted = claimed is not None
        elif op == "expire":
            self.owner.expire_lease(self.row)
            self.accepted = False
        elif op == "reclaim":
            self.accepted = self.owner.reclaim_stalled(self.row) is not None
        elif op in ("write", "retry", "release", "renew"):
            operation = {
                "write": self.owner.fenced_write,
                "retry": self.owner.fenced_retry,
                "release": self.owner.release_unchanged,
                "renew": self.owner.renew_lease,
            }[op]
            self.accepted = operation(self.row, self.token(step.args["token"])) is True
        elif op != "inspect":
            raise ValueError(f"unknown event: {op}")

    def observe(self) -> dict[str, Any]:
        state, deadline = self.owner.observe(self.row)
        if deadline is None:
            lease = "none"
        elif deadline < self.owner.clock:
            lease = "expired"
        else:
            lease = "live"
        return {"state": state, "lease": lease, "accepted": self.accepted}


def create(root: Path, work: Path, mutant: str | None = None) -> Adapter:
    return Adapter(_owner_type(mutant))
