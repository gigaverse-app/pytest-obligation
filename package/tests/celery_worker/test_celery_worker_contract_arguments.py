"""
A Celery worker contract binds one history (history=, gap=) or several (histories=, handoff_gaps=).

Building a history starts no worker, so these run anywhere.
"""

import pytest

from pytest_obligation.contract import ObligationContractDesignError
from pytest_obligation.integrations.celery_worker import worker_contract, worker_history
from pytest_obligation.process_histories import ProcessHistory


def history(name: str) -> ProcessHistory[str, str]:
    return worker_history(
        name=name,
        app="any:app",
        task="any.task",
        send=lambda: "task id",
        observe=lambda _task_id: "done",
        initial="pending",
        expected="done",
        settled=lambda _task_id: True,
    )


TASK = history("a task")
CHORD = history("a chord")


def test_one_history_and_its_gap() -> None:
    contract = worker_contract(name="one", history=TASK, gap="it diverges")
    assert contract.process_handoffs == (TASK,)
    assert contract.handoff_gaps == {"a task": "it diverges"}


def test_several_histories_each_with_its_own_gap() -> None:
    contract = worker_contract(name="several", histories=(TASK, CHORD), handoff_gaps={"a chord": "it diverges"})
    assert contract.process_handoffs == (TASK, CHORD)
    assert contract.handoff_gaps == {"a chord": "it diverges"}


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"history": TASK, "histories": (CHORD,)}, "not both"),
        ({"history": TASK, "handoff_gaps": {"a task": "it diverges"}}, "not both"),
        ({"histories": (TASK,), "gap": "it diverges"}, "declare each in handoff_gaps"),
        ({}, "at least one history"),
    ],
    ids=["history-and-histories", "history-and-handoff-gaps", "gap-with-histories", "none"],
)
def test_an_ambiguous_binding_is_refused_in_words(arguments: dict[str, object], refusal: str) -> None:
    with pytest.raises(AssertionError, match=refusal):
        worker_contract(name="refused", **arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"histories": (TASK, history("a task"))}, "handoff history names must be unique"),
        ({"histories": (TASK,), "handoff_gaps": {"a chain": "it diverges"}}, "handoff_gaps name no declared handoff"),
    ],
    ids=["same-name", "unknown-gap"],
)
def test_the_contracts_own_design_checks_cover_several_histories(arguments: dict[str, object], refusal: str) -> None:
    with pytest.raises(ObligationContractDesignError, match=refusal):
        worker_contract(name="refused", **arguments)  # type: ignore[arg-type]
