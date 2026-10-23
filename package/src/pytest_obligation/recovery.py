"""Runtime-neutral recovery coverage and bounded fault histories.

Runtimes supply executable inventories and clock controls. Adopters supply
product examples; they do not implement the proof or copy a recovery selector.
"""

from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from types import MethodType
from typing import Any, Literal
from unittest.mock import patch

from pydantic import Field, TypeAdapter

from pytest_obligation.models import HarnessModel, MutableHarnessModel, ObligationContractDesignError
from pytest_obligation.poison import PoisonDropped, PoisonStalled, PoisonSwitch, assert_poison_is_reported


def same_callback(actual: Callable[..., Any], declared: Callable[..., Any]) -> bool:
    """Bound methods must share both implementation and receiver, never just equality or names."""
    return actual is declared or (
        isinstance(actual, MethodType)
        and isinstance(declared, MethodType)
        and actual.__func__ is declared.__func__
        and actual.__self__ is declared.__self__
    )


def validate_recovery_bindings(
    required: Mapping[str, Callable[..., Any]], declared: Mapping[str, Callable[..., Any]]
) -> None:
    """Match declarations to an independently obtained executable inventory, without running fixtures."""
    missing, stale = required.keys() - declared.keys(), declared.keys() - required.keys()
    if missing or stale:
        raise ObligationContractDesignError(
            f"recovery_steps must cover exactly the custom executable callbacks; "
            f"missing={sorted(missing)}, stale={sorted(stale)}. Supply a product example for each actual step."
        )
    # INVARIANT: a declaration cannot borrow another implementation's evidence.
    for name, actual in required.items():
        if not same_callback(actual, declared[name]):
            raise ObligationContractDesignError(f"recovery_steps[{name}] is bound to a different production callback")


class RecoveryExample(HarnessModel):
    """Independent product candidates, arranged in selection order, and observations of what remains owed.

    A structured runtime can supply ``poison`` automatically at its per-item
    action. Arbitrary loops must bind the real per-identity fault seam.
    ``progressed`` is only needed when dispatch progresses work that stays owed.
    Optional ``diagnose(identity)`` supplies safe string metadata (for example
    retry eligibility) on failure only. It must be read-only; it runs after the
    injected fault context exits and never contributes proof evidence.
    """

    make_pending: Callable[[], Hashable]
    pending: Callable[[Any], bool]
    poison: Callable[[Sequence[Any]], AbstractContextManager[Callable[[], int]]] | None = None
    progressed: Callable[[Any], bool] | None = None
    diagnose: Callable[[Any], Mapping[str, str]] | None = None


class RecoveryCandidateEvidence(MutableHarnessModel):
    """Last product observation plus cumulative progress and injected-fault counts."""

    identity: str
    role: Literal["poisoned", "healthy"]
    owed: bool | None = None
    progressed: bool | None = None
    observed_after_tick: int | None = None
    fault_count: int = 0
    details: dict[str, str] = Field(default_factory=dict)
    diagnostic_error: str | None = None


class RecoveryDiagnostics(MutableHarnessModel):
    """Failure-note schema; observations never execute additional recovery work."""

    name: str
    stage: Literal["arranging", "control", "poisoned", "held", "resumed"] = "arranging"
    ticks: int = 0
    candidates: list[RecoveryCandidateEvidence]


def _identity_label(identity: Hashable) -> str:
    try:
        label = repr(identity)
    except Exception:  # noqa: BLE001 - diagnostics must preserve the proof failure
        return f"<{type(identity).__name__}: repr unavailable>"
    return label if len(label) <= 300 else label[:297] + "..."


@contextmanager
def _diagnose_recovery_failure(
    evidence: RecoveryDiagnostics, example: RecoveryExample, identities: Sequence[Hashable]
) -> Iterator[None]:
    try:
        yield
    except Exception as error:
        # INVARIANT: retain the original exception type (including known-gap
        # classifiers), traceback and cause. Metadata is optional, never proof.
        for identity, candidate in zip(identities, evidence.candidates, strict=True):
            if example.diagnose is not None:
                try:
                    candidate.details = TypeAdapter(dict[str, str]).validate_python(example.diagnose(identity))
                except Exception as diagnostic_error:  # noqa: BLE001 - a broken observer must not mask the failure
                    candidate.diagnostic_error = type(diagnostic_error).__name__
        try:
            error.add_note("Recovery diagnostics:\n" + evidence.model_dump_json(indent=2))
        except Exception as diagnostic_error:  # noqa: BLE001 - invalid optional metadata is also non-fatal
            error.add_note(f"Recovery diagnostics unavailable: {type(diagnostic_error).__name__}")
        raise


class PoisonCounts(HarnessModel):
    """Per-candidate fault observations; one firing cannot stand in for an entire page."""

    counters: tuple[Callable[[], int], ...]

    def __call__(self) -> int:
        return sum(counter() for counter in self.counters)


@contextmanager
def poison_many(
    poison: Callable[[Any], AbstractContextManager[Callable[[], int]]], identities: Sequence[Any]
) -> Iterator[PoisonCounts]:
    """Compose existing single-identity seams; counters survive context exit."""
    with ExitStack() as stack:
        counts = [stack.enter_context(poison(identity)) for identity in identities]
        yield PoisonCounts(counters=tuple(counts))


@contextmanager
def poison_call(
    target: object, attribute: str, identity_of: Callable[..., Any], identities: Sequence[Any]
) -> Iterator[PoisonCounts]:
    """Refuse selected identities at a real call boundary; delegate all others unchanged."""
    original = getattr(target, attribute)
    switch = PoisonSwitch()
    with poison_many(switch.poisoned, identities) as fired:

        def invoke(*args: Any, **kwargs: Any) -> Any:
            switch.check(identity_of(*args, **kwargs), f"{attribute} recovery fault")
            return original(*args, **kwargs)

        with patch.object(target, attribute, invoke):
            yield fired


def assert_recovery_history(
    *,
    name: str,
    example: RecoveryExample,
    run_tick: Callable[[], Any],
    page_size: int,
    poison: bool,
    resume: Callable[[], None],
    assert_held: Callable[[Sequence[Any]], None] | None = None,
) -> None:
    """A full failing page cannot starve healthy work or turn backoff into abandonment.

    Two ticks must reach the next page. Each tick that encounters a fault must
    report it, and each failed candidate must stay owed. After ``resume`` makes
    retries eligible, at most one tick per arranged candidate must make progress.
    The same arrangement without faults is the positive control. No database,
    scheduler, sleep, retry-table implementation or application transition lives here.
    """
    assert page_size > 0, f"{name}: recovery page size must be positive"
    candidates = [example.make_pending() for _ in range(page_size + 1)]
    evidence = RecoveryDiagnostics(
        name=name,
        candidates=[
            RecoveryCandidateEvidence(
                identity=_identity_label(identity),
                role="poisoned" if poison and index < page_size else "healthy",
            )
            for index, identity in enumerate(candidates)
        ],
    )
    with _diagnose_recovery_failure(evidence, example, candidates):
        _run_recovery_history(
            name=name,
            example=example,
            candidates=candidates,
            evidence=evidence,
            run_tick=run_tick,
            poison=poison,
            resume=resume,
            assert_held=assert_held,
        )


def _run_recovery_history(
    *,
    name: str,
    example: RecoveryExample,
    candidates: list[Hashable],
    evidence: RecoveryDiagnostics,
    run_tick: Callable[[], Any],
    poison: bool,
    resume: Callable[[], None],
    assert_held: Callable[[Sequence[Any]], None] | None,
) -> None:
    assert len(set(candidates)) == len(candidates), f"{name}: recovery examples must create independent candidates"
    for identity, candidate in zip(candidates, evidence.candidates, strict=True):
        candidate.owed = example.pending(identity)
        candidate.observed_after_tick = 0
    assert all(candidate.owed for candidate in evidence.candidates), f"{name}: every arranged candidate must owe work"
    bad, healthy = candidates[:-1], candidates[-1]
    progressed: set[Hashable] = set()

    def tick() -> None:
        evidence.ticks += 1
        run_tick()

    def observe() -> None:
        for identity, candidate in zip(candidates, evidence.candidates, strict=True):
            owed = example.pending(identity)
            advanced = example.progressed(identity) if example.progressed is not None else not owed
            if advanced:
                progressed.add(identity)
            candidate.owed = owed
            candidate.progressed = identity in progressed
            candidate.observed_after_tick = evidence.ticks

    if not poison:
        evidence.stage = "control"
        for _ in range(2):
            tick()
            observe()
        assert set(candidates) <= progressed, f"{name}: healthy recovery control did not progress"
        return

    assert example.poison is not None, f"{name}: bind the real per-identity poison seam"
    evidence.stage = "poisoned"
    for tick_index in range(2):
        with example.poison(bad) as fired:
            assert isinstance(fired, PoisonCounts) and len(fired.counters) == len(bad), (
                f"{name}: use poison_many or poison_call to observe each candidate's fault"
            )
            escaped: Exception | None = None
            try:
                tick()
            except Exception as error:  # noqa: BLE001 - this is the production report under test
                escaped = error
        # Faults belong to production execution, not product observation. Some
        # native observations inspect the real selector with deliveries held.
        # Their calls must neither trip the fault nor count as proof it fired.
        for candidate, counter in zip(evidence.candidates[:-1], fired.counters, strict=True):
            candidate.fault_count += counter()
        # Check every tick: an earlier loud report cannot hide a later silent failure.
        if fired() > 0:
            assert_poison_is_reported(name, escaped)
        elif escaped is not None:
            raise escaped
        if tick_index == 0:
            assert fired() > 0, f"{name}: the poison never fired; bind the real per-identity action"
        observe()
        if not all(candidate.owed for candidate in evidence.candidates[:-1]):
            raise PoisonDropped(f"{name}: failed recovery work is no longer owed")
    if healthy not in progressed:
        raise PoisonStalled(f"{name}: healthy work behind a poisoned page did not progress within two ticks")
    assert all(candidate.fault_count > 0 for candidate in evidence.candidates[:-1]), (
        f"{name}: the poison never fired for every page candidate"
    )
    if assert_held is not None:
        evidence.stage = "held"
        assert_held(bad)
        with example.poison(bad) as fired:
            try:
                tick()
            finally:
                if isinstance(fired, PoisonCounts):
                    for candidate, counter in zip(evidence.candidates[:-1], fired.counters, strict=True):
                        candidate.fault_count += counter()
        assert fired() == 0, f"{name}: deferred candidates were retried before their hold ended"
    evidence.stage = "resumed"
    resume()
    for _ in candidates:
        tick()
        observe()
        if set(bad) <= progressed:
            break
    assert set(bad) <= progressed, f"{name}: deferred recovery work was abandoned"
