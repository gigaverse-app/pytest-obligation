"""GitHub-native sticky layout: aligned summaries, actionable detail on demand."""

import re
from collections import Counter
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

from pytest_obligation.profiles.coverage import ProfileCoverage, SuiteCoverage

from .decisions import decision_sections
from .evidence import (
    GUARANTEES,
    PROJECT,
    _failure_details,
    all_cases,
    case_status,
    cell,
    code,
)
from .evidence import (
    MAX_BODY as MAX_BODY,
)
from .graphics import application_html, application_name, summary_html
from .inventory import ApplicationInventory


def _skipped_checks(
    reports: dict[str, SuiteCoverage], inventory: ApplicationInventory | None, unavailable: str
) -> tuple[int, bool]:
    declared = inventory.applications if inventory else {}
    cases = [case for suite in reports.values() for case in all_cases(suite).values()]
    # Count only known checks with explicit non-execution evidence. Interrupted
    # selected checks and expected failures must not masquerade as skips.
    skipped = sum(
        not case.outcomes
        and (not case.collected or not case.selected)
        or case_status(case) == "Test skipped or incomplete"
        and any("skipped" in outcomes for outcomes in case.outcomes.values())
        for case in cases
    )
    incomplete = bool(unavailable or set(declared) - set(reports) or inventory is None)
    return skipped, incomplete


def _execution_summary(
    reports: dict[str, SuiteCoverage],
    inventory: ApplicationInventory | None,
    unavailable: str,
    collected_skips: int | None = None,
) -> list[str]:
    declared = inventory.applications if inventory else {}
    applications = set(declared) | set(reports)
    observed = {key for key, suite in reports.items() if any(c.outcomes for c in all_cases(suite).values())}
    absent = applications - observed
    unknown = absent if unavailable else set()
    not_run = absent - unknown
    skipped, incomplete = _skipped_checks(reports, inventory, unavailable)
    if collected_skips is not None:
        skipped, incomplete = collected_skips, False
    skip_count = f"**{skipped} known**" if skipped and incomplete else "**unknown**" if incomplete else f"**{skipped}**"
    lines = [
        "<details>",
        "<summary>Application inventory and skipped tests</summary>",
        "",
        f"**{len(observed)}** applications with results · **{len(not_run)}** applications not run"
        + (f" · **{len(unknown)}** unknown" if unknown else ""),
        f"Checks skipped: {skip_count}."
        + (
            " Uncollected applications have no measured test count."
            if incomplete and set(declared) - set(reports)
            else ""
        ),
        "",
    ]
    if not reports:
        lines += ["No application contract checks ran.", ""]
    if absent or inventory is None or inventory.limitations:
        used = 0
        for key in sorted(absent):
            name = declared[key].name if key in declared else reports[key].name
            status = "Unknown: reports incomplete" if key in unknown else "Not run"
            row = f"- **{cell(name)}**: {status}."
            if used + len(row) > MAX_BODY // 3:
                lines.append("Further applications omitted; see the inventory JSON artifact.")
                break
            lines.append(row)
            used += len(row)
        if inventory is None:
            lines.append("Application inventory was not supplied; uncollected suites cannot be listed.")
        else:
            lines += ["", *[cell(limitation) for limitation in inventory.limitations[:10]]]
    lines += ["", "</details>", ""]
    return lines


METRICS = ("passed", "failed", "blocked", "gaps", "rejected")
LABELS = {
    "applications": "Applications",
    "passed": "Checks passed",
    "failed": "Failures",
    "blocked": "Blocked checks",
    "gaps": "Coverage gaps",
    "rejected": "Rejected bindings",
}


def has_gap(profile: ProfileCoverage) -> bool:
    return profile.assessment.state in ("known gap", "not assessed") or (
        profile.assessment.state == "claimed"
        and (
            not profile.cases
            or any(f.state in ("known gap", "not assessed") for f in profile.families.values())
            or any(c.debt and c.debt.kind == "known-defect" for c in profile.cases.values())
        )
    )


def counts(suite: SuiteCoverage) -> dict[str, int]:
    result = dict.fromkeys(METRICS, 0)
    for case in all_cases(suite).values():
        status = case_status(case)
        # Each unique check has exactly one display category. Gaps count guarantees,
        # never hypothetical tests, and do not add to the executed-check total.
        category = (
            "passed"
            if case.passed
            else "rejected"
            if status == "Test binding rejected"
            else "failed"
            if status == "Check failed"
            else "blocked"
        )
        result[category] += 1
    result["gaps"] = sum(has_gap(p) for p in suite.profiles.values())
    return result


def _priority(item: tuple[str, SuiteCoverage]) -> tuple[int, int, str]:
    values = counts(item[1])
    for rank, category in enumerate(("failed", "rejected", "blocked", "gaps")):
        if values[category]:
            return rank, -values[category], item[0]
    return 4, 0, item[0]


def _totals(values: dict[str, int], glyph_base: str, *, neutral: bool = False, skipped: int | None = None) -> str:
    alt = " · ".join(f"{values[kind]} {LABELS[kind].lower()}" for kind in ("applications", *METRICS))
    if not glyph_base:
        return f"**{alt} · {skipped if skipped is not None else '?'} skipped tests**"
    return summary_html({**values, "skipped": skipped}, glyph_base, neutral=neutral)


def _source_link(suite: SuiteCoverage, repository_url: str, revision: str) -> str:
    source = suite.source
    if source is None:
        return "Contract source: not reported."
    label = f"{source.path}:{source.line}"
    path = PurePosixPath(source.path)
    parsed = urlparse(repository_url)
    # Only link safe repository-relative files at an immutable tested revision.
    if (
        not re.fullmatch(r"[0-9a-fA-F]{40}", revision)
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username
        or any(c in repository_url for c in '()<>\r\n"')
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in source.path
        or ":" in source.path
    ):
        return f"Contract {cell(source.kind)}: {code(label)}"
    url = f"{repository_url.rstrip('/')}/blob/{revision}/{quote(source.path, safe='/')}#L{source.line}"
    return f"[View {source.kind}]({url}) · {code(label)} · tested revision"


def _time(suites: list[SuiteCoverage], *, compact: bool = False) -> str:
    cases = [c for s in suites for c in all_cases(s).values() if c.outcomes]
    if not cases or any(not c.durations for c in cases):
        return "Test time: not reported."
    seconds = sum(sum(c.durations) for c in cases)
    if compact:
        return f"{seconds:.1f}s summed check time"
    return f"Test time: **{seconds:.1f}s** summed check time (setup, call and cleanup; parallel work overlaps)."


def _hypothesis(suite: SuiteCoverage) -> list[str]:
    exploration = suite.exploration
    if exploration is None:
        summary, lines = "Not reported", ["This report has no generated exploration evidence."]
    elif not exploration:
        summary, lines = (
            "No generated scenario bindings collected",
            [
                "No optional schedule-exploration cases were collected for this suite. "
                "Other Hypothesis use inside application callbacks is not assessed here."
            ],
        )
    else:
        selected = [c for c in exploration.values() if c.selected]
        summary = f"{sum(c.passed for c in selected)}/{len(selected)} scenario checks passed" if selected else "Not run"
        lines = ["Generated schedule exploration uses the application's scenario bindings.", ""]
        for case in exploration.values():
            status = case_status(case) if case.selected else "Disabled or filtered out"
            lines += [f"- Application scenario {code(case.family)}: **{status}**"]
        lines += [
            "",
            "These counts are scenario checks, not generated examples. "
            "Example counts, shrinking statistics and replay histories are not recorded in this report; "
            "inspect the pytest log for a failing history.",
        ]
    return ["<details>", f"<summary><strong>Hypothesis · {summary}</strong></summary>", "", *lines, "", "</details>"]


def _suite(
    key: str, suite: SuiteCoverage, repository_url: str, revision: str, glyph_base: str, *, compact: bool = False
) -> str:
    values = counts(suite)
    description = " · ".join(f"{values[k]} {LABELS[k].lower()}" for k in METRICS)
    summary = f"{code(suite.name)} · {description}"
    if compact:
        summary = f"<strong>{cell(suite.name, 100)}</strong> · evidence and decisions"
    elif glyph_base:
        summary = application_html(suite.name, values, glyph_base)
    lines = [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        _source_link(suite, repository_url, revision),
        "",
        f"<sub>Test time: {_time([suite], compact=True).removeprefix('Test time: ')}</sub>",
        "",
    ]
    if not compact and glyph_base and application_name(suite.name)[1]:
        lines += [f"Application: {code(suite.name)}", ""]
    if "selection" in suite.profiles:
        lines += [
            "Scope: **Scheduled selection and loop**. Covers the declared query and loop checks; does not establish full automatic recovery (profile A).",
            "",
        ]
    cases = all_cases(suite)
    for title, states in (
        ("Failures", {"Check failed"}),
        ("Rejected bindings", {"Test binding rejected"}),
        (
            "Blocked checks",
            {case_status(c) for c in cases.values()} - {"Passed", "Check failed", "Test binding rejected"},
        ),
    ):
        affected = [
            (name, c)
            for name, c in cases.items()
            if case_status(c) in states
            and not (title == "Blocked checks" and c.debt and case_status(c) == "Expected failure; no passing proof")
        ]
        if not affected:
            continue
        lines += [f"**{len(affected)} {title.lower()}**", ""]
        # Keep the first concrete observation visible, with full traces on demand.
        observations = list(dict.fromkeys(f.message for _, c in affected for f in c.failures))
        lines += [cell(message, 350) + "\n" for message in observations[:2]]
        if title == "Rejected bindings":
            lines += [
                "Connect the binding to production code and rerun. These checks provide no supporting evidence.",
                "",
            ]
        elif title == "Blocked checks":
            lines += [
                "Run the missing checks or repair setup/cleanup. For expected failures whose classification was not reported, update the report producer to include declaration metadata.",
                "",
            ]
        lines += ["<details>", f"<summary><strong>{len(affected)} {title.lower()} · diagnostics</strong></summary>", ""]
        for name, case in affected[:10]:
            lines += [f"- {code(name)}: **{case_status(case)}**", *_failure_details(case)]
            guarantees = [GUARANTEES.get(letter, p.title) for letter, p in suite.profiles.items() if name in p.cases]
            if guarantees:
                lines += [f"  - Guarantee: {cell('; '.join(guarantees))}"]
        if len(affected) > 10:
            lines += [f"{len(affected) - 10} further checks are retained in the JSON artifact."]
        lines += ["", "</details>", ""]
    lines += decision_sections(suite)
    supported = [(letter, p) for letter, p in sorted(suite.profiles.items()) if p.verified]
    lines += ["---", "", *_hypothesis(suite)]
    lines += [
        "",
        "---",
        "",
        "<details>",
        f"<summary><strong>🟢 {len(supported)} supported guarantees</strong></summary>",
        "",
    ]
    for letter, profile in supported:
        lines += [f"- **{cell(GUARANTEES.get(letter, profile.title))}**"]
        if profile.assessment.because:
            lines += [f"  - Application reason: {cell(profile.assessment.because)}"]
    lines += ["", f"Suite (application code): {code(key)}", "", "</details>", "", "</details>"]
    return "\n".join(lines)


def _overview(reports: dict[str, SuiteCoverage]) -> list[str]:
    """Reserve a compact index before details can consume the comment budget."""
    headers = [
        "| Application | Passed | Failed | Blocked | Gaps | Rejected |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines = [
        "### Applications",
        "",
        "All collected applications, most actionable first. Expand the evidence below for reasons and tickets.",
        "",
        *headers,
    ]
    attention = sum(
        any(counts(suite)[metric] for metric in METRICS if metric != "passed") for suite in reports.values()
    )
    folded = False
    used = 0
    for index, (_, suite) in enumerate(sorted(reports.items(), key=_priority)):
        if 0 < attention == index < len(reports):
            lines += [
                "",
                "<details>",
                f"<summary>{len(reports) - attention} applications · zero failures, blocked checks or gaps</summary>",
                "",
                *headers,
            ]
            folded = True
        values = counts(suite)
        name = " ".join(suite.name.split())
        name = name if len(name) <= 70 else name[:70] + "…"
        # Long identifiers must wrap before squeezing the final metric offscreen.
        # Escape each chunk before adding trusted zero-width break opportunities.
        cells = ["&#8203;".join(cell(name[start : start + 24]) for start in range(0, len(name), 24))]
        for metric in METRICS:
            value = values[metric]
            # Color is supplementary: the column name and exact count carry
            # the meaning for screen readers and monochrome views.
            icon = "🔴 " if metric in ("failed", "rejected") else "🟠 " if metric != "passed" else ""
            cells.append(f"{icon}**{value}**" if value else "0")
        row = "| " + " | ".join(cells) + " |"
        if used + len(row) > MAX_BODY // 3:
            lines += ["", f"{len(reports) - index} further application rows omitted; see the full JSON artifact."]
            break
        lines.append(row)
        used += len(row)
    if folded:
        lines += ["", "</details>"]
    return [*lines, "", "### Evidence and decisions", ""]


def render(
    reports: dict[str, SuiteCoverage],
    *,
    run_url: str = "",
    source: str = "",
    unavailable: str = "",
    test_outcome: str = "unknown",
    asset_ref: str = "main",
    repository_url: str = "",
    revision: str = "",
    graphics: bool = False,
    inventory: ApplicationInventory | None = None,
    collected_skips: int | None = None,
) -> str:
    ref = quote(asset_ref, safe="")
    banner_assets = f"https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/{ref}/docs/assets"
    glyph_base = f"{banner_assets}/report-glyphs/" if graphics else ""
    totals: Counter[str] = Counter(dict.fromkeys(METRICS, 0))
    for suite in reports.values():
        totals.update(counts(suite))
    # Discovery widens the application denominator, never the passing evidence.
    totals["applications"] = len(set(reports) | (set(inventory.applications) if inventory else set()))
    head = [
        f'<a href="{PROJECT}"><picture><source media="(prefers-color-scheme: dark)" srcset="{banner_assets}/sticky-banner-dark.svg">'
        f'<img alt="pytest-obligation: what passed, what is missing, what to fix" src="{banner_assets}/sticky-banner-light.svg" width="640"></picture></a>',
        "",
    ]
    skipped, incomplete = _skipped_checks(reports, inventory, unavailable)
    if collected_skips is not None:
        skipped, incomplete = collected_skips, False
    head += [
        _totals(
            dict(totals), glyph_base, neutral=not reports or bool(unavailable), skipped=None if incomplete else skipped
        ),
        "",
    ]
    if test_outcome == "failure":
        head += [
            f"**🔴 Test step failed. {totals['failed'] + totals['rejected']} failed contract checks recorded; inspect the run log for other failures.**",
            "",
        ]
    elif test_outcome == "cancelled":
        head += ["**🟠 Test step did not complete.**", ""]
    if unavailable:
        head += ["**🟠 Evidence unavailable.**", unavailable, ""]
    elif reports:
        elapsed = next(iter(reports.values())).session_seconds
        timing = ([f"{elapsed:.1f}s elapsed"] if elapsed is not None else []) + [
            _time(list(reports.values()), compact=True)
        ]
        head += ["<sub>" + " · ".join(timing) + "</sub>", ""]
    head += _execution_summary(reports, inventory, unavailable, collected_skips)
    compact = len(reports) > 3
    if compact:
        head += _overview(reports)
    footer = [
        "",
        "<details>",
        "<summary><strong>What do these numbers mean?</strong></summary>",
        "",
        "- **Failures:** an executed assertion failed. Inspect the behavior and test assumptions.",
        "- **Rejected bindings:** repair the connection to production code; these checks provide no supporting evidence.",
        "- **Blocked checks:** expected checks did not complete successfully, including setup/cleanup errors and expected failures.",
        "- **Coverage gaps:** guarantees not assessed, missing scenarios, or with declared gaps. Each affected guarantee counts once. Deliberate exclusions are shown separately.",
        "",
        "Pass/fail/blocked/rejected counts partition unique checks. Gaps count guarantees, not extra tests. "
        "Declined and not-applicable declarations remain separate and do not establish passing coverage. Graphics show zero issues in green; missing reports never show green zeroes.",
        "",
        "Elapsed time covers the pytest session. Summed check time includes setup, execution and cleanup; parallel work overlaps.",
        "Application totals include discovered declarations and reported suites. Skipped checks count known deselections and explicit pytest skips; incomplete selected checks are not skips. Uncollected applications have unknown check counts. Zero recorded outcomes do not certify passing coverage.",
        "",
        "Application names, quoted reasons and diagnostic values come from application code. "
        "Guarantee labels come from pytest-obligation. Results cover collected suites only; passing checks do not rate every test's quality.",
        "",
        f"Test step (GitHub): **{cell(test_outcome)}**",
        f"Source: {code(source or 'local report')}",
        "",
        "</details>",
        "",
        (f"[Workflow run]({run_url}) · " if run_url else "")
        + f"[Report guide]({PROJECT}/blob/{ref}/package/docs/github-action-report.md)",
    ]
    sections = []
    for key, suite in sorted(reports.items(), key=_priority):
        section = _suite(key, suite, repository_url, revision, glyph_base, compact=compact)
        # Include disclosure separators and the overflow notice in the budget.
        if len("\n\n".join([*head, *sections, section, *footer])) > MAX_BODY - 300:
            sections.append(
                "Further contract details omitted to fit GitHub's comment limit. "
                "Application totals remain above; see the full JSON artifact for all reasons and checks."
            )
            break
        sections.append(section)
    # Blank lines end each HTML disclosure before the next Markdown block.
    return "\n".join(head) + "\n\n" + "\n\n".join(sections) + "\n\n---\n" + "\n".join(footer)
