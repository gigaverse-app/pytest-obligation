"""Transitive Celery publication reach while a caller holds a transaction.

Ported from the backend's publication tripwire. Application exemptions stay with
applications; this module supplies evidence without importing application code.
Unlike the lexical in-transaction scan, this follows typed collaborators and
inherited methods. See publications_before_commit for deliberate resolution limits.
"""

import ast
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass

from pytest_obligation.coverage.config import CoverageConfig
from pytest_obligation.coverage.project import Module, Project, dotted_parts, qualified_name, terminal_name
from pytest_obligation.models import HarnessModel

_PUBLICATION_METHODS = {"delay", "apply_async", "send_task"}
#: Imported names that open a transaction as a decorator or a ``with`` block. Any
#: ``<x>.atomic(...)`` also counts: ``transaction.atomic`` and every durable-work
#: capability's ``atomic`` producer scope open one.
_TRANSACTION_OPENERS = {"django.db.transaction.atomic"}


@dataclass(frozen=True)
class _CallRef:
    """A call target as written: ``self`` of a class, or an import-qualified prefix, then attribute names."""

    owner_class: str | None
    prefix: str | None
    attributes: tuple[str, ...]


@dataclass
class _Frame:
    """One executable scope. A lambda or nested def runs whenever it is called, so it gets its own frame."""

    callable: str | None
    owner_class: str | None
    open_transactions: int = 0


class _PublicationReach(ast.NodeVisitor):
    """
    Record, for one module, what the reach analysis needs.

    * the callables it defines, its classes' resolved bases and annotated fields
      (``community_service: CommunityService = di.dependency(...)``), so that
      ``self.community_service.create_event`` resolves to a callable;
    * every callable's direct publications and resolvable outgoing calls, outside
      any lambda or nested def it contains (an ``on_commit`` callback runs after
      the commit, not where it is written);
    * every publication or call made while the callable holds a transaction open.
    """

    def __init__(self, module: Module, project: Project) -> None:
        self.module = module.name
        tree = project.tree(module)
        self.imported = project.imports(module)
        self.openers = _TRANSACTION_OPENERS | project.config.transaction_openers
        self.module_names = {
            node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        self.scopes: list[str] = []
        self.frames: list[_Frame] = []
        self.defined: set[str] = set()
        self.fields: dict[str, dict[str, str]] = {}
        self.bases: dict[str, list[str]] = {}
        self.publications: Counter[str] = Counter()
        self.calls: list[tuple[str, _CallRef]] = []
        self.in_transaction: list[tuple[str, _CallRef | None]] = []

    def _qualified(self, expression: ast.expr) -> str | None:
        return qualified_name(expression, self.module, self.imported, self.module_names)

    def _opens_transaction(self, expression: ast.expr) -> bool:
        target = expression.func if isinstance(expression, ast.Call) else expression
        if isinstance(target, ast.Attribute) and target.attr == "atomic":
            return True
        return self._qualified(target) in self.openers

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([self.module, *self.scopes, node.name])
        self.bases[qualified] = [base for base in map(self._qualified, node.bases) if base]
        self.fields[qualified] = {
            statement.target.id: annotation
            for statement in node.body
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            if (annotation := self._qualified(statement.annotation))
        }
        self.scopes.append(node.name)
        # Methods directly in this class body bind ``self`` to it.
        self.frames.append(_Frame(callable=None, owner_class=qualified))
        self.generic_visit(node)
        self.frames.pop()
        self.scopes.pop()

    def _visit_callable(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in [*node.decorator_list, *node.args.defaults, *node.args.kw_defaults]:
            if expression is not None:
                self.visit(expression)
        enclosing = self.frames[-1] if self.frames else None
        in_class_body = enclosing is not None and enclosing.callable is None
        self.scopes.append(node.name)
        qualified = ".".join([self.module, *self.scopes])
        self.defined.add(qualified)
        self.frames.append(
            _Frame(
                callable=qualified,
                owner_class=enclosing.owner_class if enclosing is not None and in_class_body else None,
                open_transactions=int(any(self._opens_transaction(decorator) for decorator in node.decorator_list)),
            )
        )
        for statement in node.body:
            self.visit(statement)
        self.frames.pop()
        self.scopes.pop()

    visit_FunctionDef = _visit_callable
    visit_AsyncFunctionDef = _visit_callable

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.frames.append(_Frame(callable=None, owner_class=None))
        self.generic_visit(node)
        self.frames.pop()

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item)
        frame = self.frames[-1] if self.frames else None
        opens = frame is not None and any(self._opens_transaction(item.context_expr) for item in node.items)
        if frame is not None and opens:
            frame.open_transactions += 1
        for statement in node.body:
            self.visit(statement)
        if frame is not None and opens:
            frame.open_transactions -= 1

    visit_With = _visit_with
    visit_AsyncWith = _visit_with

    def _reference(self, target: ast.expr, frame: _Frame) -> _CallRef | None:
        # ``sync_to_async(f)(...)`` runs ``f``: attribute the call to ``f``.
        if isinstance(target, ast.Call) and terminal_name(target.func) == "sync_to_async" and target.args:
            target = target.args[0]
        resolved = dotted_parts(target)
        if resolved is None:
            return None
        root, attributes = resolved
        parts = [root, *attributes]
        if parts[0] == "self":
            if frame.owner_class is None or len(parts) < 2:
                return None
            return _CallRef(owner_class=frame.owner_class, prefix=None, attributes=tuple(parts[1:]))
        prefix = self._qualified(ast.Name(id=parts[0]))
        return None if prefix is None else _CallRef(owner_class=None, prefix=prefix, attributes=tuple(parts[1:]))

    def visit_Call(self, node: ast.Call) -> None:
        frame = self.frames[-1] if self.frames else None
        if frame is not None and frame.callable is not None:
            if isinstance(node.func, ast.Attribute) and node.func.attr in _PUBLICATION_METHODS:
                self.publications[frame.callable] += 1
                if frame.open_transactions:
                    self.in_transaction.append((frame.callable, None))
            elif (reference := self._reference(node.func, frame)) is not None:
                self.calls.append((frame.callable, reference))
                if frame.open_transactions:
                    self.in_transaction.append((frame.callable, reference))
        self.generic_visit(node)


@dataclass
class _ReachGraph:
    """Every scanned module's definitions, resolved across modules."""

    defined: set[str]
    fields: dict[str, dict[str, str]]
    bases: dict[str, list[str]]

    def _method(self, owner: str, name: str, seen: frozenset[str] = frozenset()) -> str | None:
        if owner in seen:
            return None
        if f"{owner}.{name}" in self.defined:
            return f"{owner}.{name}"
        return next(
            (found for base in self.bases.get(owner, []) if (found := self._method(base, name, seen | {owner}))), None
        )

    def _field(self, owner: str, name: str, seen: frozenset[str] = frozenset()) -> str | None:
        if owner in seen:
            return None
        if name in self.fields.get(owner, {}):
            return self.fields[owner][name]
        return next(
            (found for base in self.bases.get(owner, []) if (found := self._field(base, name, seen | {owner}))), None
        )

    def resolve(self, reference: _CallRef) -> str | None:
        if reference.prefix is not None:
            qualified = ".".join([reference.prefix, *reference.attributes])
            owner, _, method = qualified.rpartition(".")
            return self._method(owner, method) or qualified
        owner = reference.owner_class
        assert owner is not None, "a self reference always names its class"
        *path, method = reference.attributes
        for field in path:
            owner = self._field(owner, field)
            if owner is None:
                return None
        return self._method(owner, method)


def publications_before_commit(config: CoverageConfig) -> dict[str, dict[str, tuple[str, ...]]]:
    """
    Transaction owner -> each callable that publishes directly while its transaction is open.

    Each publisher maps to the chain of resolved callables from the owner's call
    to it; an empty chain is a publication in the owner's own body. Static
    resolution follows ``self.<method>``, ``self.<field>[.<field>].<method>``
    through class-body annotations (and their bases), ``sync_to_async(f)``, and
    imported or module-level names. It does not follow a local variable, a
    ``create()`` result, a port whose annotation is an abstract class, or a call
    made inside a lambda or nested def.
    """
    scanners: list[_PublicationReach] = []
    project = Project(config)
    for module in project.production:
        scanner = _PublicationReach(module, project)
        scanner.visit(project.tree(module))
        scanners.append(scanner)
    if project.hidden or project.unparsable:
        raise ValueError(f"Publication scan is incomplete: {project.hidden + project.unparsable}")
    graph = _ReachGraph(defined=set(), fields={}, bases={})
    publishers: set[str] = set()
    for scanner in scanners:
        graph.defined |= scanner.defined
        graph.fields |= scanner.fields
        graph.bases |= scanner.bases
        publishers |= set(scanner.publications)

    callers: dict[str, set[str]] = {}
    for scanner in scanners:
        for caller, reference in scanner.calls:
            if (callee := graph.resolve(reference)) is not None:
                callers.setdefault(callee, set()).add(caller)
    # Breadth-first back from each publisher: the shortest chain from every callable that reaches it.
    reaches: dict[str, dict[str, tuple[str, ...]]] = {}
    for publisher in sorted(publishers):
        chains: dict[str, tuple[str, ...]] = {publisher: (publisher,)}
        pending = deque([publisher])
        while pending:
            callee = pending.popleft()
            for caller in sorted(callers.get(callee, ())):
                if caller not in chains:
                    chains[caller] = (caller, *chains[callee])
                    pending.append(caller)
        for reaching, chain in chains.items():
            reaches.setdefault(reaching, {})[publisher] = chain

    found: dict[str, dict[str, tuple[str, ...]]] = {}
    for scanner in scanners:
        for owner, reference in scanner.in_transaction:
            if reference is None:
                found.setdefault(owner, {})[owner] = ()
            elif (callee := graph.resolve(reference)) is not None:
                for publisher, chain in reaches.get(callee, {}).items():
                    found.setdefault(owner, {}).setdefault(publisher, chain)
    return found


class PublishedBeforeCommit(HarnessModel):
    """An application-owned reviewed exception, naming exactly the reachable publishers."""

    reason: str
    publishers: frozenset[str]


def assert_publications_reviewed(config: CoverageConfig, *, reviewed: Mapping[str, PublishedBeforeCommit]) -> None:
    """Require all transaction-held publications to match the reviewed inventory exactly."""
    found = publications_before_commit(config)
    added = {
        owner: sorted(set(publishers) - reviewed[owner].publishers if owner in reviewed else set(publishers))
        for owner, publishers in found.items()
    }
    added = {owner: names for owner, names in added.items() if names}
    stale = {owner: sorted(entry.publishers - found.get(owner, {}).keys()) for owner, entry in reviewed.items()}
    stale = {owner: names for owner, names in stale.items() if names or owner not in found}
    thin = sorted(owner for owner, entry in reviewed.items() if len(entry.reason.strip()) < 40 or not entry.publishers)
    assert not (added or stale or thin), f"Publications before commit: unreviewed={added}; stale={stale}; thin={thin}"
