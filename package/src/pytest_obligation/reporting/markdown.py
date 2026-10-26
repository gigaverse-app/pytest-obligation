"""GitHub-native sticky layout: aligned summaries, actionable detail on demand."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
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
    rendering_own_text,
)
from .evidence import (
    MAX_BODY as MAX_BODY,
)
from .graphics import application_html, application_name, count_text, summary_html
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
    nothing_known = _applications_unknown(reports, inventory, unavailable)
    lines = [
        "<details>",
        "<summary>Application inventory and skipped tests</summary>",
        "",
        "Applications: **unknown**; no report or inventory could be read."
        if nothing_known
        else f"**{len(observed)}** applications with results · **{len(not_run)}** applications not run"
        + (f" · **{len(unknown)}** unknown" if unknown else ""),
        f"Checks skipped: {skip_count}."
        + (
            " Uncollected applications have no measured test count."
            if incomplete and set(declared) - set(reports)
            else ""
        ),
        "",
    ]
    if not reports and not nothing_known:
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
    "passed": "Contract checks passed",
    "failed": "Contract failures",
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
            if status in ("Check failed", "Known expected failure")
            else "blocked"
        )
        result[category] += 1
    result["gaps"] = sum(has_gap(p) for p in suite.profiles.values())
    return result


def report_totals(reports: dict[str, SuiteCoverage]) -> Counter[str]:
    """Each category's checks summed over every reported application: the headline counts."""
    totals: Counter[str] = Counter(dict.fromkeys(METRICS, 0))
    for suite in reports.values():
        totals.update(counts(suite))
    return totals


def known_expected_failures(reports: dict[str, SuiteCoverage]) -> int:
    """Failed checks the application declared as known defects; the rest of ``failed`` is unexpected."""
    return sum(
        case_status(case) == "Known expected failure"
        for suite in reports.values()
        for case in all_cases(suite).values()
    )


def _priority(item: tuple[str, SuiteCoverage]) -> tuple[int, int, str]:
    values = counts(item[1])
    for rank, category in enumerate(("failed", "rejected", "blocked", "gaps")):
        if values[category]:
            return rank, -values[category], item[0]
    return 4, 0, item[0]


#: A lane title is a name, not a paragraph.
TITLE_LIMIT = 120


def _recorded(suites: Iterable[SuiteCoverage]) -> bool:
    return any(case.outcomes for suite in suites for case in all_cases(suite).values())


def _unknowable(test_outcome: str, *, running: bool, recorded: bool, unavailable: str, missing: bool) -> bool:
    """
    Whether a zero count proves nothing, so it reads as unknown.

    A workflow still running has no final zero. Otherwise, a test step that
    succeeded recorded what ran, and one that was skipped ran nothing on
    purpose. One that failed, was cancelled or reported no outcome may have
    stopped before a check ran, so its zeros are unknown when nothing was
    recorded, evidence is unavailable, an application has no report or the run
    was cancelled. Non-zero counts are what was recorded, and stay.
    """
    if running:
        return True
    if test_outcome in ("success", "skipped"):
        return False
    return test_outcome == "cancelled" or not recorded or bool(unavailable) or missing


def _applications_unknown(
    reports: Mapping[str, SuiteCoverage], inventory: ApplicationInventory | None, unavailable: str
) -> bool:
    """Evidence is unavailable and nothing names an application, so even their number is unknown."""
    return bool(unavailable) and not reports and inventory is None


def _known(values: Mapping[str, int], unknowable: bool) -> dict[str, int | None]:
    """The counts as shown: under :func:`_unknowable`, a zero category is unknown, not zero."""
    return {kind: None if unknowable and kind in METRICS and value == 0 else value for kind, value in values.items()}


def _totals(
    values: Mapping[str, int | None], glyph_base: str, *, neutral: bool = False, skipped: int | None = None
) -> str:
    alt = " · ".join(f"{count_text(values[kind])} {LABELS[kind].lower()}" for kind in ("applications", *METRICS))
    if not glyph_base:
        return f"**{alt} · {count_text(skipped)} skipped tests**"
    return summary_html({**values, "skipped": skipped}, glyph_base, neutral=neutral)


def _notice(kind: str, headline: str, *details: str) -> list[str]:
    """One GitHub alert: the status in bold, then what it means. Every run status is stated this way, once."""
    lines = [f"> [!{kind}]", f"> **{headline}**"]
    for detail in details:
        lines += [">", f"> {detail}"]
    return [*lines, ""]


def _status_notices(
    test_outcome: str, *, recorded: bool, recorded_failures: int, unavailable: str, unknowable: bool
) -> list[str]:
    """
    What the test step's outcome and the evidence say about the counts, before the counts.

    Each status gets one box, and the first box says once what a ? count means.
    """
    unknown = ["A count shown as ? is not known."] if unknowable else []
    step: list[str] = []
    if test_outcome == "failure":
        if recorded_failures:
            recorded_what = [f"{recorded_failures} failed contract checks recorded."]
        elif recorded:
            recorded_what = ["No contract check failed, so the failure is elsewhere in the run."]
        elif unavailable:
            recorded_what = []  # The evidence box below says why nothing was read.
        else:
            recorded_what = ["No contract check was recorded: the step stopped before any ran."]
        step = _notice(
            "CAUTION",
            "The test step failed.",
            *recorded_what,
            *unknown,
            "Contract counts cover only obligation checks; inspect the run log for other failures.",
        )
    elif test_outcome == "cancelled":
        step = _notice("WARNING", "The test step did not complete.", *unknown)
    elif test_outcome not in ("success", "skipped") and unknown and not unavailable:
        step = _notice("WARNING", "The test step's outcome was not reported.", *unknown)
    # Without a test-step box, the evidence box is the one that explains ?.
    evidence = (
        _notice("WARNING", "Evidence unavailable.", unavailable, *([] if step else unknown)) if unavailable else []
    )
    return step + evidence


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
    key: str,
    suite: SuiteCoverage,
    repository_url: str,
    revision: str,
    glyph_base: str,
    *,
    compact: bool = False,
    timing: bool = True,
    unknowable: bool = False,
) -> str:
    values = _known(counts(suite), unknowable)
    description = " · ".join(f"{count_text(values[k])} {LABELS[k].lower()}" for k in METRICS)
    summary = f"{code(suite.name)} · {description}"
    if compact:
        summary = f"<strong>{application_name(suite.name)}</strong> · evidence and decisions"
    elif glyph_base:
        summary = application_html(suite.name, values, glyph_base)
    lines = [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        _source_link(suite, repository_url, revision),
        "",
    ]
    if timing:
        lines += [f"<sub>Test time: {_time([suite], compact=True).removeprefix('Test time: ')}</sub>", ""]
    if "selection" in suite.profiles:
        lines += [
            "Scope: **Scheduled selection and loop**. Covers the declared query and loop checks; does not establish full automatic recovery (profile A).",
            "",
        ]
    if "exemption" in suite.profiles:
        lines += [
            "Scope: **Handoff exemption**. Application reason: "
            + cell(suite.profiles["exemption"].assessment.because or "None supplied."),
            "",
        ]
    cases = all_cases(suite)
    for title, states in (
        ("Unexpected failures", {"Check failed"}),
        ("Rejected bindings", {"Test binding rejected"}),
        (
            "Blocked checks",
            {case_status(c) for c in cases.values()}
            - {"Passed", "Check failed", "Known expected failure", "Test binding rejected"},
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
        f"<summary><strong>{'🟢' if supported else '⚪'} {len(supported)} supported guarantees</strong></summary>",
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
        cells = [application_name(suite.name)]
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
    timing: bool = True,
    own_text: bool = False,
    title: str = "",
    running: bool = False,
) -> str:
    """
    The report's Markdown. ``running`` says the workflow has not finished, so no zero count is final yet. ``title`` names the lane or session, so two reports on one pull request can be
    told apart; it is shown as text, never as Markdown. ``timing=False`` leaves out elapsed and summed check times, so a copy kept
    in a document (see :mod:`pytest_obligation.reporting.readme`) changes only when the evidence does.
    ``own_text=True`` keeps the application's mentions, issue references and links live: only for
    contracts that are the repository's own code (see :func:`~.evidence.rendering_own_text`).
    """
    with rendering_own_text() if own_text else nullcontext():
        return _render(
            reports,
            run_url=run_url,
            source=source,
            unavailable=unavailable,
            test_outcome=test_outcome,
            asset_ref=asset_ref,
            repository_url=repository_url,
            revision=revision,
            graphics=graphics,
            inventory=inventory,
            collected_skips=collected_skips,
            timing=timing,
            title=title,
            running=running,
        )


def _render(
    reports: dict[str, SuiteCoverage],
    *,
    run_url: str,
    source: str,
    unavailable: str,
    test_outcome: str,
    asset_ref: str,
    repository_url: str,
    revision: str,
    graphics: bool,
    inventory: ApplicationInventory | None,
    collected_skips: int | None,
    timing: bool,
    title: str,
    running: bool,
) -> str:
    ref = quote(asset_ref, safe="")
    banner_assets = f"https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/{ref}/docs/assets"
    glyph_base = f"{banner_assets}/report-glyphs/" if graphics else ""
    totals = report_totals(reports)
    # Discovery widens the application denominator, never the passing evidence.
    totals["applications"] = len(set(reports) | (set(inventory.applications) if inventory else set()))
    skipped, incomplete = _skipped_checks(reports, inventory, unavailable)
    if collected_skips is not None:
        skipped, incomplete = collected_skips, False
    recorded = _recorded(reports.values())
    missing = bool(inventory and set(inventory.applications) - set(reports))
    unknowable = _unknowable(test_outcome, running=running, recorded=recorded, unavailable=unavailable, missing=missing)
    shown = _known(totals, unknowable)
    if _applications_unknown(reports, inventory, unavailable):
        shown["applications"] = None
    # Order, top to bottom: the title (the first line tells two lanes' stickies apart; a publisher puts its
    # workflow notice right after it), this report's status notices, the banner, then the counts.
    head = [
        *([f"### {cell(title, TITLE_LIMIT)}", ""] if title else []),
        *_status_notices(
            test_outcome,
            recorded=recorded,
            recorded_failures=totals["failed"] + totals["rejected"],
            unavailable=unavailable,
            unknowable=unknowable and not running,
        ),
        f'<a href="{PROJECT}"><picture><source media="(prefers-color-scheme: dark)" srcset="{banner_assets}/sticky-banner-dark.svg">'
        f'<img alt="pytest-obligation: what passed, what is missing, what to fix" src="{banner_assets}/sticky-banner-light.svg" width="640"></picture></a>',
        "",
        "### Obligation contract checks",
        "",
        "Other pytest tests and workflow steps are not included in these counts.",
        "",
        _totals(shown, glyph_base, neutral=not reports or bool(unavailable), skipped=None if incomplete else skipped),
        "",
    ]
    known_failures = known_expected_failures(reports)
    if known_failures:
        head += [
            f"**Failures: {totals['failed'] - known_failures} unexpected + {known_failures} known expected.** "
            "Expected failures are declared by the application and do not fail CI. "
            "Review their reasons and evidence below; counts are checks, not distinct product bugs.",
            "",
        ]
        if test_outcome == "success":
            head += ["**Test step succeeded with known expected failures.**", ""]
    if reports and timing and not unavailable:
        elapsed = next(iter(reports.values())).session_seconds
        times = ([f"{elapsed:.1f}s elapsed"] if elapsed is not None else []) + [
            _time(list(reports.values()), compact=True)
        ]
        head += ["<sub>" + " · ".join(times) + "</sub>", ""]
    head += _execution_summary(reports, inventory, unavailable, collected_skips)
    compact = len(reports) > 3
    if compact:
        head += _overview(reports)
    attempt = re.search(r"/attempts/([1-9][0-9]*)/?$", urlparse(run_url).path)
    run_label = f"run {attempt[1]}" if attempt and attempt[1] != "1" else "run"
    footer = [
        "",
        "<details>",
        "<summary><strong>What do these numbers mean?</strong></summary>",
        "",
        "- **Failures:** an executed assertion failed unexpectedly or was an application-declared expected failure. Expected failures still permit successful CI; the visible breakdown distinguishes them.",
        "- **Rejected bindings:** repair the connection to production code; these checks provide no supporting evidence.",
        "- **Blocked checks:** checks could not establish a result, including missing execution, setup/cleanup errors, binding-debt or unclassified expected failures, and unexpected passes requiring declaration review.",
        "- **Coverage gaps:** guarantees not assessed, missing scenarios, or with declared gaps. Each affected guarantee counts once. Deliberate exclusions are shown separately.",
        "",
        "Pass/fail/blocked/rejected counts partition unique checks. Gaps count guarantees, not extra tests. "
        "Declined and not-applicable declarations remain separate and do not establish passing coverage. Graphics color contract results: passing checks and zero issues are green, failures and rejected bindings are red, blocked checks and gaps are amber. Missing reports never show green zeroes. The workflow status above is separate from these contract counts.",
        "",
        "Elapsed time covers the pytest session. Summed check time includes setup, execution and cleanup; parallel work overlaps.",
        "Application totals include discovered declarations and reported suites. Skipped checks count known deselections and explicit pytest skips; incomplete selected checks are not skips. Uncollected applications have unknown check counts. Zero recorded outcomes do not certify passing coverage.",
        "",
        "Application names, quoted reasons and diagnostic values come from application code. "
        "Guarantee labels come from pytest-obligation. Results cover collected suites only; passing checks do not rate every test's quality.",
        "",
        f"Test step (reported): **{cell(test_outcome)}**",
        f"Source: {code(source or 'local report')}",
        "",
        "</details>",
        "",
        (f"[{run_label}]({run_url}) · " if run_url else "")
        + f"[Report guide]({PROJECT}/blob/{ref}/package/docs/github-action-report.md)",
    ]
    sections = []
    for key, suite in sorted(reports.items(), key=_priority):
        section = _suite(
            key,
            suite,
            repository_url,
            revision,
            glyph_base,
            compact=compact,
            timing=timing,
            unknowable=_unknowable(
                test_outcome, running=running, recorded=_recorded([suite]), unavailable=unavailable, missing=False
            ),
        )
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
