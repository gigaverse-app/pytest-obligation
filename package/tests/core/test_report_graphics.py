"""Real reports compose fixed assets without storing evidence in image files."""

import json
import re
import subprocess
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

from pytest_obligation.profiles.coverage import CaseEvidence, SuiteCoverage
from pytest_obligation.reporting.graphics import application_html, summary_html
from pytest_obligation.reporting.inventory import ApplicationInventory
from pytest_obligation.reporting.markdown import render

BASE = "https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/test-ref/docs/assets/report-glyphs/"


@pytest.mark.parametrize(
    "selected,outcomes,skipped",
    [(False, {}, 1), (True, {"setup": ["skipped"]}, 1), (True, {}, 0), (True, {"call": ["xfail"]}, 0)],
)
def test_skipped_tests_counter_is_top_level_and_does_not_count_interruptions(
    selected: bool, outcomes: dict[str, list[str]], skipped: int
) -> None:
    case = CaseEvidence(family="replay", collected=True, selected=selected, outcomes=outcomes)
    suite = SuiteCoverage(name="orders", profiles={}, additional_cases={"replay": case})
    body = render({"tests.Orders": suite}, inventory=ApplicationInventory(), graphics=True)
    headline = body.split("<details>")[0]
    assert f'alt="{skipped} skipped tests"' in headline
    assert "applications not run" not in headline
    assert "Checks skipped:" not in headline
    assert "captions-with-skips" in headline


def image_names(body: str) -> set[str]:
    return {Path(urlparse(unescape(url)).path).name for url in re.findall(r'(?:src|srcset)="([^"]+)"', body)}


def test_changed_counts_only_select_existing_glyphs_and_preserve_status_colors() -> None:
    values = dict(applications=3, passed=251, failed=2, blocked=0, gaps=2, rejected=1)
    before = summary_html(values, BASE)
    after = summary_html(dict(values, passed=1251, failed=0), BASE)
    assert 'alt="251 contract checks passed"' in before
    assert 'alt="1251 contract checks passed"' in after
    assert "bad-2-dark.svg" in before and "good-0-dark.svg" in after
    assert "warning-2-dark.svg" in before
    for body in (before, after):
        assert "<svg" not in body and "?" not in body


def test_names_stay_native_and_cannot_change_image_urls() -> None:
    values = dict(passed=42, failed=2, blocked=0, gaps=0, rejected=0)
    name = '<script>alert("x")</script> & orders'
    body = application_html(name, values, BASE)
    assert "<script>" not in body and "&lt;script&gt;" in body
    assert image_names(body) == image_names(application_html("orders", values, BASE))
    assert unescape(body).replace("\u200b", "").count(name) == 1


def test_application_names_remain_complete_with_the_counts_aligned_right() -> None:
    name = "Noticeboard.publish_notification_after_recovering_pending_delivery"
    body = application_html(name, dict(passed=42, failed=2, blocked=0, gaps=0, rejected=0), BASE)
    assert name in unescape(body).replace("\u200b", "")
    assert "…" not in body
    assert '<div align="right">' in body
    assert body.index("Noticeboard") < body.index('<div align="right">')
    assert "good-4-" in body and "bad-2-" in body


@pytest.mark.parametrize("attempt,label", [(1, "run"), (2, "run 2"), (3, "run 3")])
def test_run_link_is_a_short_footer_label(attempt: int, label: str) -> None:
    url = f"https://github.com/owner/project/actions/runs/7/attempts/{attempt}"
    body = render({}, run_url=url)
    assert f"[{label}]({url})" in body.split("</details>")[-1]
    assert "Workflow run" not in body


def test_wide_counts_remain_exact_and_never_produce_negative_spacing() -> None:
    values = dict(passed=1234567, failed=0, blocked=0, gaps=0, rejected=0)
    body = application_html("orders", values, BASE)
    assert 'alt="1234567 passed"' in body
    assert 'width="-' not in body


def test_numeric_columns_stay_fixed_when_counts_gain_digits() -> None:
    class Images(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.x = 0
            self.columns: list[int] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag != "img":
                return
            values = dict(attrs)
            if values.get("alt"):
                self.columns.append(self.x)
            self.x += int(values.get("width") or "0")

    positions = []
    for passed in (42, 1042, 1234567):
        parser = Images()
        parser.feed(
            application_html("order receipts", dict(passed=passed, failed=2, blocked=0, gaps=0, rejected=0), BASE)
        )
        positions.append(parser.columns)
    assert positions[0] == positions[1] == positions[2]


def test_application_names_cannot_create_markdown_links_or_mentions() -> None:
    body = application_html("@team [x](https://x)", dict(passed=0, failed=0, blocked=0, gaps=0, rejected=0), BASE)
    # GitHub decodes "&#64;team" back into a mention, so the check reads the body as GitHub does.
    assert "&#91;x&#93;" in body
    assert "@team" not in unescape(body) and "https://x" not in unescape(body)


def test_cli_writes_one_markdown_report_without_a_graphics_bundle(tmp_path: Path) -> None:
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
    body = output.read_text(encoding="utf-8")
    assert "order receipts" in body and 'alt="1 contract failures"' in body
    assert "/report-glyphs/" in body
    assert not output.with_suffix(".graphics.json").exists()
    assert {p.name for p in tmp_path.iterdir()} == {"evidence.json", "report.md"}


def test_large_reports_keep_graphical_headline_and_aligned_application_overview() -> None:
    suites = {str(i): SuiteCoverage(name=f"application {i}", profiles={}) for i in range(37)}
    body = render(suites, graphics=True)
    assert len(body) <= 55_000 and "report-glyphs" in body
    assert 'alt="37 applications"' in body
    assert "| Application | Passed | Failed | Blocked | Gaps | Rejected |" in body
    assert all(f"| application {i} |" in body for i in range(37))
    assert body.count("<details>") == body.count("</details>")


def test_detail_overflow_cannot_remove_application_overview_or_graphical_totals() -> None:
    from tests.core.test_report_debt import specimen

    suites = {}
    for index in range(100):
        suite = specimen()
        suite.name = f"application {index}"
        for profile in suite.profiles.values():
            profile.assessment = profile.assessment.model_copy(update={"because": "Long application decision. " * 40})
        suites[str(index)] = suite
    body = render(suites, graphics=True)
    assert len(body) <= 55_000
    assert 'alt="100 applications"' in body
    assert all(f"| application {i} |" in body for i in range(100))
    assert "omitted" in body
    assert "Known defects" in body and "Unassessed guarantees" in body and "Deliberate exclusions" in body
    assert "](https://linear.app/example/issue/BE-1)" in body
    assert body.count("<details>") == body.count("</details>")


def test_application_disclosures_have_markdown_block_boundaries() -> None:
    suites = {str(i): SuiteCoverage(name=f"application {i}", profiles={}) for i in range(3)}
    body = render(suites, graphics=True)
    assert "</details>\n---" not in body


def test_failed_test_step_precedes_branding_and_preserves_colored_contract_counts() -> None:
    case = CaseEvidence(
        family="replay",
        collected=True,
        selected=True,
        outcomes={phase: ["passed"] for phase in ("setup", "call", "teardown")},
    )
    failed = case.model_copy(update={"outcomes": {"setup": ["passed"], "call": ["failed"], "teardown": ["passed"]}})
    suite = SuiteCoverage(name="orders", profiles={}, additional_cases={"replay": case, "broken": failed})
    body = render({"tests.Orders": suite}, graphics=True, test_outcome="failure")
    assert body.startswith("## 🔴 Test step failed")
    assert 'alt="1 contract failures"' in body
    assert 'alt="1 contract checks passed"' in body
    assert "/good-1-" in body and "/bad-1-" in body
    assert "### Obligation contract checks" in body
    assert "Other pytest tests and workflow steps are not included" in body


def test_incomplete_evidence_uses_an_amber_question_mark_for_unknown_counts() -> None:
    body = render({}, graphics=True, test_outcome="failure", unavailable="Expected report is missing.")
    assert 'alt="skipped tests: unknown"' in body
    assert "warning-unknown-light.svg" in body and "warning-unknown-dark.svg" in body
    assert "/good-0-" not in body
    assert "Evidence unavailable" in body


def test_large_overview_folds_clean_apps_and_safely_wraps_long_names() -> None:
    suites = {str(i): SuiteCoverage(name=f"application {i}", profiles={}) for i in range(4)}
    suites["0"].name = "long_application_name_" * 3 + "<script>"
    suites["0"].additional_cases = {
        "bad": CaseEvidence(family="replay", collected=True, selected=True, outcomes={"call": ["failed"]})
    }
    body = render(suites)
    overview = body.split("### Evidence and decisions")[0]
    assert "3 applications · zero failures, blocked checks or gaps" in overview
    assert "&#8203;" in overview and "<script>" not in overview
    assert unescape(overview).index("long_application_name_") < unescape(overview).index("3 applications · zero")
    assert all(f"| application {i} |" in overview for i in range(1, 4))
