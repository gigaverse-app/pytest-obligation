"""A published notice is complete even when its optional subscriber alert is lost."""

import sqlite3
from collections.abc import Callable


class Noticeboard:
    """SQLite owns published notices; the queue carries only courtesy alerts."""

    def __init__(
        self, db: sqlite3.Connection, *, defer_notice: Callable[[int], None], send: Callable[[int, str], None]
    ) -> None:
        self.db, self.defer_notice, self.send = db, defer_notice, send
        db.execute("CREATE TABLE notices(id INTEGER PRIMARY KEY, title TEXT NOT NULL)")

    def publish(self, title: str) -> int:
        with self.db:
            row = self.db.execute("INSERT INTO notices(title) VALUES (?) RETURNING id", (title,)).fetchone()
            assert row is not None
            identity = int(row[0])
        self.defer_notice(identity)
        return identity

    def title(self, identity: int) -> str | None:
        row = self.db.execute("SELECT title FROM notices WHERE id=?", (identity,)).fetchone()
        return row[0] if row is not None else None

    def notify(self, identity: int) -> None:
        title = self.title(identity)
        assert title is not None, "a courtesy alert refers to an already published notice"
        self.send(identity, title)
