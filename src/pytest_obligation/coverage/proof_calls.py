"""Opt-in declaration policy: find direct proof calls outside ExtraProof runners.

Standalone proof calls remain supported by the library. Applications choosing
mandatory generated enrollment can use this scan with their own reviewed list.
It does not resolve local proof aliases or reflective getattr calls.
"""

import ast
from collections.abc import Iterator, Mapping

from pytest_obligation.coverage.project import dotted_parts, terminal_name
from pytest_obligation.models import HarnessModel

_HARNESS_PACKAGES = ("pytest_obligation", "due_work_harness", "due.django.conformance")


class ProofCall(HarnessModel):
    module: str
    proof: str
    line: int


def _in_harness(module: str) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in _HARNESS_PACKAGES)


def _harness_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """
    Local names bound to harness proofs, and to harness modules, at any depth.

    ``from <harness>... import assert_x [as y]`` binds a proof;
    ``from <harness or its parent> import sweep [as s]`` and
    ``import <harness>.sweep as s`` bind a module, whose ``s.assert_x(...)``
    calls are proofs too. A lowercase non-proof name imported from the harness
    is taken for a module; a function imported that way only matters if it has
    an ``assert_*`` attribute, which none has.
    """
    proofs: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bound = alias.asname or alias.name
                if _in_harness(node.module) and alias.name.startswith("assert_"):
                    proofs.add(bound)
                elif _in_harness(f"{node.module}.{alias.name}") and alias.name.islower():
                    modules.add(bound)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _in_harness(alias.name) and alias.asname:
                    modules.add(alias.asname)
    return proofs, modules


def _extra_proof_runners(tree: ast.Module) -> set[int]:
    """
    Node ids of the runners passed to ``ExtraProof``: the sanctioned way to apply a configured proof.

    Only the module-level function the runner names, or the lambda itself, is
    spared, never another function that happens to share the name.
    """
    module_functions = {
        node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    runners: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and terminal_name(node.func) == "ExtraProof"):
            continue
        passed = [keyword.value for keyword in node.keywords if keyword.arg == "run"] + node.args[1:2]
        for runner in passed:
            if isinstance(runner, ast.Lambda):
                runners.add(id(runner))
            elif isinstance(runner, ast.Name) and runner.id in module_functions:
                runners.add(id(module_functions[runner.id]))
    return runners


def _proof_called(call: ast.Call, proofs: set[str], modules: set[str]) -> str | None:
    if isinstance(call.func, ast.Name) and call.func.id in proofs:
        return call.func.id
    if isinstance(call.func, ast.Attribute) and call.func.attr.startswith("assert_"):
        parts = dotted_parts(call.func.value)
        owner = None if parts is None else [parts[0], *parts[1]]
        if owner is not None and (owner[0] in modules or _in_harness(".".join(owner))):
            return call.func.attr
    return None


def proof_calls(module: str, source: str) -> Iterator[ProofCall]:
    """Calls to harness proofs outside an ``ExtraProof`` runner."""
    tree = ast.parse(source)
    proofs, modules = _harness_names(tree)
    if not (proofs or modules or any(prefix in source for prefix in _HARNESS_PACKAGES)):
        return
    runners = _extra_proof_runners(tree)

    def visit(node: ast.AST, inside_runner: bool) -> Iterator[ProofCall]:
        inside_runner = inside_runner or id(node) in runners
        if not inside_runner and isinstance(node, ast.Call) and (proof := _proof_called(node, proofs, modules)):
            yield ProofCall(module=module, proof=proof, line=node.lineno)
        for child in ast.iter_child_nodes(node):
            yield from visit(child, inside_runner)

    yield from visit(tree, False)


def assert_declared_proofs(sources: Mapping[str, str], *, reviewed: Mapping[tuple[str, str], str]) -> None:
    """Reject unexplained calls and stale reviewed exceptions in caller-selected test source."""
    calls = [call for module, source in sources.items() for call in proof_calls(module, source)]
    named = {(call.module, call.proof) for call in calls}
    unreviewed = [
        f"{call.module}:{call.line} -> {call.proof}" for call in calls if (call.module, call.proof) not in reviewed
    ]
    stale = sorted(reviewed.keys() - named)
    thin = sorted(key for key, reason in reviewed.items() if len(reason.strip()) < 20)
    assert not (unreviewed or stale or thin), (
        f"Declare generated proofs: unreviewed={unreviewed}; stale={stale}; thin reasons={thin}"
    )
