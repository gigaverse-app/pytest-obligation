"""The shared recovery oracle must reject behavioral counterexamples, independently of Due."""

import pytest

from pytest_obligation.poison import PoisonedIdentity, PoisonStalled, PoisonSwitch
from pytest_obligation.recovery import RecoveryExample, assert_recovery_history, poison_many


class _Loop:
    """Small native runtime control: ordered pending work and a recoverable hold."""

    def __init__(self, defect=""):
        self.defect = defect
        self.owed = set()
        self.held = set()
        self.switch = PoisonSwitch()
        self.sequence = 0
        self.ticks = 0

    def make(self):
        self.sequence += 1
        self.owed.add(self.sequence)
        return self.sequence

    def tick(self):
        self.ticks += 1
        if self.defect == "noop":
            return
        errors = []
        selected = self.owed if self.defect in {"starved", "silent-second"} else self.owed - self.held
        for identity in sorted(selected)[:2]:
            if self.defect == "partial-seam" and identity == 2:
                continue
            try:
                if self.defect != "wrong-seam":
                    self.switch.check(identity)
                self.owed.remove(identity)
            except PoisonedIdentity as error:
                if self.defect == "abort":
                    raise
                self.held.add(identity)
                if self.defect == "dropped":
                    self.owed.remove(identity)
                errors.append(error)
        if errors and not (self.defect == "silent-second" and self.ticks == 2):
            raise ExceptionGroup("isolated rows", errors)

    def resume(self):
        if self.defect != "abandoned":
            self.held.clear()

    def example(self):
        return RecoveryExample(
            make_pending=self.make,
            pending=lambda identity: identity in self.owed,
            poison=lambda identities: poison_many(self.switch.poisoned, identities),
        )


def test_an_aborting_loop_is_a_starvation_defect_not_an_unused_fault_binding():
    loop = _Loop("abort")
    with pytest.raises(PoisonStalled):
        assert_recovery_history(
            name="native", example=loop.example(), run_tick=loop.tick, page_size=2, poison=True, resume=loop.resume
        )


@pytest.mark.parametrize("poison", [False, True])
def test_native_recovery_preserves_and_retries_a_poisoned_page(poison):
    loop = _Loop()
    assert_recovery_history(
        name="native", example=loop.example(), run_tick=loop.tick, page_size=2, poison=poison, resume=loop.resume
    )


def test_product_observation_runs_outside_the_injected_runtime_fault():
    loop = _Loop()

    def pending(identity):
        # A native observation may inspect the selection via the production
        # callback with deliveries held. That is not a faulted recovery tick.
        loop.switch.check(identity)
        return identity in loop.owed

    example = loop.example().model_copy(update={"pending": pending})
    assert_recovery_history(
        name="native", example=example, run_tick=loop.tick, page_size=2, poison=True, resume=loop.resume
    )


@pytest.mark.parametrize(
    "defect,poison,reason",
    [
        ("starved", True, "did not progress"),
        ("dropped", True, "no longer owed"),
        ("silent-second", True, "reported nothing"),
        ("wrong-seam", True, "no longer owed|poison never fired"),
        ("abandoned", True, "abandoned"),
        ("partial-seam", True, "never fired for every"),
        ("noop", False, "control did not progress"),
    ],
)
def test_shared_history_rejects_false_recovery_claims(defect, poison, reason):
    loop = _Loop(defect)
    with pytest.raises(AssertionError, match=reason):
        assert_recovery_history(
            name="native", example=loop.example(), run_tick=loop.tick, page_size=2, poison=poison, resume=loop.resume
        )
