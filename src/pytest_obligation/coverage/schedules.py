"""Static schedule classification and recovery-heartbeat checks.

Applications supply schedules, policy values and reviewed exemptions. The
analysis imports no task modules. Ported from the backend Beat inventory;
source shape checks are evidence of structure, not a runtime isolation proof.
"""

from collections.abc import Mapping
from datetime import timedelta

from pytest_obligation.coverage._internal.schedules import (
    _declared_stale_after,
    _early_return,
    _function_index,
    _per_row_loop,
    _task_definitions,
    _tick_opener,
    _ticks_somewhere,
)
from pytest_obligation.coverage.project import Project
from pytest_obligation.models import HarnessModel


class RecoveryTick(HarnessModel):
    """A task that reaches a heartbeat, optionally through a production call chain.

    ``via`` lists import-qualified callees in order. ``returns_before_tick`` is
    an application explanation for an intentional early return; stale explanations
    fail validation. This declaration provides structural, not execution, evidence.
    """

    via: tuple[str, ...] = ()
    returns_before_tick: str = ""


class GeneratedRecovery(HarnessModel):
    """The application's registered runtime owns this generated recovery task."""


class NoPerRowLoop(HarnessModel):
    """A scheduled action without a per-row loop, with a substantive product reason."""

    reason: str


class Grandfathered(HarnessModel):
    """Reviewed migration debt; its task must also appear in the exact allowlist."""

    reason: str


Sweep = RecoveryTick | GeneratedRecovery | NoPerRowLoop | Grandfathered


__all__ = ["RecoveryTick", "GeneratedRecovery", "NoPerRowLoop", "Grandfathered", "Sweep", "assert_schedule_contract"]


def assert_schedule_contract(
    project: Project,
    schedule: Mapping[str, str],
    sweeps: Mapping[str, Sweep],
    *,
    intervals: Mapping[str, timedelta],
    default_stale_after: timedelta,
    generated_recovery: Mapping[str, RecoveryTick] | None = None,
    reviewed_grandfathered: frozenset[str] = frozenset(),
) -> None:
    """Require every scheduled task's declared recovery structure and cadence.

    `schedule` maps entry names to registered task names. `intervals` maps static
    task names to their shortest cadence. Generated runtime tasks instead have
    their registry-owned cadence; their `via` chains are supplied explicitly.
    Application-owned reviewed lists are exact: growth and stale entries fail.
    """
    defined = _task_definitions(project)
    index = _function_index(project)
    problems = [*project.unparsable, *(f"hidden source: {path}" for path in project.hidden)]
    scheduled = set(schedule.values())
    problems.extend(f"unclassified scheduled task: {task}" for task in sorted(scheduled - sweeps.keys()))
    problems.extend(f"unscheduled classification: {task}" for task in sorted(sweeps.keys() - scheduled))
    problems.extend(f"no production task: {task}" for task in sorted(scheduled - defined.keys()))
    generated_recovery = {} if generated_recovery is None else generated_recovery
    claimed = {task for task, sweep in sweeps.items() if isinstance(sweep, GeneratedRecovery)}
    if claimed != generated_recovery.keys():
        problems.append(
            f"generated recovery inventory differs: declared={sorted(claimed)}, registered={sorted(generated_recovery)}"
        )
    grandfathered = {task for task, sweep in sweeps.items() if isinstance(sweep, Grandfathered)}
    problems.extend(f"unreviewed grandfathered: {task}" for task in sorted(grandfathered - reviewed_grandfathered))
    problems.extend(f"stale grandfathered: {task}" for task in sorted(reviewed_grandfathered - grandfathered))
    for name, declared in sorted(sweeps.items()):
        if isinstance(declared, (Grandfathered, NoPerRowLoop)) and len(declared.reason.strip()) < 20:
            problems.append(f"{name}: classification needs a substantive reason")
        if name not in defined:
            continue
        task = defined[name]
        if isinstance(declared, (Grandfathered, NoPerRowLoop)) and _ticks_somewhere(task, index):
            problems.append(f"{name}: reaches recovery_tick but is classified otherwise")
        if isinstance(declared, NoPerRowLoop) and (line := _per_row_loop(task)) is not None:
            problems.append(f"{name}:{line}: loops over a call")
        tick = generated_recovery.get(name) if isinstance(declared, GeneratedRecovery) else declared
        if not isinstance(tick, RecoveryTick):
            continue
        opener = _tick_opener(task, tick, project)
        if isinstance(opener, str):
            problems.append(f"{name}: {opener}")
            continue
        if isinstance(declared, GeneratedRecovery):
            continue  # Registry-owned cadence and gates are checked by the runtime's conformance adapter.
        early = _early_return(task, tick, project)
        if early and not tick.returns_before_tick:
            problems.append(early)
        elif not early and tick.returns_before_tick:
            problems.append(f"{name}: stale early-return explanation")
        if name not in intervals:
            problems.append(f"{name}: missing interval")
            continue
        required = max(default_stale_after, 2 * intervals[name])
        thresholds = _declared_stale_after(opener, default_stale_after)
        if thresholds and thresholds != {required}:
            problems.append(f"{name}: stale_after={sorted(map(str, thresholds))}; required {required}")
    assert not problems, "Schedule contract violations:\n" + "\n".join(problems)
