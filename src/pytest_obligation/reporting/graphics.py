"""Compose fixed SVG glyphs; no report-specific files or image service are needed."""

from collections.abc import Mapping
from html import escape

from .evidence import cell

#: The contract-check categories, in display order; each check counts in exactly one of the first four.
METRICS = ("passed", "failed", "blocked", "gaps", "rejected")
#: Every headline count's name, as alt text and plain text say it.
LABELS = {
    "applications": "applications",
    "passed": "contract checks passed",
    "failed": "contract failures",
    "blocked": "blocked checks",
    "gaps": "coverage gaps",
    "rejected": "rejected bindings",
    "skipped": "skipped tests",
}


def _picture(base: str, name: str, width: int, height: int, alt: str = "") -> str:
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="{base}{name}-dark.svg">'
        f'<img src="{base}{name}-light.svg" width="{width}" height="{height}" '
        f'alt="{escape(alt, quote=True)}" align="middle"></picture>'
    )


def _space(base: str, width: int, height: int = 36) -> str:
    if width <= 0:
        return ""
    return f'<picture><img src="{base}space.svg" width="{width}" height="{height}" alt="" align="middle"></picture>'


def _number(base: str, value: int, color: str, width: int, height: int, label: str) -> str:
    # Only the first digit carries the complete accessible count, avoiding digit-by-digit reading.
    return "".join(
        _picture(base, f"{color}-{digit}", width, height, f"{value} {label}" if i == 0 else "")
        for i, digit in enumerate(str(value))
    )


def count_text(value: int | None) -> str:
    """A count as text: unknown reads ``?``, never ``0``."""
    return "?" if value is None else str(value)


def _unknown(base: str, width: int, height: int, label: str) -> str:
    """The amber question mark: a count that is not known, at the size of the digits beside it."""
    return _picture(base, "warning-unknown", width, height, f"{label}: unknown")


def _color(kind: str, value: int) -> str:
    if kind in ("applications", "skipped"):
        return "neutral"
    if kind == "passed" or value == 0:
        return "good"
    return "warning" if kind in ("blocked", "gaps") else "bad"


def _count(base: str, key: str, value: int | None, width: int, label: str, *, neutral: bool = False) -> str:
    """One count's glyphs, digits ``width`` wide: the amber ``?`` when unknown, else colored by category."""
    if value is None:
        return _unknown(base, width, width * 2, label)
    return _number(base, value, "neutral" if neutral and value == 0 else _color(key, value), width, width * 2, label)


def summary_html(values: Mapping[str, int | None], base: str, *, neutral: bool = False) -> str:
    """The headline counts; ``skipped`` joins them when present. ``neutral`` shows zeros without green."""
    keys = ("applications", *METRICS, *(("skipped",) if "skipped" in values else ()))
    positions, captions = (
        ((0, 87, 193, 279, 372, 462, 553, 640), "captions-with-skips")
        if "skipped" in values
        else ((0, 107, 235, 339, 442, 546, 640), "captions")
    )
    parts = []
    for i, key in enumerate(keys):
        value = values[key]
        digits = len(count_text(value))
        # The passed column gives up room for the divider that follows it.
        available = positions[i + 1] - positions[i] - (13 if i == 1 else 0)
        width = min(18, available // digits)
        if width < 1:
            return escape(" · ".join(f"{count_text(values[k])} {LABELS[k]}" for k in keys))
        parts.append(_count(base, key, value, width, LABELS[key], neutral=neutral))
        end = positions[i] + digits * width
        if i == 1:
            parts += [_space(base, positions[2] - 13 - end), _picture(base, "divider", 1, 36), _space(base, 12)]
        else:
            parts.append(_space(base, positions[i + 1] - end))
    return (
        "<p>"
        + "".join(parts)
        + "<br>"
        + _picture(base, captions, 640, 34, " · ".join(LABELS[k] for k in keys))
        + "</p>"
    )


def application_name(name: str) -> str:
    # Native text can wrap without changing image URLs or squeezing the count columns.
    clean = " ".join(name.split())[:700]
    return "&#8203;".join(cell(clean[start : start + 24]) for start in range(0, len(clean), 24))


def application_html(name: str, values: Mapping[str, int | None], base: str) -> str:
    native_name = f"<strong>{application_name(name)}</strong>"
    label_widths = (37, 33, 44, 27, 48)
    columns = (82, 81, 88, 74, 90)
    parts = []
    for i, key in enumerate(METRICS):
        value = values[key]
        digits = len(count_text(value))
        width = min(8, (columns[i] - label_widths[i]) // digits)
        if width < 1:
            return native_name + " · " + escape(" · ".join(f"{count_text(values[k])} {k}" for k in METRICS))
        parts += [
            _count(base, key, value, width, key),
            _picture(base, f"label-{key}", label_widths[i], 18),
            _space(base, columns[i] - digits * width - label_widths[i], 18),
        ]
        if i == 0:
            parts += [_picture(base, "divider", 1, 22), _space(base, 12, 18)]
    return native_name + '<div align="right">' + "".join(parts) + "</div>"
