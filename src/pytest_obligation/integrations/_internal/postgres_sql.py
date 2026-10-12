"""Lexical SQL normalization shared by plan verdicts and lock-order observation.

This masks literals and comments without importing Django or a database driver.
It is a bounded lexical reader, not a PostgreSQL parser or a query validator.
"""

import re

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_]*\$")
_NAME = re.compile(r'"([^"]+)"|(\w+)')


def blank_literals_and_comments(sql: str) -> str:
    """
    The statement with string literals, dollar quotes and comments blanked out, so their text opens nothing.

    Quoted identifiers are kept: they are the table names. Blanking keeps every
    other character where it was.
    """
    out, index = list(sql), 0
    while index < len(sql):
        if sql.startswith("--", index):
            end = sql.find("\n", index)
            end = len(sql) if end < 0 else end
        elif sql.startswith("/*", index):
            end, depth = index + 2, 1
            while end < len(sql) and depth:
                if sql.startswith("/*", end):
                    depth, end = depth + 1, end + 2
                elif sql.startswith("*/", end):
                    depth, end = depth - 1, end + 2
                else:
                    end += 1
        elif sql[index] == "'":
            # An E'' literal takes backslash escapes; a plain one only doubles its quote.
            escapes = (
                index > 0
                and sql[index - 1] in "Ee"
                and (index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] == "_"))
            )
            end = index + 1
            while end < len(sql):
                if escapes and sql[end] == "\\":
                    end += 2
                elif sql[end] == "'" and sql.startswith("''", end):
                    end += 2
                elif sql[end] == "'":
                    end += 1
                    break
                else:
                    end += 1
        elif sql[index] == '"':
            closing = sql.find('"', index + 1)
            index = len(sql) if closing < 0 else closing + 1
            continue
        elif tag := _DOLLAR_TAG.match(sql, index):
            closing = sql.find(tag.group(), tag.end())
            end = len(sql) if closing < 0 else closing + len(tag.group())
        else:
            index += 1
            continue
        out[index:end] = " " * (end - index)
        index = end
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
        return quoted if quoted.isidentifier() else " " * len(match.group(0))

    return _NAME.sub(bare, blank_literals_and_comments(sql))
