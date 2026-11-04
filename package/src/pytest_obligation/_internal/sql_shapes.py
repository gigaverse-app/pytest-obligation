"""
Name a SQL statement by what it does to which table, from its tokens rather than its text.

Captured SQL can carry the row values a driver spliced in (psycopg 3 binds on the
client, so Django reports the final query). A value such as ``'waiting for
update'`` or ``'('`` must never be read as SQL, so literals become opaque tokens
first. Quoted identifiers stay whole, dots and spaces included. Every structural
decision then reads only the outermost level of the main statement.
"""

import re
from dataclasses import dataclass
from typing import Literal

TokenKind = Literal["word", "name", "literal", "open", "close", "other"]

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")
_LOCK_STRENGTH = {"UPDATE", "SHARE", "NO", "KEY"}
_SET_OPERATIONS = {"UNION", "INTERSECT", "EXCEPT"}
_MAIN_VERBS = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"}
_WRITES = {"insert", "update", "delete", "merge"}


class UnclassifiedStatement(AssertionError):
    """A strict caller met a statement the classifier cannot name by verb and table."""


@dataclass(frozen=True, slots=True)
class _Token:
    kind: TokenKind
    text: str
    depth: int
    start: int
    end: int

    @property
    def upper(self) -> str:
        return self.text.upper() if self.kind == "word" else ""


def _quoted_end(sql: str, start: int, quote: str, *, backslash: bool) -> int:
    """The index after a quoted run opened at ``start``; a doubled quote is part of it."""
    index = start + 1
    while index < len(sql):
        char = sql[index]
        if backslash and char == "\\":
            index += 2
            continue
        if char == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def _tokens(sql: str) -> list[_Token]:
    tokens: list[_Token] = []
    depth = 0
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        # Comments are whitespace: a ``/* FOR UPDATE */`` locks nothing.
        if sql.startswith("--", index):
            newline = sql.find("\n", index)
            index = len(sql) if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", index):
            closing = sql.find("*/", index + 2)
            index = len(sql) if closing < 0 else closing + 2
            continue
        start = index
        kind: TokenKind
        if char in "eE" and index + 1 < len(sql) and sql[index + 1] == "'":
            index, kind = _quoted_end(sql, index + 1, "'", backslash=True), "literal"
        elif char == "'":
            index, kind = _quoted_end(sql, index, "'", backslash=False), "literal"
        elif char == '"':
            index, kind = _quoted_end(sql, index, '"', backslash=False), "name"
        elif char == "$" and (tag := _DOLLAR_TAG.match(sql, index)):
            closing = sql.find(tag.group(0), tag.end())
            index, kind = (len(sql) if closing < 0 else closing + len(tag.group(0))), "literal"
        elif match := _WORD.match(sql, index):
            index, kind = match.end(), "word"
        elif char == "(":
            tokens.append(_Token("open", char, depth, start, start + 1))
            depth += 1
            index += 1
            continue
        elif char == ")":
            depth = max(depth - 1, 0)
            tokens.append(_Token("close", char, depth, start, start + 1))
            index += 1
            continue
        else:
            index, kind = index + 1, "other"
        tokens.append(_Token(kind, sql[start:index], depth, start, index))
    return tokens


def _group(tokens: list[_Token], open_at: int) -> list[_Token]:
    """The tokens inside the parenthesis opened at ``open_at``, re-leveled to depth 0."""
    base = tokens[open_at].depth + 1
    inside: list[_Token] = []
    for token in tokens[open_at + 1 :]:
        if token.kind == "close" and token.depth == base - 1:
            break
        inside.append(_Token(token.kind, token.text, token.depth - base, token.start, token.end))
    return inside


def _name(tokens: list[_Token], at: int) -> tuple[str, int] | None:
    """A possibly schema-qualified relation name starting at ``at``: its last part and where it ends."""
    if at < len(tokens) and tokens[at].upper == "ONLY":
        at += 1
    parts: list[str] = []
    while at < len(tokens) and tokens[at].kind in ("word", "name"):
        token = tokens[at]
        parts.append(token.text[1:-1].replace('""', '"') if token.kind == "name" else token.text)
        if at + 1 < len(tokens) and tokens[at + 1].text == "." and tokens[at + 1].kind == "other":
            at += 2
            continue
        return parts[-1], at + 1
    return None


def _top(tokens: list[_Token]) -> list[tuple[int, _Token]]:
    return [(index, token) for index, token in enumerate(tokens) if token.depth == 0]


def _select_source(tokens: list[_Token]) -> str | None:
    """The first relation the outermost FROM of a SELECT reads, looking into a FROM (subquery)."""
    for index, token in _top(tokens):
        if token.upper in _SET_OPERATIONS:
            return None
        if token.upper == "FROM":
            if index + 1 < len(tokens) and tokens[index + 1].kind == "open":
                inner = _group(tokens, index + 1)
                return _select_source(inner) if inner else None
            named = _name(tokens, index + 1)
            return named[0] if named else None
    return None


def _first_branch(tokens: list[_Token]) -> list[_Token]:
    """The statement itself, or the first branch of a parenthesized set operation."""
    while tokens and tokens[0].kind == "open":
        tokens = _group(tokens, 0)
    return tokens


def _expression(sql: str, tokens: list[_Token]) -> str:
    """A table-less SELECT's outermost expression: literals as ``?``, nested parts elided."""
    pieces: list[str] = []
    cursor = tokens[0].start if tokens else 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        pieces.append(sql[cursor : token.start])
        cursor = token.end
        if token.kind == "literal":
            pieces.append("?")
        elif token.kind == "open":
            inner = _group(tokens, index)
            pieces.append("(…)" if inner else "()")
            index += len(inner) + 1
            cursor = tokens[index].end if index < len(tokens) else len(sql)
        else:
            pieces.append(token.text)
        index += 1
    return " ".join("".join(pieces).split()).lower()


def statement_shape(sql: str, *, strict: bool = False) -> str:
    """
    What one SQL statement does, to which table: ``read orders``, ``lock work``, ``commit``.

    Only the outermost statement is named: a subquery, join, CTE body or a
    literal inside it is part of the statement, not a round trip of its own.
    A ``WITH`` is named by its main statement, a ``FROM (subquery)`` by the
    relation the subquery reads, and a parenthesized set operation by its first
    branch. A SELECT without a table names its expression with literals as
    ``?`` and nested parts elided, so ``SELECT clock_timestamp()`` is ``select
    clock_timestamp()``. A SELECT over a CTE takes the CTE body's shape, so
    ``WITH w AS (SELECT … FROM work FOR UPDATE) SELECT * FROM w`` is ``lock
    work``. ``strict`` raises :class:`UnclassifiedStatement` for anything else
    instead of naming it by its first words.
    """
    return _shape(sql, _tokens(sql.strip().rstrip(";")), strict, {})


def _common_table_expressions(tokens: list[_Token], before: int) -> dict[str, list[_Token]]:
    """``WITH name [(columns)] AS [NOT] [MATERIALIZED] (body), …`` before the main verb: name -> body."""
    bodies: dict[str, list[_Token]] = {}
    top = [(index, token) for index, token in _top(tokens) if index < before]
    for position, (index, token) in enumerate(top):
        if token.upper != "AS" or position == 0:
            continue
        name_at = position - 1
        if top[name_at][1].kind == "close":
            # Column list: the name precedes its opening parenthesis.
            name_at -= 1
            while name_at > 0 and top[name_at][1].kind != "open":
                name_at -= 1
            name_at -= 1
        named = _name(tokens, top[name_at][0]) if name_at >= 0 else None
        body_at = next((i for i in range(index + 1, len(tokens)) if tokens[i].kind == "open"), None)
        if named is not None and body_at is not None:
            bodies[named[0].lower()] = _group(tokens, body_at)
    return bodies


def _shape(sql: str, tokens: list[_Token], strict: bool, outer: dict[str, list[_Token]]) -> str:
    tokens = _first_branch(tokens)
    words = [token.upper for _, token in _top(tokens) if token.kind == "word"]
    if not words:
        return _unclassified(sql, strict)
    first = words[0]
    if first in ("BEGIN", "START"):
        return "begin"
    if first in ("COMMIT", "END"):
        return "commit"
    if first == "ROLLBACK":
        return "rollback to savepoint" if "TO" in words[1:3] else "rollback"
    if first == "SAVEPOINT":
        return "savepoint"
    if first == "RELEASE":
        return "release savepoint"
    main_at = next(
        (index for index, token in _top(tokens) if token.upper in _MAIN_VERBS),
        None,
    )
    if main_at is None:
        return _unclassified(sql, strict)
    ctes = {**outer, **_common_table_expressions(tokens, main_at)}
    verb = tokens[main_at].upper
    rest = tokens[main_at + 1 :]
    if verb == "UPDATE":
        return _relation("update", _name(rest, 0), sql, strict)
    if verb in ("INSERT", "MERGE"):
        into = next((i for i, token in _top(rest) if token.upper == "INTO"), None)
        return _relation(verb.lower(), _name(rest, into + 1) if into is not None else None, sql, strict)
    if verb == "DELETE":
        source = next((i for i, token in _top(rest) if token.upper == "FROM"), None)
        return _relation("delete", _name(rest, source + 1) if source is not None else None, sql, strict)
    statement = tokens[main_at:]
    for name, body in _common_table_expressions(tokens, main_at).items():
        # PostgreSQL runs a data-modifying CTE whether or not the main query reads it: the trip is the write.
        written = _shape(sql, body, strict, {other: tokens for other, tokens in ctes.items() if other != name})
        if written.partition(" ")[0] in _WRITES:
            return written
    source = _select_source(statement)
    if source is None:
        if any(token.upper == "FROM" for _, token in _top(statement)):
            return _unclassified(sql, strict)
        return "select " + _expression(sql, statement[1:])
    top = _top(statement)
    locked = any(
        token.upper == "FOR" and position + 1 < len(top) and top[position + 1][1].upper in _LOCK_STRENGTH
        for position, (_, token) in enumerate(top)
    )
    counted = any(
        (token.upper == "COUNT" and index + 1 < len(statement) and statement[index + 1].kind == "open")
        or (token.upper == "GROUP" and position + 1 < len(top) and top[position + 1][1].upper == "BY")
        for position, (index, token) in enumerate(top)
    )
    body = ctes.get(source.lower())
    if body is not None:
        # Reading a CTE is doing what its body does: its lock, its write, its table.
        inner = _shape(sql, body, strict, {name: tokens for name, tokens in ctes.items() if name != source.lower()})
        _, _, inner_table = inner.partition(" ")
        if inner_table and (locked or counted):
            return f"{'lock' if locked else 'count'} {inner_table}"
        return inner
    if locked:
        return f"lock {source}"
    return f"{'count' if counted else 'read'} {source}"


def _relation(verb: str, named: tuple[str, int] | None, sql: str, strict: bool) -> str:
    return f"{verb} {named[0]}" if named else _unclassified(sql, strict)


def _unclassified(sql: str, strict: bool) -> str:
    if strict:
        raise UnclassifiedStatement(f"cannot name this statement by verb and table: {sql[:200]}")
    words = [token.text for token in _tokens(sql) if token.kind in ("word", "other") and token.depth == 0]
    return " ".join(words[:2]).lower() or "statement"
