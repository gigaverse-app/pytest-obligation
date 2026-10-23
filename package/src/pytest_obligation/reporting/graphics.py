"""Small, self-contained SVGs for typography GitHub Markdown cannot express."""

from html import escape

LABELS = {
    "applications": "Applications",
    "passed": "Checks passed",
    "failed": "Failures",
    "blocked": "Blocked checks",
    "gaps": "Coverage gaps",
    "rejected": "Rejected bindings",
}


def _palette(dark: bool) -> dict[str, str]:
    return (
        dict(
            ink="#e6edf3",
            quiet="#9da7b3",
            line="#30363d",
            green="#7ee787",
            red="#ff9492",
            amber="#e3b341",
            code="#151b23",
        )
        if dark
        else dict(
            ink="#1f2328",
            quiet="#59636e",
            line="#d1d9e0",
            green="#176f2c",
            red="#b42324",
            amber="#865900",
            code="#f6f8fa",
        )
    )


def _color(kind: str, value: int, colors: dict[str, str]) -> str:
    if kind == "applications":
        return colors["ink"]
    if kind == "passed" or value == 0:
        return colors["green"]
    return colors["red" if kind in ("failed", "rejected") else "amber"]


def _text(value: str, x: float, y: int, size: int, color: str, *, identifier: str = "", weight: int = 400) -> str:
    return (
        f'<text id="{identifier}" x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}">{escape(value)}</text>'
    )


def _svg(parts: list[str], height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{height}" viewBox="0 0 680 {height}" '
        'role="img" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">'
        f"<title>{escape(title)}</title>" + "".join(parts) + "</svg>"
    )


def summary_svg(values: dict[str, int], *, dark: bool) -> str:
    colors = _palette(dark)
    parts = [f'<path d="M236 4v56" stroke="{colors["line"]}"/>']
    for (kind, label), x in zip(LABELS.items(), (0, 114, 250, 360, 470, 580), strict=True):
        value = values[kind]
        size = 28 if len(str(value)) < 7 else 20
        parts += [
            _text(str(value), x, 32, size, _color(kind, value, colors), identifier=kind, weight=600),
            _text(label, x, 56, 12, colors["quiet"]),
        ]
    return _svg(parts, 76, " · ".join(f"{values[k]} {label.lower()}" for k, label in LABELS.items()))


def application_svg(name: str, values: dict[str, int], *, dark: bool) -> str:
    colors = _palette(dark)
    display = name if len(name) <= 24 else name[:23] + "…"
    parts = [
        f'<rect x="0" y="9" width="{min(164, len(display) * 7 + 10)}" height="23" rx="4" fill="{colors["code"]}"/>',
        '<g font-family="ui-monospace,SFMono-Regular,Consolas,monospace">',
        _text(display, 5, 25, 12, colors["ink"], identifier="application", weight=600),
        "</g>",
        f'<path d="M258 10v22" stroke="{colors["line"]}"/>',
    ]
    for kind, x in zip((k for k in LABELS if k != "applications"), (174, 270, 370, 470, 570), strict=True):
        value = str(values[kind])
        size = 14 if len(value) <= 6 else 10
        parts += [
            _text(value, x, 25, size, _color(kind, values[kind], colors), identifier=kind, weight=600),
            _text(kind, x + len(value) * size * 0.61 + 4, 25, 11, colors["quiet"]),
        ]
    return _svg(parts, 40, name + " · " + " · ".join(f"{v} {k}" for k, v in values.items()))
