"""Static schedule classification and recovery-heartbeat checks.

Applications supply schedules, policy values and reviewed exemptions. The
analysis imports no task modules. Ported from the backend Beat inventory;
source shape checks are evidence of structure, not a runtime isolation proof.
"""

import ast
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from pytest_obligation.coverage.project import Project, terminal_name
from pytest_obligation.models import HarnessModel


class RecoveryTick(HarnessModel):
    via: tuple[str, ...] = ()
    returns_before_tick: str = ""


class GeneratedRecovery(HarnessModel):
    """The application's registered runtime owns this generated recovery task."""


class NoPerRowLoop(HarnessModel):
    reason: str


class Grandfathered(HarnessModel):
    reason: str


Sweep = RecoveryTick | GeneratedRecovery | NoPerRowLoop | Grandfathered
_Function = ast.FunctionDef | ast.AsyncFunctionDef
_LOOPS = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


@dataclass(frozen=True)
class _Callable:
    path: str
    node: _Function


def _module_source(module: str, project: Project) -> Path | None:
    source = project.modules.get(module)
    return source.path if source is not None else None


def _string_constant(expression: ast.expr, tree: ast.Module, project: Project) -> str:
    """A literal task name, or a module constant this module defines or imports by name."""
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    assert isinstance(expression, ast.Name), (
        f"a task name must be a literal or a named constant, not {ast.dump(expression)}"
    )
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == expression.id for target in node.targets
        ):
            return _string_constant(node.value, tree, project)
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if (alias.asname or alias.name) == expression.id:
                    source = _module_source(node.module, project)
                    assert source is not None, f"{node.module} is not a module under {project.config.root}"
                    imported = ast.parse(source.read_text(encoding="utf-8"))
                    return _string_constant(ast.Name(alias.name), imported, project)
    raise AssertionError(f"cannot resolve the task name constant {expression.id}")


def _registered_name(decorator: ast.expr, default: str, tree: ast.Module, project: Project) -> str:
    if isinstance(decorator, ast.Call):
        for keyword in decorator.keywords:
            if keyword.arg == "name":
                return _string_constant(keyword.value, tree, project)
    return default


def _task_definitions(project: Project) -> dict[str, _Callable]:
    """Registered task name -> its production function, as Celery would register it."""
    tasks: dict[str, _Callable] = {}
    for source in project.production:
        text = source.path.read_text(encoding="utf-8")
        if "shared_task" not in text:
            continue
        tree = ast.parse(text, filename=source.relative)
        module = source.name
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if terminal_name(target) == "shared_task":
                    default = f"{module}.{node.name}"
                    name = _registered_name(decorator, default, tree, project)
                    tasks[name] = _Callable(default, node)
    return tasks


def _resolve_callable(path: str, project: Project) -> _Callable | None:
    """The production function an import-qualified path names: a module, then classes and functions inside it."""
    parts = path.split(".")
    for split in range(len(parts) - 1, 0, -1):
        source = _module_source(".".join(parts[:split]), project)
        if source is None:
            continue
        body: list[ast.stmt] = ast.parse(source.read_text(encoding="utf-8")).body
        found: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        for name in parts[split:]:
            scope = next(
                (
                    node
                    for node in body
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
                ),
                None,
            )
            if scope is None:
                return None
            body = scope.body
            found = scope if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        return None if found is None else _Callable(path, found)
    return None


def _references(node: ast.AST, name: str) -> bool:
    return any(
        (isinstance(child, ast.Name) and child.id == name) or (isinstance(child, ast.Attribute) and child.attr == name)
        for child in ast.walk(node)
    )


def _opens_a_tick(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Call) and terminal_name(child.func) == "recovery_tick" for child in ast.walk(node))


def _tick_opener(task: _Callable, tick: RecoveryTick, project: Project) -> _Callable | str:
    """The callable that calls ``recovery_tick(...)``, reached from the task through ``tick.via``, or why there is none."""
    caller = task
    for path in tick.via:
        callee = _resolve_callable(path, project)
        if callee is None:
            return f"via names {path}, which is no production function"
        if not _references(caller.node, path.rsplit(".", maxsplit=1)[-1]):
            return f"{caller.path} never calls {path}"
        caller = callee
    if not _opens_a_tick(caller.node):
        return f"{caller.path} does not call recovery_tick(...)"
    return caller


def _returns_before(body: list[ast.stmt], reaches: Callable[[ast.stmt], bool]) -> int | None:
    """The line of a ``return`` in the statements before the first one that ``reaches``, or ``None``."""
    for statement in body:
        if reaches(statement):
            return None
        for node in _walk_own_code(statement):
            if isinstance(node, ast.Return):
                return node.lineno
    return None


def _walk_own_code(node: ast.AST) -> Iterator[ast.AST]:
    """``ast.walk``, without descending into nested functions, lambdas or classes (their returns are theirs)."""
    if isinstance(node, _NESTED_SCOPES):
        return
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(child for child in ast.iter_child_nodes(current) if not isinstance(child, _NESTED_SCOPES))


def _early_return(task: _Callable, tick: RecoveryTick, project: Project) -> str | None:
    """Where the chain from the task to its tick can return before the tick opens, or ``None``."""
    chain: list[tuple[_Callable, Callable[[ast.stmt], bool]]] = []
    caller = task
    for path in tick.via:
        name = path.rsplit(".", maxsplit=1)[-1]
        chain.append((caller, lambda statement, name=name: _references(statement, name)))
        callee = _resolve_callable(path, project)
        if callee is None:
            return None  # _tick_problem reports a broken chain.
        caller = callee
    chain.append((caller, _opens_a_tick))
    for function, reaches in chain:
        if (line := _returns_before(function.node.body, reaches)) is not None:
            return f"{function.path} returns at line {line}, before it reaches the tick"
    return None


def _tick_problem(task: _Callable, tick: RecoveryTick, project: Project) -> str | None:
    """Why the task does not reach ``recovery_tick(...)`` through ``tick.via``, or ``None``."""
    opener = _tick_opener(task, tick, project)
    return opener if isinstance(opener, str) else None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _declared_stale_after(opener: _Callable, default_stale_after: timedelta) -> set[timedelta | str]:
    """
    The ``stale_after`` of each heartbeat ``recovery_tick(...)`` the callable opens: the default when none is passed.

    Only a literal ``timedelta(<unit>=<number>, ...)`` can be read; anything else is reported as its source.
    """
    declared: set[timedelta | str] = set()
    for call in ast.walk(opener.node):
        if not (isinstance(call, ast.Call) and terminal_name(call.func) == "recovery_tick"):
            continue
        heartbeat = _keyword(call, "heartbeat")
        if isinstance(heartbeat, ast.Constant) and heartbeat.value is False:
            continue  # A standalone loop publishes no threshold.
        value = _keyword(call, "stale_after")
        if value is None:
            declared.add(default_stale_after)
        elif (
            isinstance(value, ast.Call)
            and terminal_name(value.func) == "timedelta"
            and not value.args
            and all(isinstance(keyword.value, ast.Constant) for keyword in value.keywords)
        ):
            declared.add(timedelta(**{keyword.arg: keyword.value.value for keyword in value.keywords}))  # type: ignore[misc]
        else:
            declared.add(ast.unparse(value))
    return declared


def _per_row_loop(task: _Callable) -> int | None:
    """The line of a loop in the task function's own body that calls something per row, or ``None``."""
    for node in ast.walk(task.node):
        if isinstance(node, _LOOPS) and any(isinstance(child, ast.Call) for child in ast.walk(node)):
            return node.lineno
    return None


def _function_index(project: Project) -> dict[str, list[tuple[str | None, _Function]]]:
    """Production functions by the name a call uses: ``function`` or ``Class.method``."""
    index: dict[str, list[tuple[str | None, _Function]]] = defaultdict(list)
    for source in project.production:
        for node in project.tree(source).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index[node.name].append((None, node))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        index[f"{node.name}.{item.name}"].append((node.name, item))
    return index


def _calls(owner: str | None, function: _Function) -> set[str]:
    """``f()`` and ``Name.attr()`` calls, with ``self.``/``cls.`` read as the enclosing class."""
    called: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            receiver = node.func.value.id
            called.add(f"{owner if owner and receiver in ('self', 'cls') else receiver}.{node.func.attr}")
    return called


def _ticks_somewhere(task: _Callable, index: dict[str, list[tuple[str | None, _Function]]]) -> bool:
    """Whether the task, or any function it calls by name or as ``Class.method`` (transitively), opens a tick."""
    seen: set[str] = set()
    pending: list[tuple[str | None, _Function]] = [(None, task.node)]
    while pending:
        owner, function = pending.pop()
        called = _calls(owner, function)
        if "recovery_tick" in called:
            return True
        for name in called - seen:
            seen.add(name)
            pending.extend(index.get(name, ()))
    return False


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
