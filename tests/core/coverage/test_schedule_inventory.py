import ast
from collections.abc import Callable, Mapping
from datetime import timedelta
from pathlib import Path
from textwrap import dedent, indent
from typing import NotRequired, TypedDict

import pytest

from pytest_obligation.coverage._internal.schedules import (
    _Callable,
    _declared_stale_after,
    _early_return,
    _function_index,
    _per_row_loop,
    _task_definitions,
    _tick_opener,
    _tick_problem,
    _ticks_somewhere,
)
from pytest_obligation.coverage.config import CoverageConfig
from pytest_obligation.coverage.project import Project
from pytest_obligation.coverage.schedules import RecoveryTick, Sweep


class ScheduleArguments(TypedDict):
    project: Project
    schedule: Mapping[str, str]
    sweeps: Mapping[str, Sweep]
    intervals: Mapping[str, timedelta]
    default_stale_after: timedelta
    reviewed_grandfathered: NotRequired[frozenset[str]]
    task_names: NotRequired[Mapping[str, str]]


DEFAULT_STALE_AFTER = timedelta(minutes=10)


def project(root: Path) -> Project:
    return Project(CoverageConfig(root=root, production_packages=("shop",), source_roots=(".",)))


def _write(base: Path, relative: str, source: str) -> None:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")


def test_task_names_resolve_pinned_names_and_imported_constants(tmp_path: Path) -> None:
    _write(tmp_path, "shop/app/names.py", 'PROBE_TASK = "shop.app.legacy.probe"\n')
    _write(
        tmp_path,
        "shop/app/tasks/sweeps.py",
        """
        from celery import shared_task
        from shop.app.names import PROBE_TASK

        PINNED = "shop.app.tasks.pinned_sweep"

        @shared_task
        def plain():
            pass

        @shared_task(bind=True, name="shop.app.tasks.renamed")
        def renamed(self):
            pass

        @shared_task(name=PINNED)
        def pinned_sweep():
            pass

        @shared_task(name=PROBE_TASK)
        def probe():
            pass
        """,
    )
    tasks = _task_definitions(project=project(tmp_path))
    assert {name: task.path for name, task in tasks.items()} == {
        "shop.app.tasks.sweeps.plain": "shop.app.tasks.sweeps.plain",
        "shop.app.tasks.renamed": "shop.app.tasks.sweeps.renamed",
        "shop.app.tasks.pinned_sweep": "shop.app.tasks.sweeps.pinned_sweep",
        "shop.app.legacy.probe": "shop.app.tasks.sweeps.probe",
    }


@pytest.mark.parametrize("bind_name", [False, True])
def test_configured_task_name_requires_an_explicit_production_binding(tmp_path: Path, bind_name: bool) -> None:
    from pytest_obligation.coverage.schedules import NoPerRowLoop, assert_schedule_contract

    _write(
        tmp_path,
        "shop/tasks.py",
        """
        from celery import shared_task
        from django.conf import settings

        @shared_task(name=settings.WORK_TASK_NAME)
        def run():
            pass
        """,
    )
    arguments: ScheduleArguments = dict(
        project=project(tmp_path),
        schedule={"daily": "legacy.work"},
        sweeps={"legacy.work": NoPerRowLoop(reason="One operation; no per-row recovery loop.")},
        intervals={"legacy.work": timedelta(days=1)},
        default_stale_after=DEFAULT_STALE_AFTER,
        task_names={"shop.tasks.run": "legacy.work"} if bind_name else {},
    )
    if bind_name:
        assert_schedule_contract(**arguments)
    else:
        with pytest.raises(AssertionError, match="a task name must be a literal or a named constant"):
            assert_schedule_contract(**arguments)


def _sweep_tree(base: Path, sweep_body: str) -> dict[str, _Callable]:
    """A task that calls ``SweepService.sweep``, whose body is given, beside a method that does open a tick."""
    lines = [
        "from shop.core.shared.durable_work.runtime.recovery_pass import recovery_tick",
        "",
        "class SweepService:",
        "    @staticmethod",
        "    def sweep():",
        indent(dedent(sweep_body).strip(), " " * 8),
        "",
        "    @staticmethod",
        "    def other():",
        "        with recovery_tick('app.other'):",
        "            pass",
    ]
    _write(base, "shop/app/services.py", "\n".join(lines) + "\n")
    _write(
        base,
        "shop/app/tasks.py",
        """
        from celery import shared_task

        @shared_task
        def run_sweep():
            from shop.app.services import SweepService

            SweepService.sweep()
        """,
    )
    return _task_definitions(project=project(base))


def test_a_tick_opened_in_the_named_callable_is_accepted(tmp_path: Path) -> None:
    tasks = _sweep_tree(
        tmp_path,
        """
        with recovery_tick("app.sweep") as recovery:
            for row in rows():
                with recovery.isolate(phase, row):
                    step(row)
        """,
    )
    tick = RecoveryTick(via=("shop.app.services.SweepService.sweep",))
    assert _tick_problem(tasks["shop.app.tasks.run_sweep"], tick, project=project(tmp_path)) is None


def test_a_stale_threshold_is_read_from_the_tick_call(tmp_path: Path) -> None:
    tasks = _sweep_tree(
        tmp_path,
        """
        with recovery_tick("app.sweep", stale_after=timedelta(days=2)) as recovery:
            pass
        with recovery_tick("app.hint", heartbeat=False) as hint:
            pass
        """,
    )
    opener = _tick_opener(
        tasks["shop.app.tasks.run_sweep"],
        RecoveryTick(via=("shop.app.services.SweepService.sweep",)),
        project=project(tmp_path),
    )
    assert not isinstance(opener, str)
    # The standalone loop publishes no threshold, so only the heartbeat tick's counts.
    assert _declared_stale_after(opener, DEFAULT_STALE_AFTER) == {timedelta(days=2)}


def test_a_tick_without_a_stale_threshold_has_the_default_and_a_computed_one_is_reported(tmp_path: Path) -> None:
    tasks = _sweep_tree(
        tmp_path,
        """
        with recovery_tick("app.sweep") as recovery:
            pass
        with recovery_tick("app.sweep", stale_after=DAILY * 2) as recovery:
            pass
        """,
    )
    opener = _tick_opener(
        tasks["shop.app.tasks.run_sweep"],
        RecoveryTick(via=("shop.app.services.SweepService.sweep",)),
        project=project(tmp_path),
    )
    assert not isinstance(opener, str)
    assert _declared_stale_after(opener, DEFAULT_STALE_AFTER) == {DEFAULT_STALE_AFTER, "DAILY * 2"}


def test_a_return_before_the_tick_is_found_in_the_opener_and_the_task(tmp_path: Path) -> None:
    tasks = _sweep_tree(
        tmp_path,
        """
        rows = list(pending())
        if not rows:
            return
        with recovery_tick("app.sweep") as recovery:
            pass
        """,
    )
    task = tasks["shop.app.tasks.run_sweep"]
    tick = RecoveryTick(via=("shop.app.services.SweepService.sweep",))
    assert _early_return(task, tick, project=project(tmp_path)) == (
        "shop.app.services.SweepService.sweep returns at line 8, before it reaches the tick"
    )


def test_a_return_inside_the_tick_or_a_nested_function_is_not_early(tmp_path: Path) -> None:
    tasks = _sweep_tree(
        tmp_path,
        """
        def unrelated():
            return 1
        with recovery_tick("app.sweep") as recovery:
            if not rows():
                return
        """,
    )
    tick = RecoveryTick(via=("shop.app.services.SweepService.sweep",))
    assert _early_return(tasks["shop.app.tasks.run_sweep"], tick, project=project(tmp_path)) is None


def test_a_tick_opened_through_a_helper_counts_as_ticking(tmp_path: Path) -> None:
    # The task calls SweepService.sweep, which calls SweepService.other, which opens a tick.
    tasks = _sweep_tree(tmp_path, "SweepService.other()")
    index = _function_index(project=project(tmp_path))
    assert _ticks_somewhere(tasks["shop.app.tasks.run_sweep"], index)
    quiet = _sweep_tree(tmp_path / "quiet", "pass")
    # other() still opens a tick, but nothing reaches it from the task.
    assert not _ticks_somewhere(quiet["shop.app.tasks.run_sweep"], _function_index(project=project(tmp_path / "quiet")))


def test_a_tick_claim_without_the_call_is_refused(tmp_path: Path) -> None:
    """A comment, another method's tick, or the module importing recovery_tick is not the named callable opening one."""
    tasks = _sweep_tree(
        tmp_path,
        """
        # recovery_tick("app.sweep") would go here
        for row in rows():
            step(row)
        """,
    )
    task = tasks["shop.app.tasks.run_sweep"]
    tick = RecoveryTick(via=("shop.app.services.SweepService.sweep",))
    assert _tick_problem(task, tick, project=project(tmp_path)) == (
        "shop.app.services.SweepService.sweep does not call recovery_tick(...)"
    )
    # The task never reaches the callable that does open one.
    other = RecoveryTick(via=("shop.app.services.SweepService.other",))
    assert _tick_problem(task, other, project=project(tmp_path)) == (
        "shop.app.tasks.run_sweep never calls shop.app.services.SweepService.other"
    )
    assert _tick_problem(task, RecoveryTick(), project=project(tmp_path)) == (
        "shop.app.tasks.run_sweep does not call recovery_tick(...)"
    )
    missing = RecoveryTick(via=("shop.app.services.SweepService.gone",))
    assert _tick_problem(task, missing, project=project(tmp_path)) == (
        "via names shop.app.services.SweepService.gone, which is no production function"
    )


def test_a_loop_over_a_call_contradicts_no_per_row_loop() -> None:
    def task_of(source: str) -> _Callable:
        node = ast.parse(dedent(source)).body[0]
        assert isinstance(node, ast.FunctionDef)
        return _Callable("app.tasks.task", node)

    assert _per_row_loop(task_of("def task():\n    return Model.objects.count()\n")) is None
    assert _per_row_loop(task_of("def task():\n    ids = [row.id for row in rows]\n")) is None
    assert _per_row_loop(task_of("def task():\n    for room in rooms():\n        publish.delay(room)\n")) == 2
    assert _per_row_loop(task_of("def task():\n    return [step(row) for row in rows]\n")) == 2


def test_complete_inventory_rejects_changed_schedule_and_policy(tmp_path: Path) -> None:
    import pytest

    from pytest_obligation.coverage.schedules import Grandfathered, NoPerRowLoop, assert_schedule_contract

    _sweep_tree(
        tmp_path,
        """
        with recovery_tick("app.sweep", stale_after=timedelta(minutes=20)):
            pass
    """,
    )
    task = "shop.app.tasks.run_sweep"
    kwargs: ScheduleArguments = dict(
        project=project(tmp_path),
        schedule={"regular": task},
        sweeps={task: RecoveryTick(via=("shop.app.services.SweepService.sweep",))},
        intervals={task: timedelta(minutes=10)},
        default_stale_after=DEFAULT_STALE_AFTER,
    )
    assert_schedule_contract(**kwargs)
    mutants: list[tuple[Callable[[ScheduleArguments], None], str]] = [
        (lambda p: p.update(schedule={"new": "shop.app.missing"}), "unclassified"),
        (lambda p: p.update(intervals={task: timedelta(hours=1)}), "stale_after"),
        (lambda p: p.update(sweeps={task: Grandfathered(reason="an older task awaiting conversion")}), "grandfathered"),
        (
            lambda p: p.update(sweeps={task: NoPerRowLoop(reason="runs no application code per row")}),
            "reaches recovery_tick",
        ),
        (
            lambda p: p.update(
                sweeps={
                    task: RecoveryTick(
                        via=("shop.app.services.SweepService.sweep",), returns_before_tick="feature gate"
                    )
                }
            ),
            "stale early-return",
        ),
        (lambda p: p.update(reviewed_grandfathered=frozenset({task})), "stale grandfathered"),
        (lambda p: p.update(intervals={}), "missing interval"),
    ]
    for mutate, message in mutants:
        changed = kwargs.copy()
        mutate(changed)
        with pytest.raises(AssertionError, match=message):
            assert_schedule_contract(**changed)


def test_inventory_refuses_a_loop_claim_and_early_idle_return(tmp_path: Path) -> None:
    import pytest

    from pytest_obligation.coverage.schedules import NoPerRowLoop, assert_schedule_contract

    _write(
        tmp_path,
        "shop/tasks.py",
        """
        from celery import shared_task
        @shared_task
        def run():
            for row in rows():
                send(row)
    """,
    )
    with pytest.raises(AssertionError, match="loops over a call"):
        assert_schedule_contract(
            project(tmp_path),
            {"entry": "shop.tasks.run"},
            {"shop.tasks.run": NoPerRowLoop(reason="only a database aggregation")},
            intervals={},
            default_stale_after=DEFAULT_STALE_AFTER,
        )
    _sweep_tree(tmp_path / "early", 'if idle():\n    return\nwith recovery_tick("work"):\n    pass')
    with pytest.raises(AssertionError, match="before it reaches"):
        assert_schedule_contract(
            project(tmp_path / "early"),
            {"e": "shop.app.tasks.run_sweep"},
            {"shop.app.tasks.run_sweep": RecoveryTick(via=("shop.app.services.SweepService.sweep",))},
            intervals={"shop.app.tasks.run_sweep": timedelta(minutes=1)},
            default_stale_after=DEFAULT_STALE_AFTER,
        )
