"""Find literal suite declarations without importing tests, fixtures or application code."""

import ast
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from pytest_obligation.models import HarnessModel
from pytest_obligation.profiles.coverage import SourceLocation

_DECORATORS = {"due_work_contract_suite", "safety_contract_suite"}
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
        aliases = {}
        package = path.relative_to(self.root).with_suffix("").parts[:-1]
        for node in self.tree(path).body:
            if isinstance(node, ast.ImportFrom):
                prefix = list(package[: len(package) - node.level + 1]) if node.level else []
                prefix += node.module.split(".") if node.module else []
                for alias in node.names:
                    aliases[alias.asname or alias.name] = ".".join([*prefix, alias.name])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
        return aliases

    def qualified(self, expression: ast.expr, path: Path) -> str:
        if isinstance(expression, ast.Name):
            return self.imports(path).get(expression.id, expression.id)
        if isinstance(expression, ast.Attribute):
            return f"{self.qualified(expression.value, path)}.{expression.attr}"
        return ""

    def contract_name(self, expression: ast.expr, path: Path, seen: set[tuple[Path, str]]) -> str | None:
        if isinstance(expression, ast.Call):
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
            for node in self.tree(path).body:
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
        imported = self.root.joinpath(*module.split(".")).with_suffix(".py")
        if not imported.is_file():
            imported = self.root.joinpath(*module.split("."), "__init__.py")
        return self.contract_name(ast.Name(id=name), imported, seen) if imported.is_file() else None


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
                        else next((kw.value for kw in decorator.keywords if kw.arg == "contract"), None)
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
