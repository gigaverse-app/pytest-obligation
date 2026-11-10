"""Semantic mutations of the current merge AST, shared by proof and API replay."""

import ast

SOURCE_MUTANTS = (
    "early-evidence-write",
    "replace-retained-case",
    "remove-compatibility-guards",
    "omit-evidence-commit",
)


def _is_guard(node: ast.Expr) -> bool:
    # Compatibility checks are _agree(compatible, disagreement) calls, which raise IncompatibleShard
    # even under python -O (#225); before that they were assert statements.
    call = node.value
    return isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_agree"


def mutate_source(source: str, mutant: str) -> str:
    if mutant not in SOURCE_MUTANTS:
        raise ValueError(f"unknown source mutant {mutant}")
    module = ast.parse(source)
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "merge_reports")
    start, end = function.lineno, function.end_lineno

    class Mutate(ast.NodeTransformer):
        def visit_Assert(self, node):
            return None if mutant == "remove-compatibility-guards" else node

        def visit_Assign(self, node):
            if mutant == "early-evidence-write" and ast.unparse(node.targets[0]) == "old":
                return [node, *ast.parse("old.collected |= case.collected").body]
            return node

        def visit_Expr(self, node):
            if mutant == "replace-retained-case" and ast.unparse(node) == "pairs.append((old, case))":
                return [node, *ast.parse("existing_cases[case_id] = case").body]
            if mutant == "remove-compatibility-guards" and _is_guard(node):
                return None
            return node

    if mutant == "omit-evidence-commit":
        assert isinstance(function.body[-1], ast.For)
        assert ast.unparse(function.body[-2]) == "target.update(additions)"
        function.body = function.body[:-2]
    else:
        function = ast.fix_missing_locations(Mutate().visit(function))
    lines = source.splitlines(keepends=True)
    return "".join(lines[: start - 1]) + ast.unparse(function) + "\n" + "".join(lines[end:])
