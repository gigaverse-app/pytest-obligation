"""Application-owned baseline for generated strict expected failures.

Enable collection enforcement with ``--due-work-debt-baseline PATH`` (or the
same ini setting), installing ``pytest-obligation[debt]`` for YAML support.
``NotAssessed`` is binding debt; other strict xfails are known defects and need
an issue key or URL. Reasons remain descriptive, while case IDs and kinds must
match exactly. Applications own review of additions, TODO reduction and removed
suites; this library compares the suites selected by the current invocation.

Set ``DUE_WORK_DEBT_BASELINE=update`` to regenerate selected whole suites,
preserving surviving issue references. Updates refuse xdist workers.
"""

import ast
import os
import re
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Where the baseline lives, relative to the pytest root (a child session plants its own).
BASELINE = Path("due_work_debt_baseline.yaml")

#: Set to ``update`` to rewrite each collected suite's entries instead of checking them.
UPDATE_ENVIRONMENT = "DUE_WORK_DEBT_BASELINE"

#: The ticket of a known defect imported before its ticket existed. Only the ones in the
#: committed baseline are allowed, and the repository-wide check only lets their count fall.
UNTICKETED = "TODO"

_TICKET = re.compile(r"(?:[A-Z][A-Z0-9]*-[0-9]+|https?://\S+)")
_DOC = "docs/debt-baseline.md"
_HEADER = f"""\
# Durable-work expected failures: one entry per strict xfail a generated suite carries.
#
# binding-debt: a NotAssessed profile or E family. Resolve it by binding the production seam,
#   or by declaring NotApplicable with a reason production confirms.
# known-defect: a KnownGap, a declared gap, or an interleaving KnownFailure. Every entry
#   names the ticket that fixes the defect.
#
# Collection fails when a suite's xfails differ from its entries, so this file changes in the
# same PR as the declaration, and only shrinks. Regenerate the entries of the suites you
# collect with `{UPDATE_ENVIRONMENT}=update pytest --collect-only -p no:xdist <contract files>`.
#
# Canonical doc: {_DOC}
"""

DebtKind = Literal["binding-debt", "known-defect"]


class DebtEntry(BaseModel):
    """One generated expected failure: the case id pytest shows, why it fails, and who fixes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    case: str = Field(min_length=1, description="The generated case id, as in `test_due_work_contract[<case>]`.")
    kind: DebtKind
    ticket: str | None = Field(default=None, description="issue key or URL of the fix; required for a known defect.")
    reason: str = Field(min_length=1, description="The declared reason, for readers; not compared.")


class SuiteDebt(BaseModel):
    """One generated suite's expected failures, in the order the generator emits its cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    suite: str = Field(min_length=1, description="The suite class as `module.Class`.")
    debt: list[DebtEntry] = Field(min_length=1)


class DebtBaseline(BaseModel):
    """The whole committed file, one item per suite that has any expected failure."""

    model_config = ConfigDict(extra="forbid")
    suites: list[SuiteDebt] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_item_per_suite_and_case(self) -> Self:
        suites = [item.suite for item in self.suites]
        if len(suites) != len(set(suites)):
            raise ValueError(f"a suite is listed twice: {sorted({name for name in suites if suites.count(name) > 1})}")
        for item in self.suites:
            cases = [entry.case for entry in item.debt]
            if len(cases) != len(set(cases)):
                raise ValueError(f"{item.suite} lists a case twice")
        return self

    def of(self, suite: str) -> list[DebtEntry]:
        return next((item.debt for item in self.suites if item.suite == suite), [])


def load_baseline(root: Path, *, baseline: Path = BASELINE) -> DebtBaseline:
    path = root / baseline
    if not path.is_file():
        return DebtBaseline()
    return DebtBaseline.model_validate(_yaml().safe_load(path.read_text(encoding="utf-8")) or {})


def ticket_defects(entries: list[DebtEntry]) -> list[str]:
    """Known defects without a valid ticket, and tickets that are not issue key or URLs."""
    defects = []
    for entry in entries:
        if entry.kind == "known-defect" and entry.ticket is None:
            defects.append(
                f"{entry.case}: a known defect needs the issue key or URL of its fix (`ticket: PROJECT-1234`)"
            )
        elif entry.ticket not in (None, UNTICKETED) and not _TICKET.fullmatch(entry.ticket):
            defects.append(f"{entry.case}: ticket {entry.ticket!r} is not a issue key or URL")
    return defects


def debt_mismatch(suite: str, declared: list[DebtEntry], root: Path, *, baseline: Path = BASELINE) -> str | None:
    """
    Why ``suite``'s declared expected failures and its baseline entries disagree, or None.

    Cases are compared by id and kind. Reasons are informational, so rewording one is not a
    mismatch; ``update`` mode refreshes them.
    """
    if os.environ.get(UPDATE_ENVIRONMENT) == "update":
        return _update(suite, declared, root, baseline=baseline)
    recorded = {entry.case: entry for entry in load_baseline(root, baseline=baseline).of(suite)}
    present = {entry.case: entry for entry in declared}
    added = [entry for case, entry in present.items() if case not in recorded]
    stale = [case for case in recorded if case not in present]
    rekinded = [
        f"{case}: declared {entry.kind}, baselined {recorded[case].kind}"
        for case, entry in present.items()
        if case in recorded and recorded[case].kind != entry.kind
    ]
    tickets = ticket_defects(list(recorded.values()))
    if not (added or stale or rekinded or tickets):
        return None
    sections = [
        f"{suite}: its durable-work expected failures differ from {baseline.as_posix()}. "
        f"The baseline only shrinks; see {_DOC}."
    ]
    if added:
        sections.append(
            f"New expected failures ({len(added)}). Resolve them in this PR rather than baselining them: bind the "
            "profile's production seam, or declare NotApplicable with a reason production confirms (binding "
            "debt); fix the defect (known defect). Only a real defect you cannot fix here gets an entry, with "
            f"the ticket of its fix, under `suite: {suite}`:\n" + _dump_entries(added, placeholder=True)
        )
    if stale:
        sections.append(
            f"Stale entries ({len(stale)}): the xfail is gone; delete them from the baseline:" + _bullets(stale)
        )
    if rekinded:
        sections.append("Kind changed; update the entry and its ticket:" + _bullets(rekinded))
    if tickets:
        sections.append("Ticket required:" + _bullets(tickets))
    return "\n\n".join(sections)


def _bullets(lines: list[str]) -> str:
    return "".join(f"\n  - {line}" for line in lines)


def _entry_document(entry: DebtEntry, *, placeholder: bool = False) -> dict[str, str]:
    if placeholder and entry.kind == "known-defect" and entry.ticket is None:
        entry = entry.model_copy(update={"ticket": "<issue key or URL, e.g. PROJECT-1234>"})
    return entry.model_dump(exclude_none=True)


def _dump_entries(entries: list[DebtEntry], *, placeholder: bool = False) -> str:
    document = {"debt": [_entry_document(entry, placeholder=placeholder) for entry in entries]}
    return _yaml().safe_dump(document, sort_keys=False, allow_unicode=True, width=110)


def _update(suite: str, declared: list[DebtEntry], root: Path, *, baseline: Path) -> str | None:
    """Rewrite one suite's entries, keeping each surviving case's ticket; refuse concurrent writers."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return f"{UPDATE_ENVIRONMENT}=update rewrites one file; run it without xdist workers (-p no:xdist)"
    recorded = load_baseline(root, baseline=baseline)
    tickets = {(entry.case, entry.kind): entry.ticket for entry in recorded.of(suite)}
    entries = [entry.model_copy(update={"ticket": tickets.get((entry.case, entry.kind))}) for entry in declared]
    items = [item for item in recorded.suites if item.suite != suite]
    if entries:
        items.append(SuiteDebt(suite=suite, debt=entries))
    document = {
        "suites": [
            {"suite": item.suite, "debt": [_entry_document(entry) for entry in item.debt]}
            for item in sorted(items, key=lambda item: item.suite)
        ]
    }
    path = root / baseline
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _HEADER + "\n" + _yaml().safe_dump(document, sort_keys=False, allow_unicode=True, width=110)
    # LF on every platform, so a Windows regeneration produces no line-ending diff.
    path.write_text(text, encoding="utf-8", newline="\n")
    return None


def _yaml() -> Any:
    # Optional serialization dependency: importing contracts must remain framework-free.
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError("YAML debt baselines require pytest-obligation[debt]") from error
    return yaml


def assert_debt_baseline(root: Path, *, baseline: Path = BASELINE, unticketed_ceiling: int = 0) -> None:
    """Audit the whole baseline, including suites absent from this pytest selection.

    Applications own the path and reviewed allowance. The library owns stale
    suite detection, ticket validation and the exact remaining allowance, so a
    resolved unticketed defect cannot silently free a slot for another one.
    """
    recorded = load_baseline(root, baseline=baseline)
    problems: list[str] = []
    for item in recorded.suites:
        module, _, name = item.suite.rpartition(".")
        path = root.joinpath(*module.split(".")).with_suffix(".py")
        if not path.is_file() or not any(
            isinstance(node, ast.ClassDef) and node.name == name
            for node in ast.parse(path.read_text(encoding="utf-8")).body
        ):
            problems.append(f"baseline suite no longer exists: {item.suite}")
        problems.extend(f"{item.suite}: {defect}" for defect in ticket_defects(item.debt))
    untracked = sum(entry.ticket == UNTICKETED for item in recorded.suites for entry in item.debt)
    if untracked != unticketed_ceiling:
        problems.append(
            f"unticketed defects {untracked} differ from reviewed ceiling {unticketed_ceiling}; "
            "new defects need tickets and resolved allowances must be lowered"
        )
    assert not problems, "\n".join(problems)
