"""GitHub-native sticky layout: aligned summaries, actionable detail on demand."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
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
from .graphics import LABELS, METRICS, application_html, application_name, count_text, summary_html
from .inventory import ApplicationInventory


def _skips_recorded(reports: Mapping[str, SuiteCoverage]) -> int:
    """Checks the reports show were not run on purpose: deselected, uncollected or skipped by pytest."""
    # Interrupted selected checks and expected failures must not masquerade as skips.
    return sum(
        not case.outcomes
        and (not case.collected or not case.selected)
        or case_status(case) == "Test skipped or incomplete"
        and any("skipped" in outcomes for outcomes in case.outcomes.values())
        for suite in reports.values()
        for case in all_cases(suite).values()
    )


def _execution_summary(
    reports: dict[str, SuiteCoverage], inventory: ApplicationInventory | None, unavailable: str, shown: "Headline"
) -> list[str]:
    declared = inventory.applications if inventory else {}
    applications = set(declared) | set(reports)
    observed = {key for key, suite in reports.items() if any(c.outcomes for c in all_cases(suite).values())}
    absent = applications - observed
    unknown = absent if unavailable else set()
    not_run = absent - unknown
    lines = [
        "<details>",
        "<summary>Application inventory and skipped tests</summary>",
        "",
        "Applications: **unknown**; no report or inventory names one."
        if shown.values["applications"] is None
        else f"**{len(observed)}** applications with results · **{len(not_run)}** applications not run"
        + (f" · **{len(unknown)}** unknown" if unknown else ""),
        f"Checks skipped: {_skips_text(shown)}",
        "",
    ]
    if not reports and shown.values["applications"] is not None:
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


def report_totals(reports: Mapping[str, SuiteCoverage]) -> Counter[str]:
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


def _zero_is_final(test_outcome: str, *, running: bool, unavailable: str, recorded: bool, missing: bool) -> bool:
    """
    Whether a zero count is a result rather than the absence of one.

    No zero is final while the workflow is still running, or when report evidence is unavailable. A test
    step that succeeded recorded everything it ran, and one that was skipped ran nothing on purpose. Any
    other step (failed, cancelled, outcome not reported) may have stopped before a check ran, so its zeros
    are final only when it was not cancelled, recorded an outcome, and no declared application is
    ``missing`` its report.
    """
    if running or unavailable:
        return False
    if test_outcome in ("success", "skipped"):
        return True
    return test_outcome != "cancelled" and recorded and not missing


def _shown(values: Mapping[str, int | None], final: bool) -> dict[str, int | None]:
    """Counts as shown: a zero that is not final is unknown (``None``, shown ``?``); any other is what was recorded."""
    return {kind: None if value == 0 and not final else value for kind, value in values.items()}


@dataclass(frozen=True)
class Headline:
    """
    Every headline count, decided once: the totals, the inventory details and the status notices read it.

    A count is what the evidence holds. It is ``None`` (shown ``?``) only where the evidence cannot settle
    it: a zero that is not final (:func:`_zero_is_final`), or a skip count that is only a lower bound,
    because a declared application has no report or JUnit could not classify the run's tests. A missing
    inventory narrows nothing: every count, skips included, then covers the reported applications.
    """

    #: ``applications``, each of :data:`METRICS`, and ``skipped``.
    values: dict[str, int | None]
    #: Whether a zero among ``values`` is a result.
    final: bool
    #: Whether any check recorded an outcome.
    recorded: bool
    #: The skips the evidence shows: a lower bound when ``values["skipped"]`` is unknown.
    skips_known: int
    #: Why the skip count is only a lower bound; empty when it is exact.
    skips_unknown: str


def headline(
    reports: Mapping[str, SuiteCoverage],
    *,
    inventory: ApplicationInventory | None,
    unavailable: str,
    test_outcome: str,
    running: bool,
    collected_skips: int | None,
    skips_unknown: str,
) -> Headline:
    """The headline counts. ``collected_skips`` is JUnit's exact skip count; ``skips_unknown`` says why it is missing."""
    declared = set(inventory.applications) if inventory else set()
    unreported = declared - set(reports)
    recorded = _recorded(reports.values())
    final = _zero_is_final(
        test_outcome, running=running, unavailable=unavailable, recorded=recorded, missing=bool(unreported)
    )
    if collected_skips is not None:
        skips, why = collected_skips, ""
    else:
        skips = _skips_recorded(reports)
        why = skips_unknown or ("Applications without a report have no measured test count." if unreported else "")
    values: dict[str, int | None] = {
        # Discovery widens the application denominator, never the passing evidence.
        "applications": len(declared | set(reports)),
        **report_totals(reports),
        "skipped": None if why else skips,
    }
    return Headline(values=_shown(values, final), final=final, recorded=recorded, skips_known=skips, skips_unknown=why)


def _skips_text(shown: Headline) -> str:
    """The skip count in words: exact, a lower bound or unknown, and why when it is not exact."""
    skipped = shown.values["skipped"]
    count = (
        f"**{skipped}**"
        if skipped is not None
        else f"**{shown.skips_known} known**"
        if shown.skips_known
        else "**unknown**"
    )
    return count + "." + (f" {shown.skips_unknown}" if shown.skips_unknown else "")


def suite_counts(suite: SuiteCoverage, *, test_outcome: str, running: bool, unavailable: str) -> dict[str, int | None]:
    """One application's counts as shown, by the headline's rule applied to that application's own outcomes."""
    final = _zero_is_final(
        test_outcome, running=running, unavailable=unavailable, recorded=_recorded([suite]), missing=False
    )
    return _shown(counts(suite), final)


def _totals(values: Mapping[str, int | None], glyph_base: str, *, neutral: bool = False) -> str:
    if not glyph_base:
        return "**" + " · ".join(f"{count_text(value)} {LABELS[kind]}" for kind, value in values.items()) + "**"
    return summary_html(values, glyph_base, neutral=neutral)


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
    values: Mapping[str, int | None] | None = None,
) -> str:
    """One application's section. ``values`` are its counts as shown; its recorded counts when omitted."""
    values = counts(suite) if values is None else values
    description = " · ".join(f"{count_text(values[k])} {LABELS[k]}" for k in METRICS)
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
    skips_unknown: str = "",
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
            skips_unknown=skips_unknown,
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
    skips_unknown: str,
    timing: bool,
    title: str,
    running: bool,
) -> str:
    ref = quote(asset_ref, safe="")
    banner_assets = f"https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/{ref}/docs/assets"
    glyph_base = f"{banner_assets}/report-glyphs/" if graphics else ""
    shown = headline(
        reports,
        inventory=inventory,
        unavailable=unavailable,
        test_outcome=test_outcome,
        running=running,
        collected_skips=collected_skips,
        skips_unknown=skips_unknown,
    )
    recorded_failures = (shown.values["failed"] or 0) + (shown.values["rejected"] or 0)
    # Order, top to bottom: the title (the first line tells two lanes' stickies apart; a publisher puts its
    # workflow notice right after it), this report's status notices, the banner, then the counts.
    head = [
        *([f"### {cell(title, TITLE_LIMIT)}", ""] if title else []),
        *_status_notices(
            test_outcome,
            recorded=shown.recorded,
            recorded_failures=recorded_failures,
            unavailable=unavailable,
            # While the workflow runs, the publisher's own notice says what ? means.
            unknowable=not shown.final and not running,
        ),
        f'<a href="{PROJECT}"><picture><source media="(prefers-color-scheme: dark)" srcset="{banner_assets}/sticky-banner-dark.svg">'
        f'<img alt="pytest-obligation: what passed, what is missing, what to fix" src="{banner_assets}/sticky-banner-light.svg" width="640"></picture></a>',
        "",
        "### Obligation contract checks",
        "",
        "Other pytest tests and workflow steps are not included in these counts.",
        "",
        _totals(shown.values, glyph_base, neutral=not reports),
        "",
    ]
    if shown.final and shown.values["skipped"] is None:
        # No status box explains this one ?: say why here.
        head += [f"<sub>Skipped tests: {_skips_text(shown)}</sub>", ""]
    known_failures = known_expected_failures(reports)
    if known_failures:
        failed = shown.values["failed"]
        assert failed is not None, "a known expected failure is a recorded failure"
        head += [
            f"**Failures: {failed - known_failures} unexpected + {known_failures} known expected.** "
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
    head += _execution_summary(reports, inventory, unavailable, shown)
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
            values=suite_counts(suite, test_outcome=test_outcome, running=running, unavailable=unavailable),
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
