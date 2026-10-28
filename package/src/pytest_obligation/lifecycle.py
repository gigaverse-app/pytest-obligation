"""Production lifecycle histories that isolated admission and replay cannot prove.

Bindings own fresh resources and external fault seams. The harness owns the
schedule and compares product outcomes to independently declared expectations.
These histories cover declared checkpoints and producer pairs, not every race.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from pytest_obligation.binding import INVOCATION_AUTHORING_OPERATIONS, assert_binding_reaches_production
from pytest_obligation.helpers import Binding, entered_binding
from pytest_obligation.models import HarnessModel


class AdmissionOverlap(HarnessModel):
    """Two production producers admitting cumulative effects for the same owner.

    The binding captures one owner. ``first`` admits a subset and ``later``
    admits additional effects; suppress their notifications in the binding.
    ``recover`` runs actual registered recovery, including bounded clock advances
    if needed. Observe all promised effects and meaningful duplicate counts.
    Expectations are reviewed product outcomes, never learned from a control run.
    """

    first: Callable[[], object]
    later: Callable[[], object]
    recover: Callable[[], object]
    observe: Callable[[], Any]
    expected_first: Any
    expected_combined: Any


class SettlementInterleaving(HarnessModel):
    """A competing real transition at an external observation/settlement boundary.

    Arrange admitted work before yielding. ``during`` installs an external seam
    that invokes its callback exactly once while ``run`` executes. ``compete``
    calls the other production transition; it must change ``observe_competing``.
    The seam must not implement or patch the settlement decision under proof.
    """

    run: Callable[[], object]
    compete: Callable[[], object]
    observe_competing: Callable[[], Any]
    during: Callable[[Callable[[], None]], AbstractContextManager[object]]
    recover: Callable[[], object]
    observe: Callable[[], Any]
    expected: Any


class PartialProgress(HarnessModel):
    """Recovery after a definite failure leaves some effects completed.

    Arrange admitted work with notifications held. The failure context installs
    only an external fault and yields its cumulative hit counter. Run drives the
    first real attempt; recover advances a bounded clock if needed and drives
    registered recovery, with the fault removed. Both expectations must come
    from the product promise. Observe every effect in the declared scope.

    completed_effects optionally snapshots successful effect call counts.
    Supply it when the workflow promises to checkpoint successful groups. Raw
    replay-safe effects may legitimately run again; do not impose this stronger
    efficiency guarantee on those workflows.
    """

    run: Callable[[], object]
    recover: Callable[[], object]
    failure: Callable[[], AbstractContextManager[Callable[[], int]]]
    observe: Callable[[], Any]
    expected_partial: Any
    expected: Any
    completed_effects: Callable[[], Any] | None = None


def assert_lifecycle_bindings_are_production_bound(
    example: AdmissionOverlap | SettlementInterleaving | PartialProgress,
) -> None:
    if isinstance(example, AdmissionOverlap):
        fields = ("first", "later", "recover")
    elif isinstance(example, SettlementInterleaving):
        fields = ("run", "compete", "recover")
    else:
        fields = ("run", "recover")
    for field in fields:
        assert_binding_reaches_production(
            adopter="lifecycle history",
            field=field,
            binding=getattr(example, field),
            forbidden=INVOCATION_AUTHORING_OPERATIONS,
            production_shape="the actual application command or registered recovery entry point",
        )


def _assert_admission_overlap(example: AdmissionOverlap, *, settled: bool) -> None:
    assert_lifecycle_bindings_are_production_bound(example)
    assert example.expected_first != example.expected_combined, "overlap expectations hide the additional effects"
    assert example.observe() != example.expected_first, "first admission already has its product outcome"
    example.first()
    assert example.observe() != example.expected_first, "first admission must leave pending effects for this history"
    if settled:
        example.recover()
        assert example.observe() == example.expected_first, "first admission did not reach its declared outcome"
    example.later()
    example.recover()
    assert example.observe() == example.expected_combined, "overlapping admissions lost or duplicated promised effects"
    # An old producer can return after expansion. It cannot erase the broader
    # promise, repeat completed effects, or reset progress.
    example.first()
    example.recover()
    assert example.observe() == example.expected_combined, "subset replay lost or duplicated promised effects"


def assert_pending_admission_preserves_effects(example: AdmissionOverlap) -> None:
    _assert_admission_overlap(example, settled=False)


def assert_settled_admission_preserves_effects(example: AdmissionOverlap) -> None:
    _assert_admission_overlap(example, settled=True)


def assert_competing_transition_preserves_effects(example: SettlementInterleaving) -> None:
    assert_lifecycle_bindings_are_production_bound(example)
    assert example.observe() != example.expected, "interleaving already has its product outcome"
    reached = 0
    running = False
    checkpoint_error: BaseException | None = None

    def checkpoint() -> None:
        nonlocal reached, checkpoint_error
        try:
            assert running, "checkpoint ran outside the production operation"
            reached += 1
            assert reached == 1, "checkpoint ran more than once"
            before = example.observe_competing()
            example.compete()
            assert example.observe_competing() != before, "competing transition changed no product state"
        except BaseException as error:
            checkpoint_error = error
            raise

    with example.during(checkpoint):
        running = True
        try:
            example.run()
        finally:
            running = False
    if checkpoint_error is not None:
        raise checkpoint_error
    assert reached == 1, "production operation never reached the declared checkpoint"
    example.recover()
    assert example.observe() == example.expected, "competing transition discarded or duplicated admitted effects"


def assert_partial_progress_recovers(example: PartialProgress) -> None:
    assert_lifecycle_bindings_are_production_bound(example)
    assert example.expected_partial != example.expected, "partial expectations hide the remaining effects"
    initial = example.observe()
    assert initial != example.expected_partial, "partial progress already exists before the attempt"
    assert initial != example.expected, "partial progress already has its terminal outcome"
    with example.failure() as hits:
        before = hits()
        example.run()
        assert hits() > before, "production operation never reached the injected failure"
    assert example.observe() == example.expected_partial, "failed attempt missed its declared partial outcome"
    completed = example.completed_effects() if example.completed_effects is not None else None
    example.recover()
    if example.completed_effects is not None:
        assert example.completed_effects() == completed, "recovery repeated completed effect groups"
    assert example.observe() == example.expected, "partial progress lost remaining promised effects"
    example.recover()
    if example.completed_effects is not None:
        assert example.completed_effects() == completed, "settled recovery repeated completed effect groups"
    assert example.observe() == example.expected, "settled recovery changed the declared outcome"


class LifecycleProof(HarnessModel):
    """Configure a lifecycle proof through an existing host's ``ExtraProof`` API.

    This compatibility route runs the same assertions as the named contract
    fields, allowing adopters to upgrade the proof library independently of a
    runtime release. The binding scope stays open for the entire proof.
    """

    binding: Binding[Any]
    proof: Callable[[Any], None]

    def __call__(self) -> None:
        assert self.proof in (
            assert_pending_admission_preserves_effects,
            assert_settled_admission_preserves_effects,
            assert_competing_transition_preserves_effects,
            assert_partial_progress_recovers,
        ), "LifecycleProof requires a shared lifecycle assertion"
        with entered_binding(self.binding) as example:
            self.proof(example)
