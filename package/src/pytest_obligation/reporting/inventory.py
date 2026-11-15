"""Find literal suite declarations without importing tests, fixtures or application code."""

import ast
import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from pytest_obligation._internal.python_source import Module, qualified_name, top_level_imports
from pytest_obligation.models import HarnessModel
from pytest_obligation.profiles.coverage import SourceLocation

_DECORATORS = {"due_work_contract_suite", "safety_contract_suite", "scheduled_selection_suite", "exempt_due_work_suite"}
_DUE_DECORATOR = "due.django.conformance.suite.effect_contract_suite"


class Application(HarnessModel):
    """A source declaration, never execution evidence or a coverage claim."""

    name: str
    source: SourceLocation
    nodeids: list[str] | None = None


class ApplicationInventory(HarnessModel):
    revision: str = ""
    collection_key: str = ""
    applications: dict[str, Application] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class InventoryFailure(HarnessModel):
    """Bounded diagnostic data; never retain parser errors or file contents."""

    kind: Literal["missing", "unreadable", "invalid", "revision"]
    expected_revision: str = Field(default="", max_length=128)
    actual_revision: str = Field(default="", max_length=128)

    def explain(self) -> str:
        if self.kind == "missing":
            return "Collected test inventory file was not found. Check the artifact download and inventory-path."
        if self.kind == "unreadable":
            return "Collected test inventory could not be read. Check the artifact download and file permissions."
        if self.kind == "invalid":
            return (
                "Collected test inventory has invalid JSON or inventory schema. Regenerate it with the collect action."
            )

        # Artifacts can be supplied by a fork. Only inert revision labels reach Markdown.
        def label(value: str) -> str:
            return value if re.fullmatch(r"[a-zA-Z0-9./_-]{1,128}", value) else "unavailable"

        return (
            f"Inventory revision: {label(self.actual_revision)}; "
            f"reporting checkout: {label(self.expected_revision)}. "
            "Collect and report against the same resolved commit as test execution. "
            "For PRs, choose either the PR head or the merge commit consistently across jobs."
        )


def _module_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Context managers do not introduce a Python scope; functions and classes do."""
    for node in body:
        yield node
        if isinstance(node, ast.With | ast.AsyncWith):
            yield from _module_statements(node.body)


class _Sources:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.trees: dict[Path, ast.Module] = {}

    def tree(self, path: Path, text: str | None = None) -> ast.Module:
        path = path.resolve()
        path.relative_to(self.root)
        if path not in self.trees:
            self.trees[path] = ast.parse(text if text is not None else path.read_text(encoding="utf-8-sig"))
        return self.trees[path]

    def imports(self, path: Path) -> dict[str, str]:
        relative = path.relative_to(self.root)
        parts = list(relative.with_suffix("").parts)
        package = parts[-1] == "__init__"
        if package:
            parts.pop()
        module = Module(name=".".join(parts), path=path, relative=relative.as_posix(), package=package)
        return top_level_imports(self.tree(path), module)

    def qualified(self, expression: ast.expr, path: Path) -> str:
        return qualified_name(expression, "", self.imports(path), set(), allow_unbound=True) or ""

    def module_file(self, parts: list[str]) -> Path | None:
        """Find local source in flat or src layouts; never search installed packages."""
        for root in (self.root, self.root / "src"):
            module = root.joinpath(*parts)
            for path in (module.with_suffix(".py"), module / "__init__.py"):
                if path.is_file():
                    return path
        return None

    def callable_name(self, expression: ast.expr, path: Path) -> str | None:
        """Resolve a declared function/class method, including imported aliases, without imports."""
        parts = self.qualified(expression, path).split(".")
        candidates = [(path, parts)]
        for split in range(len(parts) - 1, 0, -1):
            source = self.module_file(parts[:split])
            if source is not None:
                candidates.append((source, parts[split:]))
        for source, names in candidates:
            body = self.tree(source).body
            for index, name in enumerate(names):
                node = next(
                    (
                        item
                        for item in body
                        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and item.name == name
                    ),
                    None,
                )
                if node is None:
                    break
                if index == len(names) - 1:
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        return ".".join(names)
                elif isinstance(node, ast.ClassDef):
                    body = node.body
                else:
                    break
        return None

    def contract_name(self, expression: ast.expr, path: Path, seen: set[tuple[Path, str]]) -> str | None:
        if isinstance(expression, ast.Call):
            if self.qualified(expression.func, path) in (
                "pytest_obligation.DueWorkSource",
                "pytest_obligation.contract.DueWorkSource",
            ):
                target = (
                    expression.args[0]
                    if expression.args
                    else next((kw.value for kw in expression.keywords if kw.arg == "callable"), None)
                )
                name = self.callable_name(target, path) if target is not None else None
                return f"{name} exemption" if name else None
            return next(
                (
                    kw.value.value
                    for kw in expression.keywords
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
                ),
                None,
            )
        if isinstance(expression, ast.Name):
            identity = (path, expression.id)
            if identity in seen:
                return None
            seen.add(identity)
            for node in _module_statements(self.tree(path).body):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                    if isinstance(node, ast.AnnAssign)
                    else []
                )
                if any(isinstance(target, ast.Name) and target.id == expression.id for target in targets):
                    assert isinstance(node, (ast.Assign, ast.AnnAssign))
                    return self.contract_name(node.value, path, seen) if node.value else None
        qualified = self.qualified(expression, path)
        if "." not in qualified:
            return None
        module, name = qualified.rsplit(".", 1)
        imported = self.module_file(module.split("."))
        return self.contract_name(ast.Name(id=name), imported, seen) if imported is not None else None


def discover(root: Path, paths: list[str], *, suite_decorators: Sequence[str] = ()) -> ApplicationInventory:
    """Scan explicit source roots once; unresolved names keep their suite identity visible."""
    adapters = {_DUE_DECORATOR, *suite_decorators}
    names = _DECORATORS | {name.rsplit(".", 1)[-1] for name in adapters}
    sources = _Sources(root)
    applications: dict[str, Application] = {}
    limitations = [
        "Static declarations only; dynamically generated suites may be absent. No application code was imported."
    ]
    candidates: set[Path] = set()
    for value in paths:
        path = (sources.root / value).resolve()
        try:
            path.relative_to(sources.root)
            if not path.exists():
                raise ValueError("missing source root")
            candidates.update(path.rglob("*.py") if path.is_dir() else [path])
        except ValueError:
            limitations.append(f"Application source root unavailable: {value}")
    for path in sorted(candidates):
        try:
            path.resolve().relative_to(sources.root)
            text = path.read_text(encoding="utf-8-sig")
            # Most test modules contain no contract declaration. Read them once,
            # but allocate ASTs only for possible suites and their named bindings.
            if not any(name in text for name in names):
                continue
            tree = sources.tree(path, text)
            module = ".".join(path.relative_to(sources.root).with_suffix("").parts)
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    qualified = sources.qualified(decorator.func, path)
                    native = qualified.startswith("pytest_obligation.") and qualified.rsplit(".", 1)[-1] in _DECORATORS
                    if not native and qualified not in adapters:
                        continue
                    contract = (
                        decorator.args[0]
                        if decorator.args
                        else next((kw.value for kw in decorator.keywords if kw.arg in ("contract", "selection")), None)
                    )
                    try:
                        name = sources.contract_name(contract, path, set()) if contract else None
                    except (OSError, ValueError, SyntaxError, UnicodeError):
                        # The declaration is already known. Failure to inspect its
                        # display name must not erase that application's existence.
                        name = None
                    identity = f"{module}.{node.name}"
                    applications[identity] = Application(
                        name=name or node.name,
                        source=SourceLocation(path=path.relative_to(sources.root).as_posix(), line=node.lineno),
                    )
                    if name is None:
                        limitations.append(f"Application name unresolved: {identity}; showing its suite name.")
        except (OSError, ValueError, SyntaxError, UnicodeError):
            limitations.append(f"Application source could not be inspected: {path.name}")
    return ApplicationInventory(applications=applications, limitations=limitations)
