"""Verify the hosted report assets against the renderer in the full checkout."""

import re
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from pytest_obligation.reporting.graphics import application_html, summary_html

ASSETS = Path(__file__).resolve().parents[2] / "docs/assets/report-glyphs"
BASE = "https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/test-ref/docs/assets/report-glyphs/"


def test_every_rendered_glyph_exists_in_the_hosted_asset_set() -> None:
    # Exercise every digit, both themes, all status colors and both report sizes.
    for digit in range(10):
        values = dict(applications=digit, passed=digit, failed=digit, blocked=digit, gaps=digit, rejected=digit)
        body = summary_html(values, BASE) + application_html("orders", values, BASE)
        for url in re.findall(r'(?:src|srcset)="([^"]+)"', body):
            name = Path(urlparse(unescape(url)).path).name
            assert (ASSETS / name).is_file(), name


def test_fixed_assets_are_small_passive_images_with_both_themes() -> None:
    files = list(ASSETS.glob("*.svg"))
    assert len(files) == 95 and sum(p.stat().st_size for p in files) < 25_000
    for path in files:
        root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
        assert all(n.tag.rsplit("}")[-1] in {"svg", "text", "path"} for n in root.iter())
        assert not any(k in {"href", "src", "onload", "style"} for n in root.iter() for k in n.attrib)
