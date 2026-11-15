"""Static Python names and source traversal shared by coverage and report discovery.

These helpers parse source; they never import the inspected application.
"""

import ast
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

from pytest_obligation.models import HarnessModel


class Module(HarnessModel):
    name: str
    path: Path
    relative: str
    package: bool


def relative_source(node: ast.ImportFrom, module: Module) -> str:
    source = node.module or ""
    if not node.level:
        return source
    package = module.name if module.package else module.name.rpartition(".")[0]
    parts = package.split(".") if package else []
    anchor = parts[: max(len(parts) - node.level + 1, 0)]
    return ".".join([*anchor, source] if source else anchor)


def import_bindings(node: ast.Import | ast.ImportFrom, module: Module) -> dict[str, str]:
    """The local names one import binds, including relative imports and aliases."""
    if isinstance(node, ast.ImportFrom):
        source = relative_source(node, module)
        return {alias.asname or alias.name: f"{source}.{alias.name}" if source else alias.name for alias in node.names}
    return {
        alias.asname or alias.name.split(".", 1)[0]: alias.name if alias.asname else alias.name.split(".", 1)[0]
        for alias in node.names
    }


def top_level_imports(tree: ast.Module, module: Module) -> dict[str, str]:
    """Local name -> qualified name, with later module-level imports taking precedence."""
    imported: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            imported.update(import_bindings(node, module))
    return imported


def defined_names(tree: ast.Module) -> set[str]:
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)}


def dotted_parts(expression: ast.expr) -> tuple[str, list[str]] | None:
    """``a.b.c`` -> ("a", ["b", "c"]); anything else -> None."""
    parts: list[str] = []
    while isinstance(expression, ast.Attribute):
        parts.append(expression.attr)
        expression = expression.value
    if not isinstance(expression, ast.Name):
        return None
    return expression.id, list(reversed(parts))


def qualified_name(
    expression: ast.expr, module: str, imported: Mapping[str, str], defined: set[str], *, allow_unbound: bool = False
) -> str | None:
    dotted = dotted_parts(expression)
    if dotted is None:
        return None
    base, rest = dotted
    if base in imported:
        head = imported[base]
    elif base in defined:
        head = f"{module}.{base}"
    elif allow_unbound:
        head = base
    else:
        return None
    return ".".join([head, *rest])


def within_packages(qualified: str, packages: Iterable[str]) -> bool:
    """Match a package itself or a dotted descendant, never a coincidental name prefix."""
    return any(qualified == package or qualified.startswith(f"{package}.") for package in packages)


def python_files(
    base: Path, skip_directory: Callable[[Path], bool], skip_file: Callable[[Path], bool] | None = None
) -> Iterator[Path]:
    """Walk deterministically while callers own their distinct directory/file exclusion policies."""
    for directory, subdirectories, files in os.walk(base):
        here = Path(directory)
        subdirectories[:] = [name for name in sorted(subdirectories) if not skip_directory(here / name)]
        for name in sorted(files):
            path = here / name
            if name.endswith(".py") and (skip_file is None or not skip_file(path)):
                yield path


def resolve_callable(
    path: str,
    module_tree: Callable[[str], ast.Module | None],
    *,
    allow_nested_functions: bool = True,
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef] | None:
    """Resolve a callable to its module-relative name and AST; callers own source lookup.

    The first existing module prefix owns the remaining path. An empty prefix
    permits a caller to supply its current module for local declarations.
    """
    parts = path.split(".")
    for split in range(len(parts) - 1, -1, -1):
        tree = module_tree(".".join(parts[:split]))
        if tree is None:
            continue
        body = tree.body
        for index, name in enumerate(parts[split:], start=split):
            scope = next(
                (
                    node
                    for node in body
                    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
                ),
                None,
            )
            if scope is None:
                return None
            if index == len(parts) - 1:
                return (
                    (".".join(parts[split:]), scope)
                    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef)
                    else None
                )
            if not allow_nested_functions and not isinstance(scope, ast.ClassDef):
                return None
            body = scope.body
    return None
