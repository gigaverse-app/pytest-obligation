"""Locate contract setup without executing factories or guessing their internals."""

import ast
import inspect
from pathlib import Path

from .coverage import SourceLocation


def contract_source(cls: type, contract: object, root: Path) -> SourceLocation | None:
    try:
        filename = inspect.getsourcefile(cls)
        if filename is None:
            return None
        path = Path(filename).resolve()
        relative = path.relative_to(root.resolve()).as_posix()
        module = inspect.getmodule(cls)
        aliases = {name for name, value in vars(module).items() if value is contract} if module else set()
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, ast.AnnAssign)
                else []
            )
            if any(isinstance(target, ast.Name) and target.id in aliases for target in targets):
                return SourceLocation(path=relative, line=node.lineno, kind="contract setup")
        return SourceLocation(path=relative, line=inspect.getsourcelines(cls)[1])
    except (OSError, ValueError, TypeError, SyntaxError, UnicodeError):
        return None  # Source navigation is optional; never disrupt test collection.
