"""Collection-time fixture validation behind ``--due-work-check-fixtures``.

Only retained items are checked. Skipped tests still need resolvable fixtures;
dynamic ``request.getfixturevalue`` calls cannot be validated at collection.
The xdist worker emits one ordinary failing item instead of crashing collection.
"""

from pathlib import Path
from typing import Any

import pytest


def _indirect(item: pytest.Item) -> set[str]:
    """Names a ``parametrize`` mark routes through a fixture (``indirect=``); those still need the fixture."""
    names: set[str] = set()
    for mark in item.iter_markers("parametrize"):
        argnames = mark.args[0] if mark.args else mark.kwargs.get("argnames", ())
        if isinstance(argnames, str):
            argnames = [name.strip() for name in argnames.split(",") if name.strip()]
        indirect = mark.kwargs.get("indirect", False)
        names.update(argnames if indirect is True else indirect if isinstance(indirect, (list, tuple)) else ())
    return names


class MissingFixtures(pytest.Item):
    """Fails with the report, for xdist workers, where raising during collection crashes the run instead."""

    def __init__(self, *, message: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.message = message

    def runtest(self) -> None:
        pytest.fail(self.message, pytrace=False)

    def reportinfo(self) -> tuple[Path, None, str]:
        return self.path, None, "missing fixture imports"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session: pytest.Session, items: list[pytest.Item]) -> None:
    # trylast: runs after the hooks that deselect items, so only tests this run keeps are checked.
    manager = session._fixturemanager
    missing = []
    for item in items:
        info = getattr(item, "_fixtureinfo", None)
        if info is None:
            continue
        direct = set(getattr(getattr(item, "callspec", None), "params", {})) - _indirect(item)
        for name in info.names_closure:
            if name != "request" and name not in direct and not manager.getfixturedefs(name, item):
                missing.append(f"{item.nodeid}: {name}")
    if not missing:
        return
    message = (
        "Collected tests request unavailable fixtures; define or import them, including for skipped tests:\n  "
        + "\n  ".join(missing)
    )
    if hasattr(session.config, "workerinput"):
        # Every worker collects the same items, so each adds the same failing one and xdist runs it once.
        items.append(MissingFixtures.from_parent(session, name="missing-fixtures", message=message))
        return
    raise pytest.UsageError(message)
