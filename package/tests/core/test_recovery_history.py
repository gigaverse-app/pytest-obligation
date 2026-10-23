"""The shared recovery oracle must reject behavioral counterexamples, independently of Due."""

import json

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
    with pytest.raises(AssertionError, match=reason) as caught:
        assert_recovery_history(
            name="native", example=loop.example(), run_tick=loop.tick, page_size=2, poison=poison, resume=loop.resume
        )
    evidence = json.loads(caught.value.__notes__[-1].removeprefix("Recovery diagnostics:\n"))
    assert evidence["name"] == "native"
    assert evidence["ticks"] == loop.ticks
    assert [row["identity"] for row in evidence["candidates"]] == ["1", "2", "3"]
    assert evidence["candidates"][-1]["role"] == "healthy"
    if defect == "starved":
        assert evidence["stage"] == "poisoned"
        assert [row["fault_count"] for row in evidence["candidates"]] == [2, 2, 0]
        assert all(row["owed"] and not row["progressed"] for row in evidence["candidates"])
        assert all(row["observed_after_tick"] == 2 for row in evidence["candidates"])
    elif defect == "dropped":
        assert [row["owed"] for row in evidence["candidates"]] == [False, False, True]
    elif defect == "abandoned":
        assert evidence["stage"] == "resumed"
        assert evidence["candidates"][-1]["progressed"]
    elif defect == "partial-seam":
        assert [row["fault_count"] for row in evidence["candidates"]] == [1, 0, 0]
    elif defect == "silent-second":
        # The reporting assertion fails before observation: the timestamp must
        # expose that these are the preceding tick's observations.
        assert all(row["observed_after_tick"] == 1 for row in evidence["candidates"])


@pytest.mark.parametrize("broken_metadata", ["", "raises", "invalid"])
def test_runtime_diagnostics_preserve_failure_type_and_run_outside_faults(broken_metadata):
    loop = _Loop("starved")
    inspected = []

    def diagnose(identity):
        loop.switch.check(identity)
        inspected.append(identity)
        if broken_metadata == "raises":
            raise RuntimeError("metadata unavailable")
        if broken_metadata == "invalid":
            return {"unsupported": object()}
        return {"retry_at": "2030-01-01T00:00:00Z", "held": str(identity in loop.held)}

    example = loop.example().model_copy(update={"diagnose": diagnose})
    with pytest.raises(PoisonStalled) as caught:
        assert_recovery_history(
            name="native", example=example, run_tick=loop.tick, page_size=2, poison=True, resume=loop.resume
        )
    evidence = json.loads(caught.value.__notes__[-1].removeprefix("Recovery diagnostics:\n"))
    assert inspected == [1, 2, 3]
    assert loop.ticks == 2
    for row in evidence["candidates"]:
        if broken_metadata:
            assert row["diagnostic_error"] == ("RuntimeError" if broken_metadata == "raises" else "ValidationError")
        else:
            assert row["details"]["retry_at"] == "2030-01-01T00:00:00Z"


def test_successful_recovery_does_not_read_optional_diagnostics():
    loop = _Loop()

    def diagnose(identity):
        pytest.fail("Successful histories must not read diagnostics")

    assert_recovery_history(
        name="native",
        example=loop.example().model_copy(update={"diagnose": diagnose}),
        run_tick=loop.tick,
        page_size=2,
        poison=True,
        resume=loop.resume,
    )


def test_held_tick_records_fault_counts_and_preserves_the_original_exception():
    loop = _Loop()
    failures = []

    def tick():
        try:
            loop.tick()
        except ExceptionGroup as error:
            failures.append(error)
            raise

    def break_hold(identities):
        loop.held.clear()

    with pytest.raises(ExceptionGroup) as caught:
        assert_recovery_history(
            name="native",
            example=loop.example(),
            run_tick=tick,
            page_size=2,
            poison=True,
            resume=loop.resume,
            assert_held=break_hold,
        )
    assert caught.value is failures[-1]
    evidence = json.loads(caught.value.__notes__[-1].removeprefix("Recovery diagnostics:\n"))
    assert evidence["stage"] == "held"
    assert evidence["ticks"] == 3
    assert [row["fault_count"] for row in evidence["candidates"]] == [2, 2, 0]


def test_diagnostics_do_not_repeat_product_observations_after_a_failure():
    loop = _Loop("noop")
    observed = []

    def pending(identity):
        observed.append(identity)
        return identity in loop.owed

    with pytest.raises(AssertionError, match="control did not progress"):
        assert_recovery_history(
            name="native",
            example=loop.example().model_copy(update={"pending": pending}),
            run_tick=loop.tick,
            page_size=2,
            poison=False,
            resume=loop.resume,
        )
    # Initial arrangement and two normal observations; failure adds no reads.
    assert observed == [1, 2, 3] * 3


def test_pytest_displays_recovery_evidence_in_the_original_failure(pytester: pytest.Pytester):
    pytester.makepyfile("""
from itertools import count
from pytest_obligation.recovery import RecoveryExample, assert_recovery_history

def test_abandoned_control():
    identities = count(1)
    example = RecoveryExample(make_pending=lambda: next(identities), pending=lambda identity: True)
    assert_recovery_history(
        name="receipts", example=example, run_tick=lambda: None,
        page_size=2, poison=False, resume=lambda: None,
    )
""")
    result = pytester.runpytest_subprocess("-q", "--tb=short")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*AssertionError: receipts: healthy recovery control did not progress*",
            "*Recovery diagnostics:*",
            '*"stage": "control"*',
            '*"ticks": 2*',
            '*"identity": "3"*',
            '*"owed": true*',
        ]
    )
