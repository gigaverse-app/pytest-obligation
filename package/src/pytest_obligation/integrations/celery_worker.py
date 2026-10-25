"""
Celery worker integration: the application's real worker in a child process, failing at Celery's own stages.

A Celery worker runs each task in a pool child: the tracer runs the body,
publishes the task's links, stores its result, runs its hooks, and the parent
acknowledges the message. A test cannot die inside a pool child in process, so
these histories run the application's real worker, ``celery worker`` with the
prefork pool, as a child process of the test, and tell it where to fail
(:mod:`pytest_obligation.process_histories`). Recovery is what production does
after any failure: the worker starting again.

The faults are Celery's, the same for every application, applied to the first
execution of one named task:

Deaths (the pool child ``os._exit``\\ s; the worker's main process lives on and
sees the child lost):

* ``task_prerun`` — as the task starts, before its body runs;
* ``mark_as_done`` — the body ran and its links were published; the result
  was not stored yet;
* ``task_postrun`` — the result was stored as SUCCESS; the parent has not heard.

The same three stages are available with the pool child killed by the kernel
instead, ``task_prerun (SIGKILL)`` and so on (:data:`SIGKILL_DEATH_POINTS`), as
the OOM killer or ``kill -9`` would. Billiard reports a signal death through its
own path ("signal 9 (SIGKILL)" rather than "exitcode 1"). They are opt-in: pass
``death_points=DEATH_POINTS + SIGKILL_DEATH_POINTS``.

Failures the worker survives:

* ``the task's on_success hook raised`` — the ``Task.on_success`` hook raises
  instead of running, as a hook with a bug or an unreachable service would;
* ``the broker refused the task's link`` — the first signature the task's
  execution publishes (a link, a chain's next step) is refused with kombu's
  ``OperationalError``, as a broker that is down would.

And one real refusal, opt-in because it needs a Redis server of its own:

* ``the Redis broker was full`` (:data:`BROKER_FULL`) — once the task's body
  has run on its first execution, the broker's Redis server is set to
  ``maxmemory 1`` with ``noeviction``, so Redis itself refuses the writes that
  follow (the link's publish among them) and kombu raises its
  ``OperationalError``. ``maxmemory`` is server-wide, so the broker must not
  share its server with the result backend or anything the test reads. The
  test process restores the server once the run settles, or fails, before
  recovery starts. It needs ``broker_url`` and a server that allows ``CONFIG``.

:func:`worker_history` builds the process history; its observation is the
adopter's, typically the task's result state with what its links and errbacks
did. Helpers import Celery only in the child. POSIX only (see :func:`running_worker`).
"""

import importlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

from pytest_obligation.contract import (
    Adoption,
    Decline,
    NotApplicable,
    ObligationContract,
    Profile,
)
from pytest_obligation.crash_histories import Findings
from pytest_obligation.helpers import wait_until
from pytest_obligation.integrations.task_queues import (
    application_admission,
    application_gate,
    replay_safety_is_the_functions,
    settled_by_one_worker,
    the_obligation_is_the,
)
from pytest_obligation.process_histories import (
    FAULT_VARIABLE,
    ProcessHistory,
    fault_environment,
    fault_fires,
    fault_happened,
)

#: Where the pool child dies, exiting with ``os._exit(1)``: what every history runs by default.
DEATH_POINTS = ("task_prerun", "mark_as_done", "task_postrun")
_SIGKILL = " (SIGKILL)"
#: The same stages, the pool child killed by the kernel with SIGKILL, as the OOM killer would. Opt-in.
SIGKILL_DEATH_POINTS = tuple(f"{point}{_SIGKILL}" for point in DEATH_POINTS)
#: What fails while the worker lives on.
FAILURE_POINTS = ("the task's on_success hook raised", "the broker refused the task's link")
#: Opt-in: the broker's own Redis server refuses writes after the task's body ran. Needs ``broker_url``.
BROKER_FULL = "the Redis broker was full"

#: Which task the child fails; the fault itself travels in process_histories' protocol.
_TASK = "DUE_WORK_CELERY_TASK"


@contextmanager
def running_worker(
    app: str,
    *,
    fault: str | None = None,
    task: str | None = None,
    marker: Path | None = None,
    env: Mapping[str, str] | None = None,
    log: Path | None = None,
    worker_args: Sequence[str] = (),
) -> Iterator[subprocess.Popen[bytes]]:
    """
    The application's worker, ``celery worker`` with one prefork child, running for the block.

    ``app`` is the Celery application as ``module:attribute``. When ``fault``
    names a death or failure point, the first execution of ``task`` fails there
    and ``marker`` is created. On exit the worker gets a warm shutdown, as a
    deploy would, and is killed if it does not stop.

    POSIX only: the fault is installed in the worker's main process and reaches
    its pool child through ``fork``, and the warm shutdown is ``SIGTERM``.
    """
    assert sys.platform != "win32", (
        "the Celery worker histories need Celery's prefork pool, which does not run on Windows: billiard "
        "spawns the pool child, which inherits neither the fault installed in the worker's main process nor "
        "usable pool semaphores, so the task never settles. Run these histories on Linux or macOS"
    )
    environ = {**os.environ, **(env or {}), **fault_environment(fault, marker), _TASK: task or ""}
    output = open(log, "ab") if log is not None else subprocess.DEVNULL  # noqa: SIM115 - closed below
    command = [sys.executable, "-m", "pytest_obligation.integrations.celery_worker", app, *worker_args]
    process = subprocess.Popen(command, env=environ, stdout=output, stderr=subprocess.STDOUT)
    try:
        yield process
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if log is not None and not isinstance(output, int):
            output.close()


HandleT = TypeVar("HandleT")
ObservationT = TypeVar("ObservationT")


def worker_history(
    *,
    name: str,
    app: str,
    task: str,
    send: Callable[[], HandleT],
    observe: Callable[[HandleT], ObservationT],
    initial: ObservationT,
    expected: ObservationT | Callable[[HandleT], ObservationT],
    settled: Callable[[HandleT], bool],
    death_points: Sequence[str] = DEATH_POINTS,
    failure_points: Sequence[str] = FAILURE_POINTS,
    quiet: float = 1.0,
    timeout: float = 60.0,
    env: Mapping[str, str] | None = None,
    log: Path | None = None,
    findings: Findings | None = None,
    broker_url: str | None = None,
) -> ProcessHistory[HandleT, ObservationT]:
    """
    One task through the application's real worker, failing at each of Celery's stages, recovered by a restart.

    ``send`` publishes the task (with its links and error callbacks) and returns
    what ``observe`` reads. ``settled`` says when the work it started is done;
    each run then waits ``quiet`` seconds more for anything it published late.
    A run reports status 1 when its fault happened, so a stage the task never
    reached is caught as a history that was never interrupted. ``broker_url``
    is the worker's Redis broker, which :data:`BROKER_FULL` fills and the test
    process restores.
    """
    deaths, failures = DEATH_POINTS + SIGKILL_DEATH_POINTS, (*FAILURE_POINTS, BROKER_FULL)
    unknown = set(death_points) - set(deaths) | set(failure_points) - set(failures)
    assert not unknown, f"{name}: no such Celery fault {sorted(unknown)}; the faults are {deaths + failures}"
    if BROKER_FULL in failure_points:
        assert broker_url is not None and urlsplit(broker_url).scheme in ("redis", "rediss"), (
            f"{name}: {BROKER_FULL!r} fills the broker's own Redis server, so it needs broker_url= naming a Redis "
            f"broker the test process can restore, on a server shared with nothing else; got {broker_url!r}"
        )

    def run(fault: str | None) -> tuple[HandleT, int]:
        with tempfile.TemporaryDirectory() as scratch:
            marker = Path(scratch) / "fault"
            with running_worker(app, fault=fault, task=task, marker=marker, env=env, log=log):
                # The broker is restored before the worker stops, whether the run settles or not.
                with broker_restored(broker_url) if fault == BROKER_FULL and broker_url else nullcontext():
                    handle = send()
                    wait_until(lambda: settled(handle), timeout=timeout, what=f"{name}: the task did not settle")
                    time.sleep(quiet)
            happened = fault_happened(marker)
        return handle, 0 if fault is None else int(happened)

    def recover(handle: HandleT) -> None:
        # REAL PRODUCTION: the worker starting again, then running until the work is settled.
        with running_worker(app, env=env, log=log):
            wait_until(lambda: settled(handle), timeout=timeout, what=f"{name}: recovery did not settle")
            time.sleep(quiet)

    return ProcessHistory(
        name=name,
        initial=initial,
        expected=expected,
        run=run,
        observe=observe,
        recover=recover,
        death_points=tuple(death_points),
        failure_points=tuple(failure_points),
        findings=findings,
    )


def broker_restored(broker_url: str) -> AbstractContextManager[None]:
    """
    TEST PROCESS: the broker's Redis server put back as it was when the block exits, however it exits.

    Reads ``maxmemory`` and ``maxmemory-policy`` before the block and sets them
    back after it, so the :data:`BROKER_FULL` fault never outlives its run.
    """
    import redis

    @contextmanager
    def restoring() -> Iterator[None]:
        server = redis.Redis.from_url(broker_url, decode_responses=True)
        try:
            saved = {key: str(server.config_get(key)[key]) for key in ("maxmemory", "maxmemory-policy")}
        except redis.ResponseError as error:
            raise AssertionError(
                f"{BROKER_FULL!r} sets maxmemory on the broker's Redis server, which refused CONFIG ({error}); "
                "run it against a Redis server you administer"
            ) from error
        try:
            yield
        finally:
            for key, value in saved.items():
                server.config_set(key, value)

    return restoring()


#: What Celery's worker does not promise, for any adopter's contract.
BROKER_REDELIVERS = (
    "Celery keeps no owed state of its own to sweep: a message the worker did not acknowledge is the broker's to "
    "redeliver (task_acks_late), and one it did acknowledge is settled"
)
BROKER_OWNS_LEASES = (
    "a task's lease is the broker's visibility timeout or connection, not a fenced claim Celery can check"
)
AT_LEAST_ONCE = "with task_acks_late a task whose worker died may run again; whether it reached its service is its own"
RESULTS_ARE_NOT_OWED = "stored results are the record of settled work, not work still owed"


def worker_contract(
    *,
    name: str,
    history: ProcessHistory[Any, Any] | None = None,
    gap: str | None = None,
    histories: Sequence[ProcessHistory[Any, Any]] = (),
    handoff_gaps: Mapping[str, str] | None = None,
    fixtures: tuple[str, ...] = (),
) -> ObligationContract:
    """
    Celery's contract with its worker: the adopter's work through the real worker, failing at each of Celery's stages.

    ``history`` is :func:`worker_history` for one of the adopter's tasks, a
    process handoff of the contract, and what it finds is declared as ``gap``,
    a strict xfail. To bind several (a task, a chain, a chord), pass them as
    ``histories`` instead, with ``handoff_gaps`` declaring each one's gap by
    history name, as RQ's ``worker_contract`` does. When a history carries its
    ``findings``, they are pinned history by history in the same run. The
    profiles Celery leaves to the broker or to the task are declined with the
    reason.
    """
    if history is not None:
        assert not histories and handoff_gaps is None, (
            f"{name}: bind one history with history= and gap=, or several with histories= and handoff_gaps=, not both"
        )
        histories = (history,)
        handoff_gaps = {history.name: gap} if gap is not None else {}
    else:
        assert gap is None, f"{name}: gap= declares history='s gap; with histories=, declare each in handoff_gaps="
    assert histories, f"{name}: a Celery worker contract binds at least one history"
    names = [each.name for each in histories]
    assert len(set(names)) == len(names), f"{name}: two histories share a name: {sorted(names)}"
    handoff_gaps = dict(handoff_gaps or {})
    unknown = handoff_gaps.keys() - set(names)
    assert not unknown, f"{name}: handoff_gaps name no bound history: {sorted(unknown)}; the histories are {names}"
    return ObligationContract(
        name=name,
        adoption=Adoption.LEGACY,
        profiles={
            Profile.A: Decline(BROKER_REDELIVERS),
            Profile.B: Decline(BROKER_OWNS_LEASES),
            Profile.C: Decline(AT_LEAST_ONCE),
            Profile.D: NotApplicable(RESULTS_ARE_NOT_OWED),
            Profile.E: settled_by_one_worker("delivery"),
            Profile.F: the_obligation_is_the("message"),
            Profile.H: replay_safety_is_the_functions(
                "task", "Celery", runs_again="with task_acks_late, a redelivery after its worker was lost"
            ),
            Profile.J: Decline(
                "a task's retries are its own (self.retry, autoretry_for); a redelivery after a lost worker is "
                "not counted as one"
            ),
            Profile.G: application_gate("Celery"),
            Profile.I: application_admission("Celery"),
        },
        process_handoffs=tuple(histories),
        handoff_gaps=handoff_gaps,
        fixtures=fixtures,
    )


def _install(app: Any, fault: str, task: str) -> None:
    """FAULT INJECTION, in the worker process before it forks its pool."""
    from celery import signals
    from celery.canvas import Signature
    from kombu.exceptions import OperationalError

    from pytest_obligation.worker_death import ReceiverFailed

    def ours(name: str | None) -> bool:
        return name == task and fault_fires(fault)

    stage = fault.removesuffix(_SIGKILL)

    def die() -> None:
        if stage != fault:
            # The kernel kills the child, as the OOM killer would: billiard sees signal 9, not an exit status.
            os.kill(os.getpid(), signal.SIGKILL)
        os._exit(1)

    if stage == "task_prerun":

        def die_at_start(sender: Any = None, **_kwargs: Any) -> None:
            if ours(getattr(sender, "name", None)):
                die()

        signals.task_prerun.connect(die_at_start, weak=False)
    elif stage == "task_postrun":

        def die_after_store(sender: Any = None, **_kwargs: Any) -> None:
            if ours(getattr(sender, "name", None)):
                die()

        signals.task_postrun.connect(die_after_store, weak=False)
    elif stage == "mark_as_done":
        backend_class = type(app.backend)
        store = backend_class.mark_as_done

        def die_before_store(
            self: Any, task_id: str, result: Any, request: Any = None, *args: Any, **kwargs: Any
        ) -> Any:
            if ours(getattr(request, "task", None)):
                die()
            return store(self, task_id, result, request, *args, **kwargs)

        backend_class.mark_as_done = die_before_store
    elif fault == "the task's on_success hook raised":
        target = app.tasks[task]

        def on_success(*_args: Any, **_kwargs: Any) -> None:
            if fault_fires(fault):
                raise ReceiverFailed(f"the on_success hook of {task} failed")

        type(target).on_success = on_success
    elif fault == "the broker refused the task's link":
        publish = Signature.apply_async

        def refusing(self: Any, *args: Any, **kwargs: Any) -> Any:
            if self.task != task and fault_fires(fault):
                raise OperationalError(f"the broker refused {self.task}: [Errno 111] Connection refused")
            return publish(self, *args, **kwargs)

        Signature.apply_async = refusing
    elif fault == BROKER_FULL:
        import redis

        broker = app.connection_for_write().as_uri(include_password=True)
        assert urlsplit(broker).scheme in ("redis", "rediss"), (
            f"{BROKER_FULL!r} needs a Redis broker; this worker's broker is {urlsplit(broker).scheme}://"
        )
        target = app.tasks[task]
        body = target.run

        def run_then_fill_the_broker(*args: Any, **kwargs: Any) -> Any:
            result = body(*args, **kwargs)
            if fault_fires(fault):
                # REAL FAILURE: from here Redis itself refuses the broker's writes, the link's publish among them.
                server = redis.Redis.from_url(broker)
                server.config_set("maxmemory-policy", "noeviction")
                server.config_set("maxmemory", 1)
            return result

        # The tracer calls task.run; an instance attribute shadows the task class's own.
        target.run = run_then_fill_the_broker
    else:
        raise AssertionError(f"no such Celery fault {fault!r}")


def main(argv: Sequence[str]) -> None:
    """The child: import the application, install its one fault, run its worker."""
    module, _, attribute = argv[0].partition(":")
    app = getattr(importlib.import_module(module), attribute or "app")
    fault = os.environ.get(FAULT_VARIABLE, "")
    if fault:
        _install(app, fault, os.environ[_TASK])
    app.worker_main(
        [
            "worker",
            "--pool=prefork",
            "--concurrency=1",
            "--loglevel=WARNING",
            "--without-mingle",
            "--without-gossip",
            "--without-heartbeat",
            *argv[1:],
        ]
    )


if __name__ == "__main__":
    main(sys.argv[1:])


__all__ = [
    "AT_LEAST_ONCE",
    "BROKER_FULL",
    "BROKER_OWNS_LEASES",
    "BROKER_REDELIVERS",
    "DEATH_POINTS",
    "FAILURE_POINTS",
    "RESULTS_ARE_NOT_OWED",
    "SIGKILL_DEATH_POINTS",
    "broker_restored",
    "running_worker",
    "wait_until",
    "worker_contract",
    "worker_history",
]
