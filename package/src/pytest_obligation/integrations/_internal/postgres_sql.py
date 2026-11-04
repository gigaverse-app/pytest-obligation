"""Lexical SQL normalization shared by plan verdicts and lock-order observation.

This masks literals and comments without importing Django or a database driver.
It is a bounded lexical reader, not a PostgreSQL parser or a query validator.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

_DOLLAR_TAG = re.compile(r"\$(?:[^\W\d]\w*)?\$")
_WORD = re.compile(r"[^\W\d][\w$]*")
_NAME = re.compile(r'"((?:[^"]|"")*)"|(\w+)')

LexemeKind = Literal["comment", "literal", "name", "word", "other"]


@dataclass(frozen=True, slots=True)
class Lexeme:
    """One lexical unit of a statement: what it is and where it sits."""

    kind: LexemeKind
    start: int
    end: int


def lexemes(sql: str) -> Iterator[Lexeme]:
    """
    Every lexical unit of ``sql`` except whitespace, in order: the one reading of its comments, literals and names.

    Block comments nest, as PostgreSQL's do. A plain literal only doubles its
    quote; an ``E''`` literal (``E`` as a word of its own) also takes backslash
    escapes, and its prefix belongs to it. A quoted identifier keeps doubled
    quotes inside it. An unterminated run ends at the end of the statement.
    Anything else is one ``other`` character.
    """
    index = 0
    while index < len(sql):
        char = sql[index]
        kind: LexemeKind
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index)
            end, kind = (len(sql) if newline < 0 else newline), "comment"
        elif sql.startswith("/*", index):
            end, kind = _block_comment_end(sql, index), "comment"
        elif char == "'":
            end, kind = _quoted_end(sql, index, "'", backslash=False), "literal"
        elif char == '"':
            end, kind = _quoted_end(sql, index, '"', backslash=False), "name"
        elif tag := _DOLLAR_TAG.match(sql, index):
            closing = sql.find(tag.group(), tag.end())
            end, kind = (len(sql) if closing < 0 else closing + len(tag.group())), "literal"
        elif word := _WORD.match(sql, index):
            end, kind = word.end(), "word"
            if end == index + 1 and char in "Ee" and sql.startswith("'", end):
                end, kind = _quoted_end(sql, end, "'", backslash=True), "literal"
        else:
            end, kind = index + 1, "other"
        yield Lexeme(kind, index, end)
        index = end


def _block_comment_end(sql: str, start: int) -> int:
    end, depth = start + 2, 1
    while end < len(sql) and depth:
        if sql.startswith("/*", end):
            depth, end = depth + 1, end + 2
        elif sql.startswith("*/", end):
            depth, end = depth - 1, end + 2
        else:
            end += 1
    return end


def _quoted_end(sql: str, start: int, quote: str, *, backslash: bool) -> int:
    """The index after a quoted run opened at ``start``; a doubled quote is part of it."""
    index = start + 1
    while index < len(sql):
        if backslash and sql[index] == "\\":
            index += 2
        elif sql.startswith(quote * 2, index):
            index += 2
        elif sql[index] == quote:
            return index + 1
        else:
            index += 1
    return len(sql)


def blank_literals_and_comments(sql: str) -> str:
    """
    The statement with string literals, dollar quotes and comments blanked out, so their text opens nothing.

    Quoted identifiers are kept: they are the table names. Blanking keeps every
    other character where it was.
    """
    out = list(sql)
    for lexeme in lexemes(sql):
        if lexeme.kind in ("comment", "literal"):
            out[lexeme.start : lexeme.end] = " " * (lexeme.end - lexeme.start)
    return "".join(out)


def bare_identifiers(sql: str) -> str:
    """
    SQL text with literals and comments blanked, and each quoted identifier reduced to its bare name.

    For a reader that matches column names with a word pattern: a column named
    only inside a string literal (``'available_at <= soon'``) is no column, and a
    quoted identifier that is a plain word (``"order"``) is the same column bare.
    One that is not a plain word (``"odd name"``) is blanked, since no word
    pattern can name it faithfully.
    """

    def bare(match: re.Match[str]) -> str:
        quoted, word = match.group(1), match.group(2)
        if word is not None:
            return word
        quoted = quoted.replace('""', '"')
        return quoted if quoted.isidentifier() else " " * len(match.group(0))

    return _NAME.sub(bare, blank_literals_and_comments(sql))
