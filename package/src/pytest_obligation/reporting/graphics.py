"""Compose fixed SVG glyphs; no report-specific files or image service are needed."""

from collections.abc import Mapping
from html import escape

from .evidence import cell

METRICS = ("passed", "failed", "blocked", "gaps", "rejected")
LABELS = (
    "applications",
    "contract checks passed",
    "contract failures",
    "blocked checks",
    "coverage gaps",
    "rejected bindings",
)


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


def _color(kind: str, value: int) -> str:
    if kind == "applications":
        return "neutral"
    if kind == "passed" or value == 0:
        return "good"
    return "warning" if kind in ("blocked", "gaps") else "bad"


def summary_html(values: Mapping[str, int | None], base: str, *, neutral: bool = False) -> str:
    keys = ("applications", *METRICS)
    labels = LABELS
    positions = (0, 107, 235, 339, 442, 546, 640)
    captions = "captions"
    if "skipped" in values:
        keys = (*keys, "skipped")
        labels = (*labels, "skipped tests")
        positions = (0, 87, 193, 279, 372, 462, 553, 640)
        captions = "captions-with-skips"
    parts = []
    for i, (key, label) in enumerate(zip(keys, labels, strict=True)):
        value = values[key]
        if value is None:
            parts += [
                _picture(base, "warning-unknown", 18, 36, f"{label}: unknown"),
                _space(base, positions[i + 1] - positions[i] - 18),
            ]
            continue
        available = positions[i + 1] - positions[i] - (13 if i == 1 else 0)
        width = min(18, available // len(str(value)))
        if width < 1:
            return escape(" · ".join(f"{values[k]} {label}" for k, label in zip(keys, labels, strict=True)))
        parts.append(
            _number(
                base,
                value,
                "neutral" if key == "skipped" or neutral and value == 0 else _color(key, value),
                width,
                width * 2,
                label,
            )
        )
        end = positions[i] + len(str(value)) * width
        if i == 1:
            parts += [_space(base, positions[2] - 13 - end), _picture(base, "divider", 1, 36), _space(base, 12)]
        else:
            parts.append(_space(base, positions[i + 1] - end))
    return "<p>" + "".join(parts) + "<br>" + _picture(base, captions, 640, 34, " · ".join(labels)) + "</p>"


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
        if value is None:
            # Unknown, not zero: the same amber question mark as the headline, at the row's digit size.
            parts += [
                _picture(base, "warning-unknown", 8, 16, f"{key}: unknown"),
                _picture(base, f"label-{key}", label_widths[i], 18),
                _space(base, columns[i] - 8 - label_widths[i], 18),
            ]
            if i == 0:
                parts += [_picture(base, "divider", 1, 22), _space(base, 12, 18)]
            continue
        width = min(8, (columns[i] - label_widths[i]) // len(str(value)))
        if width < 1:
            return (
                native_name
                + " · "
                + escape(" · ".join(f"{'?' if values[k] is None else values[k]} {k}" for k in METRICS))
            )
        parts += [
            _number(base, value, _color(key, value), width, width * 2, key),
            _picture(base, f"label-{key}", label_widths[i], 18),
            _space(base, columns[i] - len(str(value)) * width - label_widths[i], 18),
        ]
        if i == 0:
            parts += [_picture(base, "divider", 1, 22), _space(base, 12, 18)]
    return native_name + '<div align="right">' + "".join(parts) + "</div>"
