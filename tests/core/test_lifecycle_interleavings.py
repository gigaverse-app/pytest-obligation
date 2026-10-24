"""Shared retirement/recreation histories must discriminate late writes and rollback loss."""

from functools import partial

import pytest

from pytest_obligation.interleavings import InFlightConvergence
from pytest_obligation.interleavings.engine.runner import replay_history
from pytest_obligation.interleavings.model import History, HistoryTrace, InterleavingFailure, Operation
from pytest_obligation.interleavings.testing.reference import reference


def lifecycle(
    *, forget: bool = False, forget_at: int = 0, lose_rollback: bool = False
) -> InFlightConvergence[int, str, str]:
    return InFlightConvergence(
        name="root-recreation",
        bind=partial(
            reference,
            inline_retirement=True,
            recreation=True,
            forget=forget,
            forget_at=forget_at,
            lose_rollback=lose_rollback,
        ),
        intents=("A", "B", "C"),
        seams=("write",),
        retirement=True,
        recreation=True,
        rejected_retirement_seams=("write",),
        repair_seams=("write",),
        no_independent_because="Independent authorities have separate root controls.",
        no_transport_because="This reference has no delivery transport.",
    )


@pytest.mark.parametrize("family", ["IF.recreate-before-completion", "IF.rejected-retirement"])
def test_recreation_histories_detect_lost_repair_and_replay(family: str) -> None:
    correct, broken = lifecycle(), lifecycle(forget=True)
    histories = [h for h in correct.histories() if family in h.families]
    assert histories
    for history in histories:
        correct.run(history)
        with pytest.raises(InterleavingFailure, match="convergence") as caught:
            broken.run(history)
        trace = HistoryTrace.model_validate_json(next(n for n in caught.value.__notes__ if n.startswith('{"version":')))
        with pytest.raises(InterleavingFailure, match="convergence"):
            replay_history(broken, trace)


def test_rejected_command_must_preserve_authority() -> None:
    broken = lifecycle(lose_rollback=True)
    history = next(h for h in broken.histories() if "IF.rejected-retirement" in h.families)
    with pytest.raises(InterleavingFailure, match="rejected-authority"):
        broken.run(history)


@pytest.mark.parametrize("max_steps", [11, 12, 40])
def test_recreation_exploration_preserves_budget_and_legal_lifecycles(max_steps: int) -> None:
    pytest.importorskip("hypothesis")
    from hypothesis import given, settings

    from pytest_obligation.interleavings.exploration.hypothesis import histories

    correct = lifecycle()

    @settings(max_examples=25, deadline=None, database=None, derandomize=True)
    @given(histories(correct, max_steps))
    def check(history: History) -> None:
        assert len(history.steps) <= max_steps
        assert any(s.operation == Operation.RECREATE for s in history.steps)
        correct.run(history)

    check()


def test_hypothesis_recreation_finds_later_cycle_defect() -> None:
    pytest.importorskip("hypothesis")
    from pytest_obligation.interleavings.exploration.hypothesis import explore

    broken = lifecycle(forget_at=6)
    # The fixed one-cycle regressions remain green; exploration must go deeper.
    for history in broken.histories():
        broken.run(history)
    with pytest.raises(InterleavingFailure) as caught:
        explore(broken, max_examples=35, max_steps=40)
    trace = HistoryTrace.model_validate_json(next(n for n in caught.value.__notes__ if n.startswith('{"version":')))
    with pytest.raises(InterleavingFailure):
        replay_history(broken, trace)


@pytest.mark.parametrize("field,value", [("retirement", False), ("recreation", False)])
def test_invalid_recreation_capabilities_are_rejected(field: str, value: bool) -> None:
    data = lifecycle().model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        InFlightConvergence(**data)
