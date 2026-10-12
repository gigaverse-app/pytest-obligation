"""One independent expected-outcome contract shared by history and replay proofs."""

from collections.abc import Callable
from enum import Enum, auto
from typing import Any, Generic, TypeVar

from pytest_obligation.models import HarnessModel

HandleT = TypeVar("HandleT")
ObservationT = TypeVar("ObservationT")


class _ExpectedOutcome(Enum):
    UNSPECIFIED = auto()


class ExpectedOutcome(HarnessModel, Generic[HandleT, ObservationT]):
    """An input-derived product requirement, independent of the observed result."""

    name: str
    #: None is a real requirement. Omission only permits standalone convergence proofs.
    expected: ObservationT | Callable[[HandleT], ObservationT] | _ExpectedOutcome = _ExpectedOutcome.UNSPECIFIED

    def expected_for(self, handle: HandleT) -> ObservationT | _ExpectedOutcome:
        """Resolve before executing/recovering; never infer correctness from the result."""
        return self.expected(handle) if callable(self.expected) else self.expected

    def require_expected_outcome(self) -> None:
        """Generated application contracts must establish correctness, not just agreement."""
        if self.expected is _ExpectedOutcome.UNSPECIFIED:
            raise ValueError(f"{self.name}: declare expected independently of observe to prove application correctness")


def assert_expected_outcome(name: str, expected: Any, observed: Any) -> None:
    """None-safe assertion shared by normal histories and initial/replayed effects."""
    if expected is not _ExpectedOutcome.UNSPECIFIED:
        assert observed == expected, (
            f"{name} did not reach the declared product outcome: expected {expected!r}, observed {observed!r}"
        )
