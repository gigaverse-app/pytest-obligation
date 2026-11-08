"""pytest-quint-connect driver: apply Quint events to profile C's reference machine, InMemoryMachine."""

import hashlib
from pathlib import Path
from typing import Any

from pytest_obligation.references.in_memory import InMemoryMachine

SHIPPED_9AA6FF2_SHA256 = "6dd65daf8e042104c7a4f06ec1e3345179321fee49601bf25122cec313c2b846"


def _machine_type(mutant: str | None) -> type[InMemoryMachine]:
    if mutant is None:
        return InMemoryMachine
    if mutant == "shipped-9aa6ff2":
        # The exact pre-fix reaper, run on a subclass of today's machine. The hash keeps this
        # frozen evidence from being edited until it agrees with the model.
        shipped = Path(__file__).with_name("resolve-9aa6ff2.py.txt")
        text = shipped.read_bytes()
        assert hashlib.sha256(text).hexdigest() == SHIPPED_9AA6FF2_SHA256, f"{shipped} was edited"
        namespace: dict[str, Any] = {}
        exec(compile(text, str(shipped), "exec"), namespace)
        return type("ShippedMachine", (InMemoryMachine,), {"resolve_stalled": namespace["resolve_stalled"]})
    if mutant == "blind-retry":

        def resolve_stalled(self: InMemoryMachine, row_id: int) -> str | None:
            row = self.rows[row_id]
            if row.state == "SENT":
                return None
            row.state = "READY"
            return "REARM_READY"

        return type("BlindRetry", (InMemoryMachine,), {"resolve_stalled": resolve_stalled})
    if mutant == "ambiguous-redispatch":

        def due_work_ids(self: InMemoryMachine) -> set[int]:
            return {row_id for row_id, row in self.rows.items() if row.state in ("READY", "UNKNOWN")}

        return type("AmbiguousRedispatch", (InMemoryMachine,), {"due_work_ids": due_work_ids})
    raise ValueError(f"unknown planted bug: {mutant}")


class Adapter:
    def __init__(self, machine_type: type[InMemoryMachine]) -> None:
        self.machine_type = machine_type

    def step(self, step: Any) -> None:
        op = step.action
        if op == "init":
            self.machine = self.machine_type()
            self.row, self.token = self.machine.claim()
        elif op == "startAttempt":
            self.machine.start_attempt(self.row, self.token)
        elif op == "expire":
            self.machine.expire_lease(self.row)
        elif op == "resolve":
            self.machine.resolve_stalled(self.row)
        elif op == "evidence":
            self.machine.apply_late_evidence(self.row)
        elif op != "inspect":
            raise ValueError(f"unknown event: {op}")

    def observe(self) -> dict[str, Any]:
        return {
            "state": self.machine.state_of(self.row),
            "attempt": self.machine.open_attempt(self.row) is not None,
            "due": self.row in self.machine.due_work_ids(),
        }


def create(root: Path, work: Path, mutant: str | None = None) -> Adapter:
    return Adapter(_machine_type(mutant))
