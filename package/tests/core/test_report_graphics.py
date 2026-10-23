"""Report graphics preserve readable evidence and contain application text safely."""

import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pytest_obligation.profiles.coverage import CaseEvidence, SuiteCoverage
from pytest_obligation.reporting.graphics import application_svg, summary_svg


@pytest.mark.parametrize("dark", [False, True])
def test_summary_retains_all_counts_and_colors_zero_issues_as_good(dark: bool) -> None:
    values = dict(applications=3, passed=251, failed=2, blocked=0, gaps=2, rejected=1)
    root = ElementTree.fromstring(summary_svg(values, dark=dark))
    texts = {n.attrib.get("id"): n for n in root.iter("{http://www.w3.org/2000/svg}text")}
    for key, value in values.items():
        assert texts[key].text == str(value)
    assert texts["blocked"].attrib["fill"] == texts["passed"].attrib["fill"]
    assert texts["failed"].attrib["fill"] != texts["passed"].attrib["fill"]
    assert texts["gaps"].attrib["fill"] not in (texts["passed"].attrib["fill"], texts["failed"].attrib["fill"])


def test_application_name_cannot_introduce_svg_elements_or_links() -> None:
    name = '<script>alert("x")</script> & orders'
    source = application_svg(name, dict(passed=42, failed=2, blocked=0, gaps=0, rejected=0), dark=True)
    root = ElementTree.fromstring(source)
    assert name in "".join(root.itertext())
    assert not list(root.iter("{http://www.w3.org/2000/svg}script"))
    assert "href=" not in source


def test_application_metrics_do_not_shift_with_the_name() -> None:
    values = dict(passed=42, failed=2, blocked=0, gaps=0, rejected=0)
    positions = []
    for name in ("orders", "billing callbacks", "example catalog"):
        root = ElementTree.fromstring(application_svg(name, values, dark=True))
        texts = {n.attrib.get("id"): n for n in root.iter("{http://www.w3.org/2000/svg}text")}
        assert texts["application"].text == name
        positions.append([texts[key].attrib["x"] for key in values])
        assert "applications" not in texts
    assert positions[0] == positions[1] == positions[2]


def test_cli_produces_graphics_and_a_complete_network_free_fallback(tmp_path: Path) -> None:
    case = CaseEvidence(family="replay", collected=True, selected=True, outcomes={"call": ["failed"]})
    suite = SuiteCoverage(name="order receipts", profiles={}, additional_cases={"replay": case})
    source, output = tmp_path / "evidence.json", tmp_path / "report.md"
    source.write_text(json.dumps({"tests.Orders": suite.model_dump()}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest_obligation.reporting",
            "--input",
            str(source),
            "--output",
            str(output),
            "--graphics",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    fallback = output.read_text(encoding="utf-8")
    assert "order receipts" in fallback and "1 failures" in fallback
    assert "pytest-obligation.invalid" not in fallback and "shields.io" not in fallback
    bundle = json.loads(output.with_suffix(".graphics.json").read_text(encoding="utf-8"))
    assert bundle["version"] == 1 and len(bundle["assets"]) == 4
    assert "1 failures" in bundle["markdown"]
    for svg in bundle["assets"].values():
        ElementTree.fromstring(svg)
