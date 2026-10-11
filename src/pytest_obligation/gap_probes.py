"""
Typed detect probes for the recurring shapes of missing capability.

A :class:`~.contract.KnownGap` is strongest with a ``detect`` probe — a check
that **fails exactly while the gap exists**, so the fix trips the strict xfail
and forces the declaration to flip to a claim. The first adopters wrote those
probes by hand, which put bespoke assertion logic back inside a declaration —
the exact thing the declarative layer exists to remove. This module owns the
assertions for the gap shapes that recur; an adopter supplies production
bindings only::

    Profile.A: KnownGap(
        "nothing scheduled consumes the derived obligation ...",
        detect=MissingScheduledConsumer(
            make_stranded=lambda: make_aged_upload(age=timedelta(hours=2)),
            outstanding=documents.needing_previews,
            scheduled_tasks=scheduled_task_paths,
            task_name_fragment="preview",
        ),
    )

Each probe is a frozen model whose ``__call__`` runs the standard check.
Because they are defined here — in harness code, not in a test module — the
contract's binding validation accepts them as root-owned; a hand-rolled detect
that neither lives here nor delegates to a shared ``assert_*`` proof is a
design error, nudging the recurring shape into this module where it gets
self-tests and a single owner.
"""

import re
from collections.abc import Callable, Collection, Iterable
from typing import Any

from pytest_obligation.binding import (
    assert_test_binding_delegates_to_production,
)
from pytest_obligation.models import HarnessModel
from pytest_obligation.profiles.automatic_recovery import (
    DueWorkSweep,
    assert_sweep_bindings_are_production_bound,
    assert_the_adapter_does_not_author_the_selection,
    assert_the_adapter_does_not_author_the_tick,
)
from pytest_obligation.profiles.bounded_ownership import (
    FencedOwnership,
    assert_ownership_bindings_are_production_bound,
    assert_ownership_transitions_are_production_bound,
)
from pytest_obligation.profiles.crash_ambiguity import (
    AmbiguityAware,
    assert_ambiguity_bindings_are_production_bound,
    assert_ambiguity_transitions_are_production_bound,
    assert_ordinary_due_work_is_production_bound,
)
from pytest_obligation.profiles.durable_retention import (
    Retention,
    assert_retention_transition_is_production_bound,
)
from pytest_obligation.profiles.eventual_convergence import (
    ConvergentWrite,
    SupersededSnapshot,
    assert_convergence_bindings_are_production_bound,
    assert_evidence_application_is_production_bound,
    assert_snapshot_transitions_are_production_bound,
)
from pytest_obligation.profiles.fact_derived_obligations import (
    StateDerived,
    assert_derivation_bindings_are_production_bound,
    assert_derived_transitions_are_production_bound,
    assert_outstanding_selection_is_production_bound,
    assert_settlement_is_production_bound,
)


def _sweep_guards(sweep: DueWorkSweep) -> None:
    assert_the_adapter_does_not_author_the_selection(sweep)
    assert_the_adapter_does_not_author_the_tick(sweep)
    assert_sweep_bindings_are_production_bound(sweep)


def _ownership_guards(ownership: FencedOwnership) -> None:
    assert_ownership_transitions_are_production_bound(ownership)
    assert_ownership_bindings_are_production_bound(ownership)


def _ambiguity_guards(ambiguity: AmbiguityAware) -> None:
    assert_ambiguity_transitions_are_production_bound(ambiguity)
    assert_ordinary_due_work_is_production_bound(ambiguity)
    assert_ambiguity_bindings_are_production_bound(ambiguity)


def _convergence_guards(convergence: ConvergentWrite) -> None:
    assert_evidence_application_is_production_bound(convergence)
    assert_convergence_bindings_are_production_bound(convergence)


def _derivation_guards(derived: StateDerived) -> None:
    assert_derived_transitions_are_production_bound(derived)
    assert_settlement_is_production_bound(derived)
    assert_outstanding_selection_is_production_bound(derived)
    assert_derivation_bindings_are_production_bound(derived)


#: Each profile binding's full invariant-0 guard set — both halves, authorship
#: and delegation — keyed by adapter type.
_SEMANTIC_BINDING_GUARDS: dict[type, Callable[[Any], None]] = {
    DueWorkSweep: _sweep_guards,
    FencedOwnership: _ownership_guards,
    AmbiguityAware: _ambiguity_guards,
    Retention: assert_retention_transition_is_production_bound,
    ConvergentWrite: _convergence_guards,
    SupersededSnapshot: assert_snapshot_transitions_are_production_bound,
    StateDerived: _derivation_guards,
}


class MissingScheduledConsumer(HarnessModel):
    """
    Due work is derivable from product state, but nothing scheduled consumes it.

    The derived-but-unscheduled shape: the row itself implies the obligation
    (profile F holds), yet a lost dispatch still strands it forever because no
    schedule entry runs a recovery tick. Fails while no scheduled task matches
    ``task_name_fragment``; the fix's schedule entry makes it pass.

    The probe never reads a framework's settings. ``scheduled_tasks`` is the
    adopter's read of what its scheduler actually runs — an integration's
    schedule reader, or a function over the application's own scheduler
    configuration. Bind the real schedule: a hand-written list makes the probe
    measure the list, and one that stays empty keeps the gap "open" after the
    fix lands, which is exactly the silence a strict xfail exists to prevent.
    """

    #: Create one row that owes work, aged past any dispatch grace.
    make_stranded: Callable[[], Any]

    #: The production derivation/selection of outstanding work. The probe first
    #: proves the obligation is derivable, so the gap it reports is precisely
    #: "derivable but unconsumed" rather than "not derivable at all".
    outstanding: Callable[[], Iterable[Any]]

    #: The dotted paths of the tasks something actually schedules, read from
    #: the application's real scheduler configuration on every call.
    scheduled_tasks: Callable[[], Iterable[str]]

    #: A substring a consuming scheduled task's dotted path would contain.
    task_name_fragment: str

    def __call__(self) -> None:
        stranded = self.make_stranded()
        assert stranded in self.outstanding(), (
            "the stranded row is not in the production outstanding selection, so "
            "this probe cannot tell 'derivable but unconsumed' from 'not derivable "
            "at all' — fix make_stranded/outstanding first"
        )

        scheduled = set(self.scheduled_tasks())
        consumers = {task for task in scheduled if self.task_name_fragment in task}
        assert consumers, (
            f"no scheduled task matches {self.task_name_fragment!r} (scheduled: {sorted(scheduled)}), so "
            f"a row stranded by a lost dispatch is never recovered: the obligation "
            f"is derivable (proven above) but nothing scheduled consumes it"
        )


class DisprovenCapability(HarnessModel):
    """
    Executable decline evidence: the discriminating proof fails against
    PRODUCTION bindings, on the assertion it is about.

    A decline's ``prove`` needs to invert a shared proof — a decline IS "this
    invariant genuinely fails here" — and inversion is exactly the move a sham
    contract abuses: wrap ``pytest.raises`` around a shared proof, feed it a
    synthetic adapter built in the test module, and the resulting green test
    "proves" production lacks a capability while measuring only the fake. An
    early profile-F decline shipped in precisely that shape: ``derive=lambda:
    None`` plus a test-authored query, refuting an implementation that never
    existed.

    So inversion lives here, root-owned, and costs what it should:

    * the adapter the binding builds is first run through the profile's full
      invariant-0 guard set, so its semantic fields must be production-bound —
      a synthetic implementation is rejected before anything is "disproven"
      (declared-absent members via ``undeclared(...)`` pass, as they should);
    * the proof must fail by *asserting*, and the failure message must match
      ``match``, pinning the refutation to the invariant it is about rather
      than to an error on the way there;
    * a proof that PASSES fails this probe loudly: the capability exists, and
      the disposition must flip to a claim.
    """

    #: Builds the profile adapter (a
    #: :class:`~pytest_obligation.profiles.fact_derived_obligations.StateDerived`,
    #: :class:`~pytest_obligation.profiles.bounded_ownership.FencedOwnership`, ...) with production-bound
    #: semantic fields; members no proof reaches take
    #: :func:`~pytest_obligation.helpers.undeclared`.
    binding: Callable[[], Any]

    #: The discriminating shared ``assert_*`` proof expected to fail.
    proof: Callable[[Any], None]

    #: A regex the expected failure message must match.
    match: str

    def __call__(self) -> None:
        built = self.binding()
        guard = _SEMANTIC_BINDING_GUARDS.get(type(built))
        assert guard is not None, (
            f"DisprovenCapability: the binding built a {type(built).__name__}, "
            f"which is not a profile adapter this probe knows how to guard"
        )
        guard(built)
        try:
            self.proof(built)
        except AssertionError as error:
            assert re.search(self.match, str(error)), (
                f"the decline names {self.proof.__name__} but the failure was a "
                f"different one ({error}). A refutation that fails on the way "
                f"to its assertion disproves nothing — fix the binding until "
                f"the proof fails on the invariant the decline is about"
            )
            return
        raise AssertionError(
            f"the decline is refuted: {self.proof.__name__} PASSES against "
            f"production bindings, so the capability this contract declines "
            f"actually exists. Flip the disposition to a Claim"
        )


class LossIsAbsorbedElsewhere(HarnessModel):
    """
    Executable evidence for an exemption: lose the dispatch, keep the effect.

    An exemption says the harness's central claim — work published after a
    commit is lost when the broker message dies — does not apply to one
    callable, because something else produces the same effect. That is a
    falsifiable statement about production, and a reason checked only for its
    length is prose, not evidence: nothing stops it from being wrong.

    The probe is the exemption's own sentence, executed:

    * ``strand`` arranges the state the exempted callback would have published
      from, with its dispatch suppressed, and returns the identity;
    * ``observe`` must report the effect ABSENT straight afterwards — the
      positive control that the dispatch really was suppressed, without which
      an exemption "holds" because the effect was there all along;
    * ``absorb`` runs the production path the reason names — the re-derivation,
      the lazy read, the next request — after which the effect must be present.

    ``absorb`` is required to reach production: a test-authored absorber
    proves only that the test can produce the effect, which is never what the
    exemption claims.
    """

    #: Arrange the published-but-undispatched state; return its identity.
    strand: Callable[[], Any]

    #: Read the effect the lost dispatch would have produced. Falsy means absent.
    observe: Callable[[Any], Any]

    #: The production path the exemption's reason names as absorbing the loss.
    absorb: Callable[[Any], Any]

    def __call__(self) -> None:
        assert_test_binding_delegates_to_production(
            adopter="exemption evidence",
            field="absorb",
            binding=self.absorb,
            production_shape="the production path the exemption's reason names as absorbing the lost dispatch",
        )
        identity = self.strand()
        before = self.observe(identity)
        assert not before, (
            f"the effect was already present for {identity!r} before the absorbing path ran, so this probe "
            f"cannot tell 'the loss is absorbed' from 'the dispatch was never actually suppressed'. Arrange "
            f"the state the exempted callback publishes from, with its dispatch suppressed"
        )
        self.absorb(identity)
        after = self.observe(identity)
        assert after, (
            f"the exempted dispatch was lost and the production path the exemption names did not produce the "
            f"effect for {identity!r}. The exemption's reason does not hold: losing this callback loses the work"
        )


class LossDropsOnlyANotification(HarnessModel):
    """
    Executable evidence for a best-effort exemption: the lost dispatch owes nothing but itself.

    Some after-commit work is a courtesy notification that nothing re-derives:
    lose the message and that notification is gone, which the product accepts.
    No absorber exists, so :class:`LossIsAbsorbedElsewhere` cannot bind it
    honestly. The exemption's reason still makes two falsifiable claims about
    production, and this probe runs both:

    * the product state committed with the producer is complete without the
      dispatch, so nothing waits for it;
    * the dispatch is that notification and only that: delivering it produces
      the notification and changes none of that product state.

    The bindings:

    * ``strand`` runs the real producer with the dispatch suppressed and returns
      the identity;
    * ``notified`` reads the notification the dispatch would have produced.
      It must be ABSENT after ``strand``, the positive control that the dispatch
      really was suppressed;
    * ``product`` reads the committed state the reason says does not depend on
      the notification, falsy when that state is incomplete. It must be present
      without the dispatch;
    * ``deliver`` runs the stranded dispatch through production, as a worker
      would. Afterwards ``notified`` must be PRESENT, the positive control that
      it observes this dispatch, and ``product`` must read exactly as before.

    The probe is what turns a dispatch from "best effort" into "owed work" the
    day either claim breaks: a task that starts writing product state, or a
    product state that starts waiting for the task, fails it, and the callable
    then needs a recovering disposition. ``deliver`` must reach production; a
    test-authored deliverer proves only what the test sends.
    """

    #: Run the real producer with the dispatch suppressed; return its identity.
    strand: Callable[[], Any]

    #: Read the notification the dispatch produces. Falsy means absent.
    notified: Callable[[Any], Any]

    #: Read the committed product state the reason says is complete without the notification.
    product: Callable[[Any], Any]

    #: Run the stranded dispatch through production, as a worker would.
    deliver: Callable[[Any], Any]

    def __call__(self) -> None:
        assert_test_binding_delegates_to_production(
            adopter="exemption evidence",
            field="deliver",
            binding=self.deliver,
            production_shape="the production task or worker entry point the lost dispatch would have run",
        )
        identity = self.strand()
        assert not self.notified(identity), (
            f"the notification was already present for {identity!r} before its dispatch was delivered, so "
            f"this probe cannot tell 'nothing waits for it' from 'the dispatch was never actually suppressed'. "
            f"Run the producer with its dispatch suppressed"
        )
        without = self.product(identity)
        assert without, (
            f"the committed product state for {identity!r} is incomplete without the exempted dispatch, so "
            f"something waits for it: losing the dispatch loses product work, not only a notification"
        )
        self.deliver(identity)
        assert self.notified(identity), (
            f"delivering the stranded dispatch produced no notification for {identity!r}, so `notified` does "
            f"not observe what this dispatch does and its absence above proved nothing"
        )
        after = self.product(identity)
        assert after == without, (
            f"delivering the exempted dispatch changed the product state for {identity!r} "
            f"({without!r} -> {after!r}). It does more than notify, and losing it loses that work"
        )


class MissingReclaim(HarnessModel):
    """
    A state that marks work in flight is never re-selected once its owner dies.

    The stamped-then-orphaned shape: a worker stamps the row (``PROCESSING``)
    and then dies; no sweep, lease, or reaper ever selects that state again, so
    the row is stranded forever. Fails while the production tick does not re-dispatch a
    stranded row; the day a reclaim path exists, it passes and trips the strict
    xfail.
    """

    #: Create one row stranded in the unreclaimed state (aged, dead owner) and
    #: return its identity.
    make_stranded: Callable[[], Any]

    #: Run one production recovery tick with dispatch recorded, returning the
    #: identities it dispatched. The recording wrapper is the adopter's — it
    #: patches the domain's own dispatch path — but carries no assertions.
    dispatched_by_one_tick: Callable[[], Collection[Any]]

    def __call__(self) -> None:
        stranded = self.make_stranded()
        dispatched = self.dispatched_by_one_tick()
        assert stranded in dispatched, (
            f"a stranded row ({stranded!r}) was not re-dispatched by the recovery "
            f"tick: nothing in production re-selects its state, so a dead owner "
            f"strands it permanently"
        )
