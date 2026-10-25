"""
Generated failure tests for an application's own Celery task, through the real worker.

:mod:`pytest_obligation.integrations.celery_worker` runs a ``celery worker``
and fails it at each of Celery's stages: the pool child lost as the task starts,
after its body ran, or after its result was stored; the task's ``on_success``
hook raising; the broker refusing what the task publishes. Then the worker
starts again, as a deployment would, and what is left is compared with a
normal run.

:func:`task_contract` is the application's way in. The application supplies
what only it knows: how its own code sends the task, how to see what the task
did, and what that should be after one run. This module supplies what Celery
does at each stage for the task's configuration (``acks_late``,
``reject_on_worker_lost``, ``ignore_result``), declared as a strict expected
failure, so the test passes while Celery behaves that way and fails if Celery
changes. Anything else the task does, such as a second email when
``reject_on_worker_lost`` runs it again after its body ran, fails the test::

    from pytest_obligation import due_work_contract_suite
    from pytest_obligation.integrations.celery_tasks import task_contract

    WELCOME = task_contract(
        "myapp.celery:app",
        send_welcome_email,
        send=lambda: sign_up(f"{uuid4()}@example.com"),
        effect=lambda result: outbox.count(result.args[0]),
        expected_effect=1,
    )


    @due_work_contract_suite(WELCOME)
    class TestWelcomeEmail:
        pass

When the application recovers what Celery loses, with a recovery sweep its
beat schedule runs or a work table of its own, pass that sweep as
``recovery`` and say what it is with ``recovered_by``. Celery's rows are then
not declared: the application claims that every failure converges, and each
history checks it. Such work, and a task whose result is not kept
(``ignore_result``, or an application with no result backend), is observed
by its effect alone: its state reads :data:`UNOBSERVED`.

Needs a broker and result backend the test process can reach, the task's own
application importable by the worker, and Linux or macOS: the stages are
reached through the prefork pool.
"""

import importlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

from pytest_obligation.contract import ObligationContract
from pytest_obligation.crash_histories import Findings
from pytest_obligation.integrations.celery_worker import (
    DEATH_POINTS,
    FAILURE_POINTS,
    SIGKILL_DEATH_POINTS,
    worker_contract,
    worker_history,
)
from pytest_obligation.integrations.task_queues import TaskOutcome

HandleT = TypeVar("HandleT")

#: The state column when Celery's record is not part of the observation: the task does not keep its result
#: (``ignore_result``, or no result backend), or the application's own recovery owns the outcome.
UNOBSERVED = "not observed"

#: Celery's stages where it leaves a task differently from a normal run, by history label.
PRERUN, BEFORE_STORE = "died at task_prerun", "died at mark_as_done"
LINK_REFUSED = "the broker refused the task's link"
_ON_SUCCESS = "the task's on_success hook raised"
_SIGKILL = " (SIGKILL)"

NOT_RUN_AGAIN = (
    "with acks_late and reject_on_worker_lost not both set (Celery's default), a task whose pool child is lost is "
    "recorded FAILURE (WorkerLostError) and is not run again: lost as it starts, its effect never happens; lost "
    "after its body ran and before its result was stored, it is recorded FAILURE though its effect happened. Set "
    "both on the task to have it run again instead, and make the task safe to run twice"
)
LOST_UNRECORDED = (
    "with acks_late and reject_on_worker_lost not both set (Celery's default), a task whose pool child is lost as "
    "it starts is not run again, and as Celery keeps no result for it, nothing records that it was lost: its "
    "effect never happens. Set both on the task to have it run again instead, and make the task safe to run twice"
)
LINK_LOST = (
    "when the broker refuses the task's link, the task is recorded FAILURE though its effect happened, and the "
    "message is acknowledged, so the link is not sent again (https://github.com/celery/celery/issues/10725)"
)


def records_state(task: Any) -> bool:
    """Whether Celery keeps the task's outcome: it does not ignore its result, and its app has a result backend."""
    from celery.backends.base import DisabledBackend

    return not task.ignore_result and not isinstance(task.backend, DisabledBackend)


def runs_again(task: Any) -> bool:
    """Whether a task whose pool child is lost is requeued: ``acks_late`` with ``reject_on_worker_lost``."""
    return bool(task.acks_late and task.reject_on_worker_lost)


def celery_outcomes(
    task: Any,
    *,
    initial_effect: Any,
    expected_effect: Any,
    publishes: bool = False,
    sigkill: bool = False,
) -> dict[str, TaskOutcome]:
    """
    What Celery leaves ``task`` at each stage where that differs from a normal run, for its configuration.

    Keyed by history label. The task's effect either never happened
    (``initial_effect``) or happened once (``expected_effect``); its state is
    what Celery recorded, or :data:`UNOBSERVED`. Stages not listed reach a
    normal run, and a stage where the task runs twice is never listed: what a
    second run does belongs to the task.

    On a Celery without https://github.com/celery/celery/pull/10752 and
    https://github.com/celery/celery/pull/10759 (5.6 and earlier), a pool child
    lost after the result was stored, or an ``on_success`` that raises, also
    runs the task's error callbacks, and with ``reject_on_worker_lost`` runs the
    task again. The state stays SUCCESS, so those differences show only in an
    effect that observes them; they are not listed here
    (https://github.com/celery/celery/issues/10724).
    """
    state = "FAILURE" if records_state(task) else UNOBSERVED
    rows: dict[str, TaskOutcome] = {}
    if not runs_again(task):
        rows[PRERUN] = TaskOutcome(status=state, effect=initial_effect)
        rows[BEFORE_STORE] = TaskOutcome(status=state, effect=expected_effect)
    if sigkill:
        rows |= {f"{stage}{_SIGKILL}": outcome for stage, outcome in rows.items()}
    if publishes:
        rows[LINK_REFUSED] = TaskOutcome(status=state, effect=expected_effect)
    normal = TaskOutcome(status="SUCCESS" if records_state(task) else UNOBSERVED, effect=expected_effect)
    return {stage: outcome for stage, outcome in rows.items() if outcome != normal}


def _reasons(rows: Mapping[str, TaskOutcome]) -> list[str]:
    reasons = []
    deaths = [outcome for stage, outcome in rows.items() if stage.removesuffix(_SIGKILL) in (PRERUN, BEFORE_STORE)]
    if deaths:
        reasons.append(LOST_UNRECORDED if all(death.status == UNOBSERVED for death in deaths) else NOT_RUN_AGAIN)
    if LINK_REFUSED in rows:
        reasons.append(LINK_LOST)
    return reasons


def _resolve(app: str, task: Any) -> Any:
    """The task as the worker will import it, from the application the worker runs."""
    module, _, attribute = app.partition(":")
    application = getattr(importlib.import_module(module), attribute or "app")
    name = task if isinstance(task, str) else task.name
    assert name in application.tasks, (
        f"{app} has no task {name!r}: pass the task registered on the application the worker runs"
    )
    return application.tasks[name]


def task_contract(
    app: str,
    task: Any,
    *,
    send: Callable[[], HandleT],
    effect: Callable[[HandleT], Any],
    expected_effect: Any,
    initial_effect: Any = 0,
    recovery: Callable[[HandleT], object] | None = None,
    recovered_by: str | None = None,
    publishes: bool = False,
    known: Mapping[str, TaskOutcome] | None = None,
    because: str | None = None,
    sigkill: bool = False,
    settled: Callable[[HandleT], bool] | None = None,
    name: str | None = None,
    fixtures: tuple[str, ...] = (),
    transactional: bool = False,
    env: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
    worker_args: Sequence[str] = (),
    worker_setup: str | None = None,
    log: Path | None = None,
    quiet: float = 1.0,
    timeout: float = 60.0,
) -> ObligationContract:
    """
    Celery's contract with its worker, for one of the application's tasks.

    Arguments:
        app: The Celery application the worker runs, as ``"module:attribute"``.
            The worker imports it in a new process, so its configuration must
            not depend on anything only the test process sets; pass that as
            ``env``.
        task: The task to fail at each stage, or its registered name. For work
            that runs through a library's own task (a work table's runner, for
            example), name that task.
        send: The application's own code that sends the task, such as the view
            or service that calls ``.delay()``. Returns the handle that
            ``effect`` and ``recovery`` receive. When Celery keeps the task's
            outcome (:func:`records_state`) and no ``recovery`` is bound, the
            handle is the task's :class:`~celery.result.AsyncResult` or its id,
            and its state is observed too.
        effect: What the task did, read from the handle: how many emails
            reached this user, or a row's state with what it sent. Each history
            starts from a fresh effect, so ``send`` should use a new identity
            each time.
        expected_effect: ``effect`` after one successful run.
        initial_effect: ``effect`` before the task ran.
        recovery: What the application's deployment runs besides the worker to
            recover lost work, such as its recovery sweep, called once the
            worker has started again. With it, Celery's rows are not declared
            and its record is not observed: the effect must converge after
            every failure. Requires ``recovered_by``.
        recovered_by: What ``recovery`` is, for the contract's Profile A reason.
        publishes: The task's execution publishes another task (a link, a
            chain's next step, a chord body), so the broker can refuse it.
        known: The application's own known differences, by history label: what
            the task does that you cannot fix yet. Requires ``because``.
        because: Why the ``known`` differences exist, with a link to their issue.
        sigkill: Also lose the pool child at each stage by ``SIGKILL``, as the
            kernel's OOM killer would.
        settled: When the work is done; by default, when the worker is idle.
        fixtures: pytest fixtures every generated case requests.
        transactional: Run each case with real commits, so the worker, a
            separate process, sees the rows the test writes (a Django
            database, for example).
        env: Added to the worker's environment; a callable is called each time
            a worker starts, for values only a running test knows.
        worker_args: Passed to ``celery worker``, such as ``-Q`` and its queues.
        worker_setup: ``"module:function"`` the worker calls once it has loaded
            its tasks, to install the test doubles the task needs there (a
            fake provider, a filesystem storage): doubles installed in the test
            process do not reach the worker.

    The remaining arguments go to
    :func:`~pytest_obligation.integrations.celery_worker.worker_history`.
    """
    assert (known is None) == (because is None), "known= and because= go together: say why each difference exists"
    assert (recovery is None) == (recovered_by is None), (
        "recovery= and recovered_by= go together: say what recovers the work the worker loses"
    )
    target = _resolve(app, task)
    # With the application's own recovery, Celery's record of the first delivery is not the outcome.
    recorded = records_state(target) and recovery is None

    def observe(handle: HandleT) -> TaskOutcome:
        # OBSERVE: the state Celery recorded, and what the task did.
        return TaskOutcome(status=_state(target, handle) if recorded else UNOBSERVED, effect=effect(handle))

    rows = (
        {}
        if recovery is not None
        else celery_outcomes(
            target, initial_effect=initial_effect, expected_effect=expected_effect, publishes=publishes, sigkill=sigkill
        )
    )
    declared = {**rows, **(known or {})}
    expected = TaskOutcome(status="SUCCESS" if recorded else UNOBSERVED, effect=expected_effect)
    history = worker_history(
        name=name or f"a worker runs {target.name}",
        app=app,
        task=target.name,
        send=send,
        observe=observe,
        initial=TaskOutcome(status="PENDING" if recorded else UNOBSERVED, effect=initial_effect),
        expected=expected,
        settled=settled,
        death_points=DEATH_POINTS + (SIGKILL_DEATH_POINTS if sigkill else ()),
        failure_points=FAILURE_POINTS if publishes else (_ON_SUCCESS,),
        quiet=quiet,
        timeout=timeout,
        env=env,
        log=log,
        findings=Findings(expected, declared) if declared else None,
        worker_args=worker_args,
        recovery=recovery,
        worker_setup=worker_setup,
    )
    reasons = [*_reasons(rows), *([because] if because else [])]
    return worker_contract(
        name=f"celery: {history.name}",
        process_handoffs=(history,),
        handoff_gaps={history.name: "; ".join(reasons)} if declared else None,
        fixtures=fixtures,
        recovered_by=recovered_by,
        transactional=transactional,
    )


def _state(task: Any, handle: Any) -> str:
    from celery.result import AsyncResult

    assert isinstance(handle, (AsyncResult, str)), (
        f"{task.name} keeps its result, so send= returns its AsyncResult or task id; got {type(handle).__name__}"
    )
    return AsyncResult(handle if isinstance(handle, str) else handle.id, app=task.app).state


__all__ = [
    "LINK_LOST",
    "LOST_UNRECORDED",
    "NOT_RUN_AGAIN",
    "UNOBSERVED",
    "celery_outcomes",
    "records_state",
    "runs_again",
    "task_contract",
]
