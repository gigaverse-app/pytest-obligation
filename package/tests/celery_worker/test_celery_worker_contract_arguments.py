"""
A Celery worker contract binds its histories as ObligationContract does (process_handoffs=, handoff_gaps=).

The one-history form (history=, gap=) is deprecated: it still binds, and warns. Building a history
starts no worker, so these run anywhere.
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


def test_histories_and_their_gaps_are_the_contracts_own() -> None:
    contract = worker_contract(name="several", process_handoffs=(TASK, CHORD), handoff_gaps={"a chord": "it diverges"})
    assert contract.process_handoffs == (TASK, CHORD)
    assert contract.handoff_gaps == {"a chord": "it diverges"}


def test_the_deprecated_one_history_form_still_binds_and_warns() -> None:
    with pytest.warns(DeprecationWarning, match=r"process_handoffs=\(history,\)"):
        contract = worker_contract(name="one", history=TASK, gap="it diverges")
    assert contract.process_handoffs == (TASK,)
    assert contract.handoff_gaps == {"a task": "it diverges"}


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"history": TASK, "process_handoffs": (CHORD,)}, "not both"),
        ({"history": TASK, "handoff_gaps": {"a task": "it diverges"}}, "not both"),
        ({"process_handoffs": (TASK,), "gap": "it diverges"}, "declare gaps in handoff_gaps"),
        ({}, "at least one history"),
    ],
    ids=["history-and-process-handoffs", "history-and-handoff-gaps", "gap-without-history", "none"],
)
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_a_mixed_binding_is_refused_in_words(arguments: dict[str, object], refusal: str) -> None:
    with pytest.raises(AssertionError, match=refusal):
        worker_contract(name="refused", **arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"process_handoffs": (TASK, history("a task"))}, "handoff history names must be unique"),
        ({"process_handoffs": (TASK,), "handoff_gaps": {"a chain": "it diverges"}}, "handoff_gaps name no declared"),
    ],
    ids=["same-name", "unknown-gap"],
)
def test_the_contracts_own_design_checks_cover_several_histories(arguments: dict[str, object], refusal: str) -> None:
    with pytest.raises(ObligationContractDesignError, match=refusal):
        worker_contract(name="refused", **arguments)  # type: ignore[arg-type]
