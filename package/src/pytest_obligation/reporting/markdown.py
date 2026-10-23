"""GitHub-native sticky layout: aligned summaries, actionable detail on demand."""

import re
from collections import Counter
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

from pytest_obligation.profiles.coverage import ProfileCoverage, SuiteCoverage

from .evidence import (
    GUARANTEES,
    PROJECT,
    _failure_details,
    advice,
    all_cases,
    assessment_status,
    case_status,
    cell,
    code,
)
from .evidence import (
    MAX_BODY as MAX_BODY,
)
from .graphics import application_svg, summary_svg

METRICS = ("passed", "failed", "blocked", "gaps", "rejected")
LABELS = {
    "applications": "Applications",
    "passed": "Checks passed",
    "failed": "Failures",
    "blocked": "Blocked checks",
    "gaps": "Coverage gaps",
    "rejected": "Rejected bindings",
}
ASSET_URL = "https://pytest-obligation.invalid/assets/"


def has_gap(profile: ProfileCoverage) -> bool:
    return profile.assessment.state in ("declined", "known gap", "not assessed") or (
        profile.assessment.state == "claimed"
        and (not profile.cases or any(f.state not in ("claimed", "not applicable") for f in profile.families.values()))
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


def _picture(name: str, alt: str, *, row: bool = False) -> str:
    width = "96%" if row else "100%"
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="{ASSET_URL}{name}-dark.svg">'
        f'<img alt="{cell(alt)}" src="{ASSET_URL}{name}-light.svg" width="{width}" align="middle"></picture>'
    )


def _totals(values: dict[str, int], assets: dict[str, str] | None) -> str:
    alt = " · ".join(f"{values[kind]} {LABELS[kind].lower()}" for kind in ("applications", *METRICS))
    if assets is None:
        return f"**{alt}**"
    for theme in ("light", "dark"):
        assets[f"totals-{theme}.svg"] = summary_svg(values, dark=theme == "dark")
    return _picture("totals", alt)


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


def _profile_detail(letter: str, profile: ProfileCoverage, *, gap: bool = False) -> list[str]:
    label = GUARANTEES.get(letter, profile.title)
    result = [f"- **{cell(label)}**" + (f" · {assessment_status(profile.assessment)}" if gap else "")]
    if profile.assessment.because:
        result += [f"  - Application reason: {cell(profile.assessment.because)}"]
    if gap:
        result += [f"  - {advice(profile)}"]
    for family, assessment in profile.families.items():
        if assessment.state != "claimed":
            result += [
                f"  - {code(family)}: {assessment_status(assessment)}. "
                f"Application reason: {cell(assessment.because or 'None supplied.')}"
            ]
    return result


def _suite(key: str, suite: SuiteCoverage, repository_url: str, revision: str, assets: dict[str, str] | None) -> str:
    values = counts(suite)
    description = " · ".join(f"{values[k]} {LABELS[k].lower()}" for k in METRICS)
    summary = f"{code(suite.name)} · {description}"
    if assets is not None:
        name = "app-" + sha256(key.encode()).hexdigest()[:16]
        for theme in ("light", "dark"):
            assets[f"{name}-{theme}.svg"] = application_svg(suite.name, values, dark=theme == "dark")
        summary = _picture(name, f"{suite.name}: {description}", row=True)
    lines = [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        _source_link(suite, repository_url, revision),
        "",
        f"<sub>Test time: {_time([suite], compact=True).removeprefix('Test time: ')}</sub>",
        "",
    ]
    if len(suite.name) > 24:
        lines += [f"Application: {code(suite.name)}", ""]
    cases = all_cases(suite)
    for title, states in (
        ("Failures", {"Check failed"}),
        ("Rejected bindings", {"Test binding rejected"}),
        (
            "Blocked checks",
            {case_status(c) for c in cases.values()} - {"Passed", "Check failed", "Test binding rejected"},
        ),
    ):
        affected = [(name, c) for name, c in cases.items() if case_status(c) in states]
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
            lines += ["Run the missing checks, or repair their setup/cleanup.", ""]
        lines += ["<details>", f"<summary><strong>{len(affected)} {title.lower()} · diagnostics</strong></summary>", ""]
        for name, case in affected[:10]:
            lines += [f"- {code(name)}: **{case_status(case)}**", *_failure_details(case)]
            guarantees = [GUARANTEES.get(letter, p.title) for letter, p in suite.profiles.items() if name in p.cases]
            if guarantees:
                lines += [f"  - Guarantee: {cell('; '.join(guarantees))}"]
        if len(affected) > 10:
            lines += [f"{len(affected) - 10} further checks are retained in the JSON artifact."]
        lines += ["", "</details>", ""]
    gaps = [(letter, p) for letter, p in sorted(suite.profiles.items()) if has_gap(p)]
    if gaps:
        lines += [f"**Coverage gaps · {len(gaps)} guarantees need review**", ""]
        for letter, profile in gaps:
            lines += [
                f"**{cell(GUARANTEES.get(letter, profile.title))}** · {assessment_status(profile.assessment)}",
                "",
            ]
            if profile.assessment.because:
                lines += [f"Application reason: {cell(profile.assessment.because)}", ""]
        for recommendation in dict.fromkeys(advice(p) for _, p in gaps):
            lines += [recommendation, ""]
        if any(p.families for _, p in gaps):
            lines += ["<details>", "<summary><strong>Missing scenario details</strong></summary>", ""]
            for letter, profile in gaps:
                lines += _profile_detail(letter, profile, gap=True)
            lines += ["", "</details>"]
        lines += [""]
    supported = [(letter, p) for letter, p in sorted(suite.profiles.items()) if p.verified]
    excluded = [(letter, p) for letter, p in sorted(suite.profiles.items()) if p.assessment.state == "not applicable"]
    lines += ["---", "", *_hypothesis(suite)]
    lines += [
        "",
        "---",
        "",
        "<details>",
        f"<summary><strong>{len(supported)} supported guarantees · {len(excluded)} not applicable</strong></summary>",
        "",
    ]
    for letter, profile in supported:
        lines += _profile_detail(letter, profile)
    if excluded:
        lines += ["", "**Not applicable, as declared by the application**", ""]
        for letter, profile in excluded:
            lines += _profile_detail(letter, profile)
    lines += ["", f"Suite (application code): {code(key)}", "", "</details>", "", "</details>"]
    return "\n".join(lines)


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
    assets: dict[str, str] | None = None,
) -> str:
    ref = quote(asset_ref, safe="")
    banner_assets = f"https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/{ref}/docs/assets"
    totals: Counter[str] = Counter()
    for suite in reports.values():
        totals.update(counts(suite))
    totals["applications"] = len(reports)
    head = [
        f'<a href="{PROJECT}"><picture><source media="(prefers-color-scheme: dark)" srcset="{banner_assets}/sticky-banner-dark.svg">'
        f'<img alt="pytest-obligation: what passed, what is missing, what to fix" src="{banner_assets}/sticky-banner-light.svg" width="640"></picture></a>',
        "",
    ]
    if test_outcome == "failure":
        head += [
            f"**🔴 Test step failed. {totals['failed'] + totals['rejected']} failed contract checks recorded; inspect the run log for other failures.**",
            "",
        ]
    elif test_outcome in ("cancelled", "skipped"):
        head += ["**🟠 Test step did not complete.**", ""]
    if unavailable or not reports:
        head += ["**🟠 Evidence unavailable.**", unavailable, ""]
    else:
        head += [_totals(dict(totals), assets), ""]
        elapsed = next(iter(reports.values())).session_seconds
        timing = ([f"{elapsed:.1f}s elapsed"] if elapsed is not None else []) + [
            _time(list(reports.values()), compact=True)
        ]
        head += ["<sub>" + " · ".join(timing) + "</sub>", ""]
    outer = len(reports) > 3
    if outer:
        head += ["<details>", f"<summary>Applications · {len(reports)} · most actionable first</summary>", ""]
    footer = (["", "</details>"] if outer else []) + [
        "",
        "<details>",
        "<summary><strong>What do these numbers mean?</strong></summary>",
        "",
        "- **Failures:** an executed assertion failed. Inspect the behavior and test assumptions.",
        "- **Rejected bindings:** repair the connection to production code; these checks provide no supporting evidence.",
        "- **Blocked checks:** expected checks did not complete successfully, including setup/cleanup errors and expected failures.",
        "- **Coverage gaps:** guarantees not claimed, not assessed, missing scenarios, or with declared gaps. Each affected guarantee counts once.",
        "",
        "Pass/fail/blocked/rejected counts partition unique checks. Gaps count guarantees, not extra tests. "
        "Not-applicable declarations remain separate. Graphics show zero issues in green; missing reports never show green zeroes.",
        "",
        "Elapsed time covers the pytest session. Summed check time includes setup, execution and cleanup; parallel work overlaps.",
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
        section = "---\n\n" + _suite(key, suite, repository_url, revision, assets)
        if len("\n".join([*head, *sections, section, *footer])) > MAX_BODY:
            sections.append(
                "Further contract details omitted to fit GitHub's comment limit. See the full JSON artifact."
            )
            break
        sections.append(section)
    return "\n".join([*head, *sections, "", "---", *footer])
