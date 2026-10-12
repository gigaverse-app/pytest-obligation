"""Transitive Celery publication reach while a caller holds a transaction.

Ported from the backend's publication tripwire. Application exemptions stay with
applications; this module supplies evidence without importing application code.
Unlike the lexical in-transaction scan, this follows typed collaborators and
inherited methods. See publications_before_commit for deliberate resolution limits.
"""

from collections import deque
from collections.abc import Mapping

from pytest_obligation.coverage._internal.transactions import _PublicationReach, _ReachGraph
from pytest_obligation.coverage.config import CoverageConfig
from pytest_obligation.coverage.project import Project
from pytest_obligation.models import HarnessModel

__all__ = ["PublishedBeforeCommit", "assert_publications_reviewed", "publications_before_commit"]


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
