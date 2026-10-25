"""
Profile C, acknowledged effects: a provider's reply is not its effect.

Some providers answer before they act. A bulk delete answers with a task id
and deletes in the background; a billing API answers 202 and may reject the
event later. If production treats that reply as the effect and discharges its
obligation, a provider that later fails, drops or never runs the work leaves
nothing owed and nothing that will notice.

Crash ambiguity (the ``ambiguity`` binding) asks what happens when the reply
never arrives. This binding asks the neighbouring question: what happens when
the reply arrives and the effect does not. It needs no attempt journal and no
ambiguous state, only three facts about one owed operation:

1. **An acknowledgement does not discharge.** With the provider holding its
   acknowledgements, one production run reaches the provider (a counted
   positive control) and the effect stays unapplied, yet the operation must
   still be owed according to production's own owed-work selection.
2. **An applied acknowledgement does discharge.** The operation is still owed
   after the held run, and once the provider applies what it acknowledged, a
   bounded number of further production runs must discharge it. Without this,
   an implementation that never discharges anything would pass the first proof;
   without the owed check, one that discharges on the reply would pass this one.

Bind the provider half with :class:`pytest_obligation.fakes.AsyncTasks`, or any
fake whose acknowledgements can be held and later applied. Declare it only for
an API whose documented contract acknowledges receipt rather than completion;
an API that replies once the operation is done may be trusted without a read-back.
"""

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from typing import Any

from pytest_obligation.binding import (
    INVOCATION_AUTHORING_OPERATIONS,
    SELECTION_AUTHORING_OPERATIONS,
    assert_binding_reaches_production,
)
from pytest_obligation.models import HarnessModel


def _identity(value: Any) -> Any:
    return value


class AcknowledgedEffect(HarnessModel):
    """One owed operation whose external effect the provider acknowledges before applying."""

    name: str

    #: ARRANGE one owed operation whose effect goes through the acknowledging provider.
    make_owed: Callable[[], Any]

    #: REAL PRODUCTION: the selection of work production still owes (a recovery
    #: sweep's outstanding query, or the scheduled pass's candidates). The harness
    #: decides membership, so a test predicate cannot stand in for production.
    owed_work: Callable[[], Iterable[Any]]

    #: REAL PRODUCTION: run the production executor or scheduled pass once.
    run_once: Callable[[Any], Any]

    #: EXTERNAL SEAM: inside this context the provider acknowledges requests for
    #: the operation without applying them (``AsyncTasks.held``).
    hold_acknowledgements: Callable[[Any], AbstractContextManager[Any]]

    #: OBSERVE: acknowledgements the provider issued for the operation, counted at
    #: the provider boundary: the positive control that a run reached it.
    acknowledgement_count: Callable[[Any], int]

    #: OBSERVE: whether the provider-side effect exists, read from the provider's
    #: state rather than from anything production recorded.
    applied: Callable[[Any], bool]

    #: EXTERNAL SEAM: the provider applies every acknowledgement it holds for the operation.
    apply_acknowledged: Callable[[Any], Any]

    #: Production runs allowed, after the provider applies, to discharge the operation.
    max_runs_to_discharge: int = 3

    #: Convert the arranged operation and each owed item to one comparable identity.
    identity_of: Callable[[Any], Any] = _identity

    def model_post_init(self, _context: Any) -> None:
        if self.max_runs_to_discharge < 1:
            raise ValueError("AcknowledgedEffect.max_runs_to_discharge must be at least one")


def _is_owed(effect: AcknowledgedEffect, operation: Any) -> bool:
    identity = effect.identity_of(operation)
    return any(effect.identity_of(item) == identity for item in effect.owed_work())


def _fresh(effect: AcknowledgedEffect) -> Any:
    operation = effect.make_owed()
    assert _is_owed(effect, operation), (
        f"{effect.name}: make_owed() did not create work production owes, so no run can be measured"
    )
    assert not effect.applied(operation), f"{effect.name}: make_owed() created an already-applied effect"
    return operation


def _run_holding(effect: AcknowledgedEffect, operation: Any) -> None:
    before = effect.acknowledgement_count(operation)
    with effect.hold_acknowledgements(operation):
        effect.run_once(operation)
    reached = effect.acknowledgement_count(operation) - before
    assert reached >= 1, (
        f"{effect.name}: the production run never reached the acknowledging provider "
        f"({before} -> {before + reached} acknowledgements), so the history proves nothing about its reply"
    )
    assert not effect.applied(operation), (
        f"{effect.name}: the provider applied an acknowledgement it was told to hold. "
        f"hold_acknowledgements does not hold, so the history cannot separate a reply from its effect"
    )


def assert_acknowledgement_bindings_are_production_bound(effect: AcknowledgedEffect) -> None:
    """The runner and the owed-work selection are production's, not a test state machine."""
    assert_binding_reaches_production(
        adopter=effect.name,
        field="run_once",
        binding=effect.run_once,
        forbidden=INVOCATION_AUTHORING_OPERATIONS,
        production_shape="the production executor",
    )
    assert_binding_reaches_production(
        adopter=effect.name,
        field="owed_work",
        binding=effect.owed_work,
        forbidden=SELECTION_AUTHORING_OPERATIONS,
        production_shape="the production owed-work selection",
    )


def assert_an_acknowledgement_does_not_discharge(effect: AcknowledgedEffect) -> None:
    """INVARIANT 1: a reply alone leaves the operation owed."""
    operation = _fresh(effect)
    _run_holding(effect, operation)
    assert _is_owed(effect, operation), (
        f"{effect.name}: production discharged the operation on the provider's acknowledgement alone. "
        f"The effect never applied, and if the provider fails or drops it nothing is left owed to notice"
    )


def assert_an_applied_acknowledgement_discharges(effect: AcknowledgedEffect) -> None:
    """INVARIANT 2: once the provider applies, production discharges within a bounded number of runs."""
    operation = _fresh(effect)
    _run_holding(effect, operation)
    assert _is_owed(effect, operation), (
        f"{effect.name}: production discharged the operation before the provider applied it, so this history "
        f"cannot show that applying is what discharges it. assert_an_acknowledgement_does_not_discharge names the defect"
    )
    effect.apply_acknowledged(operation)
    assert effect.applied(operation), (
        f"{effect.name}: apply_acknowledged did not apply the held acknowledgement, so discharge cannot be measured"
    )
    for _ in range(effect.max_runs_to_discharge):
        if not _is_owed(effect, operation):
            return
        effect.run_once(operation)
    assert not _is_owed(effect, operation), (
        f"{effect.name}: the provider applied the effect, yet {effect.max_runs_to_discharge} further production "
        f"run(s) left the operation owed. Work the provider finished would be repeated or retained forever"
    )


ACKNOWLEDGED_EFFECT_PROOFS: tuple[Callable[[AcknowledgedEffect], None], ...] = (
    assert_an_acknowledgement_does_not_discharge,
    assert_an_applied_acknowledgement_discharges,
)


def assert_acknowledged_effect_contract(effect: AcknowledgedEffect) -> None:
    """Run the production-binding guard and both acknowledgement invariants."""
    assert_acknowledgement_bindings_are_production_bound(effect)
    for proof in ACKNOWLEDGED_EFFECT_PROOFS:
        proof(effect)
