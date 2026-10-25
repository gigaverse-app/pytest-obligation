"""Keep a rendered report inside a Markdown document, between two markers the document owns.

A repository can show its latest report in its README: it writes the markers once, and every
run replaces only what lies between them. Text outside the markers is never touched, so the
document can be edited, or merged from upstream, independently of the report.
"""

from pathlib import Path

START = "<!-- pytest-obligation:start -->"
END = "<!-- pytest-obligation:end -->"


def embed(document: str, report: str) -> str:
    """``document`` with the text between its markers replaced by ``report``."""
    if document.count(START) != 1 or document.count(END) != 1 or document.index(START) > document.index(END):
        raise ValueError(f"the document must contain {START} once, followed by {END} once, to receive the report")
    before, _, rest = document.partition(START)
    _, _, after = rest.partition(END)
    return f"{before}{START}\n{report.strip()}\n{END}{after}"


def update(path: Path, report: str) -> bool:
    """Write ``report`` into the document at ``path``; ``False`` when it already held exactly this report."""
    document = path.read_text(encoding="utf-8")
    updated = embed(document, report)
    if updated == document:
        return False
    path.write_text(updated, encoding="utf-8")
    return True
