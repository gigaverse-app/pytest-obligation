"""Portable collect-only hook: works with the adopter's installed pytest version."""

import json
import os
from pathlib import Path

import pytest

_NODEIDS = pytest.StashKey[list[str]]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_NODEIDS] = []


def pytest_itemcollected(item: pytest.Item) -> None:
    # Capture before collection filters, including optional generated tests.
    item.config.stash[_NODEIDS].append(item.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if session.config.getoption("collectonly") and exitstatus in (0, 5) and _NODEIDS in session.config.stash:
        Path(os.environ["OBLIGATION_COLLECTION_OUTPUT"]).write_text(json.dumps(session.config.stash[_NODEIDS]))
