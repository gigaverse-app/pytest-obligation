"""Compose fixed SVG glyphs; no report-specific files or image service are needed."""

from collections.abc import Mapping
from html import escape
from unicodedata import combining, east_asian_width

from .evidence import cell, inert

METRICS = ("passed", "failed", "blocked", "gaps", "rejected")
LABELS = ("applications", "checks passed", "failures", "blocked checks", "coverage gaps", "rejected bindings")


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
                _picture(base, "neutral-unknown", 18, 36, f"{label}: unknown"),
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
    return "<p>" + "".join(parts) + "<br>" + _picture(base, captions, 640, 22, " · ".join(labels)) + "</p>"


def application_name(name: str) -> tuple[str, bool]:
    # Keep names in native selectable text, with a fixed monospace column.
    clean = " ".join(name.split())

    def columns(text: str) -> int:
        return sum(0 if combining(c) else 2 if east_asian_width(c) in ("W", "F") else 1 for c in text)

    display = clean
    shortened = columns(display) > 20
    if shortened:
        # Bound the prefix before trimming wide characters, keeping long names linear-time.
        display = display[:20]
        while columns(display) > 19:
            display = display[:-1]
        display += "…"
    title = f' title="{escape(inert(clean[:700]), quote=True)}"' if shortened else ""
    return f"<samp{title}><strong>{cell(display)}</strong>" + "&nbsp;" * (20 - columns(display)) + "</samp>", shortened


def application_html(name: str, values: dict[str, int], base: str) -> str:
    native_name, _ = application_name(name)
    label_widths = (37, 33, 44, 27, 48)
    columns = (82, 81, 88, 74, 90)
    parts = [native_name]
    for i, key in enumerate(METRICS):
        value = values[key]
        width = min(8, (columns[i] - label_widths[i]) // len(str(value)))
        if width < 1:
            return native_name + " · " + escape(" · ".join(f"{values[k]} {k}" for k in METRICS))
        parts += [
            _number(base, value, _color(key, value), width, width * 2, key),
            _picture(base, f"label-{key}", label_widths[i], 18),
            _space(base, columns[i] - len(str(value)) * width - label_widths[i], 18),
        ]
        if i == 0:
            parts += [_picture(base, "divider", 1, 22), _space(base, 12, 18)]
    return "".join(parts)
