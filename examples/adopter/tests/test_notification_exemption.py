"""An executable best-effort disposition with independent SQL and delivery observations."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from adopter_app.announcements import Noticeboard

from pytest_obligation import DueWorkSource, LossDropsOnlyANotification, exempt_due_work_suite

_BOARDS: list[Noticeboard] = []
_READERS: list[sqlite3.Connection] = []
_SENT: dict[int, str] = {}


@pytest.fixture
def noticeboard(tmp_path: Path) -> Iterator[None]:
    # ARRANGE: a file-backed noticeboard and an independent reader connection.
    # EXTERNAL SEAM: drop the queue wakeup, record actual provider deliveries.
    path = tmp_path / "notices.sqlite"
    db, reader = sqlite3.connect(path), sqlite3.connect(path)
    _SENT.clear()
    _BOARDS.append(Noticeboard(db, defer_notice=lambda identity: None, send=_SENT.__setitem__))
    _READERS.append(reader)
    try:
        yield
    finally:
        _BOARDS.pop()
        _READERS.pop().close()
        db.close()


def current_board() -> Noticeboard:
    assert _BOARDS, "the notification probe runs inside the noticeboard fixture"
    return _BOARDS[-1]


def product(identity: int) -> str | None:
    # OBSERVE: committed product state, from a connection that never writes it.
    row = _READERS[-1].execute("SELECT title FROM notices WHERE id=?", (identity,)).fetchone()
    return row[0] if row is not None else None


OPTIONAL_ALERT = LossDropsOnlyANotification(
    # REAL PRODUCTION: the producer commits the title before queueing; the worker only sends it.
    strand=lambda: Noticeboard.publish(current_board(), "New opening hours"),
    notified=_SENT.get,
    product=product,
    deliver=lambda identity: Noticeboard.notify(current_board(), identity),
)


@pytest.mark.usefixtures("noticeboard")
@exempt_due_work_suite(
    DueWorkSource(Noticeboard.publish),
    reason="Publishing commits the complete notice; the optional alert neither finishes nor changes that notice.",
    prove=OPTIONAL_ALERT,
)
class TestOptionalAlert:
    pass


@pytest.mark.usefixtures("noticeboard")
def test_exemption_rejects_a_worker_that_changes_product_state(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Noticeboard.notify

    def editing_worker(board: Noticeboard, identity: int) -> None:
        original(board, identity)
        with board.db:
            board.db.execute("UPDATE notices SET title='worker-edited' WHERE id=?", (identity,))

    monkeypatch.setattr(Noticeboard, "notify", editing_worker)
    with pytest.raises(AssertionError, match="does more than notify"):
        OPTIONAL_ALERT()
