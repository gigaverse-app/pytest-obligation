"""Failure attribution from exception identity and guard origin, never message keywords."""

from typing import Literal

from pydantic import Field, ValidationError

from pytest_obligation.models import HarnessModel, ObligationContractDesignError
from pytest_obligation.recovery import RecoveryDiagnostics


class FailureEvidence(HarnessModel):
    phase: str
    kind: Literal["binding", "check", "test environment"]
    message: str
    recovery: list[RecoveryDiagnostics] = Field(default_factory=list)


def failure_evidence(error: BaseException, phase: str) -> FailureEvidence:
    """A rejected harness binding invalidates that proof, not every test in the project."""
    trace = error.__traceback__
    while trace is not None and trace.tb_next is not None:
        trace = trace.tb_next
    module = trace.tb_frame.f_globals.get("__name__") if trace else None
    function = trace.tb_frame.f_code.co_name if trace else None
    binding = isinstance(error, ObligationContractDesignError) or (
        isinstance(error, AssertionError)
        and (
            module == "pytest_obligation.binding"
            or (module == "pytest_obligation.host" and function in ("require", "inspector_for"))
        )
    )
    recovery = []
    for note in getattr(error, "__notes__", ()):
        if isinstance(note, str) and note.startswith("Recovery diagnostics:\n"):
            try:
                recovery.append(RecoveryDiagnostics.model_validate_json(note.split("\n", 1)[1]))
            except ValidationError:
                pass  # Optional diagnostics must never mask the original failure.
    try:
        message = str(error)[:1200]
    except Exception:
        message = "Exception message unavailable"
    return FailureEvidence(
        phase=phase,
        kind="binding" if binding else "check" if phase == "call" else "test environment",
        message=f"{type(error).__name__}: {message}",
        recovery=recovery,
    )
