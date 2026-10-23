"""A compact PR sticky: conclusions first, application vocabulary explicitly attributed."""

from collections import Counter
from html import escape
from urllib.parse import quote

from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage

PROJECT = "https://github.com/gigaverse-app/pytest-obligation"
MAX_BODY = 55000

# These are library-owned explanations. Contract names and reasons always carry
# an application label and are escaped before entering Markdown or HTML.
GUARANTEES = {
    "A": "Unfinished work gets recovered",
    "B": "Worker ownership is bounded",
    "C": "Uncertain outcomes are handled",
    "D": "Needed records are retained",
    "E": "Results eventually settle correctly",
    "F": "Owed work is discovered from stored facts",
    "G": "Execution respects its gate",
    "H": "Repeating work is harmless",
    "I": "Intent and work are saved together",
    "J": "Retries have a limit",
}


def cell(value: str, limit: int = 700) -> str:
    text = value if len(value) <= limit else value[:limit] + "…"
    # HTML entities also neutralize mentions, table delimiters and Markdown links.
    return (
        "".join(f"&#{ord(c)};" if c in "|`[]*_@\\" else escape(c) for c in text).replace("\n", "<br>").replace("\r", "")
    )


def code(value: str) -> str:
    return f"<code>{cell(value)}</code>"


def case_status(case: CaseEvidence) -> str:
    if case.passed:
        return "Passed"
    if any(f.kind == "binding" for f in case.failures):
        return "Test binding rejected"
    if any(f.kind == "test environment" for f in case.failures):
        return "Test setup/cleanup failed"
    if any("failed" in results for results in case.outcomes.values()):
        return "Check failed"
    if any("xpass" in results for results in case.outcomes.values()):
        return "Expected failure passed; review declaration"
    if any("xfail" in results for results in case.outcomes.values()):
        return "Expected failure; no passing proof"
    if not case.collected:
        return "Test not collected"
    if not case.selected:
        return "Test filtered out"
    return "Test skipped or incomplete"


def assessment_status(assessment: Assessment) -> str:
    return {
        "claimed": "Evidence incomplete",
        "known gap": "Known gap declared",
        "declined": "Not claimed by application",
        "not applicable": "Not applicable (application decision)",
        "not assessed": "Coverage not assessed",
    }[assessment.state]


def profile_status(profile: ProfileCoverage) -> str:
    if profile.verified:
        return "✅ Supported by this run"
    statuses = {case_status(c) for c in profile.cases.values()}
    for status in ("Test binding rejected", "Test setup/cleanup failed", "Check failed"):
        if status in statuses:
            return f"🔴 {status}"
    if profile.assessment.state in ("not applicable", "declined"):
        return "⚪ " + assessment_status(profile.assessment)
    return "🟠 " + assessment_status(profile.assessment)


def advice(profile: ProfileCoverage) -> str:
    statuses = {case_status(c) for c in profile.cases.values()}
    if "Test binding rejected" in statuses:
        return "Repair the test binding. This rejected check provides no evidence for the claim."
    if "Test setup/cleanup failed" in statuses:
        return "Repair the test environment or fixture; rerun the affected checks."
    if "Check failed" in statuses:
        return (
            "Inspect the failed assertion and application state; fix the behavior or an incorrect contract assumption."
        )
    if profile.verified:
        return "All declared checks passed. Further scenarios may still strengthen coverage."
    if profile.assessment.state == "known gap":
        return "Resolve the application-declared gap; this may need implementation work, test bindings, or both."
    if profile.assessment.state == "declined":
        return (
            "Review whether the application should promise this guarantee. Passing declaration checks do not prove it."
        )
    if profile.assessment.state == "not applicable":
        return "Review the application's reason for excluding this guarantee."
    if profile.assessment.state == "not assessed" or not profile.cases:
        return "Add a production binding and scenarios, or explicitly declare why this guarantee is outside scope."
    if any(not case.passed for case in profile.cases.values()):
        return "Run the missing, filtered, skipped or incomplete checks before relying on this claim."
    return "Assess the missing scenario families; add bindings and scenarios where applicable."


def all_cases(suite: SuiteCoverage) -> dict[str, CaseEvidence]:
    # Related profiles can reference the same generated case. Count that case once.
    return {key: value for group in suite.case_groups() for key, value in group.items()}


def _boolean(value: bool | None) -> str:
    return "unknown" if value is None else "yes" if value else "no"


def _failure_details(case: CaseEvidence) -> list[str]:
    lines = []
    for failure in case.failures:
        lines += [f"- **{cell(failure.phase)}:** {cell(failure.message)}"]
        for recovery in failure.recovery:
            lines += [
                f"- Recovery stage (library): **{recovery.stage}**; ticks: **{recovery.ticks}**; "
                f"scenario (application): {code(recovery.name)}",
                "",
                "| Item (application) | Injected fault? | Still owed? | Progress observed? | State (application) |",
                "| --- | --- | --- | --- | --- |",
            ]
            for candidate in recovery.candidates[:12]:
                metadata = "; ".join(f"{k}={v}" for k, v in candidate.details.items())
                if candidate.diagnostic_error:
                    metadata += f"; diagnostic unavailable: {candidate.diagnostic_error}"
                lines.append(
                    f"| {code(candidate.identity)} | {candidate.fault_count} | {_boolean(candidate.owed)} | "
                    f"{_boolean(candidate.progressed)} | {cell(metadata)} |"
                )
            if len(recovery.candidates) > 12:
                lines += ["", "More items are retained in the JSON report."]
            lines += [""]
    return lines


def _suite(key: str, suite: SuiteCoverage) -> str:
    cases = all_cases(suite)
    lines = [
        "<details>",
        f"<summary><strong>Application: {cell(suite.name)}</strong> · "
        f"{'supported scope' if suite.verified else 'attention needed'} · "
        f"{sum(c.passed for c in cases.values())}/{len(cases)} checks passed</summary>",
        "",
        f"Suite (application code): {code(key)}",
        "",
        "| Guarantee (library terminology) | Result | Next step |",
        "| --- | --- | --- |",
    ]
    for letter, profile in sorted(suite.profiles.items()):
        label = GUARANTEES.get(letter, profile.title)
        count = f"{sum(c.passed for c in profile.cases.values())}/{len(profile.cases)} checks passed"
        lines.append(f"| {cell(label)} ({cell(letter)}) | {profile_status(profile)}<br>{count} | {advice(profile)} |")
    lines += ["", "#### Application decisions and missing scenarios", ""]
    for letter, profile in sorted(suite.profiles.items()):
        if profile.assessment.because:
            lines.append(f"- **{cell(letter)}**, reason from application: {cell(profile.assessment.because)}")
        for family, assessment in profile.families.items():
            if assessment.state != "claimed":
                lines.append(
                    f"- **{cell(letter)} / {code(family)}** (library scenario family): "
                    f"{assessment_status(assessment)}. Application reason: {cell(assessment.because or 'None supplied.')}"
                )
    incomplete = [(name, case) for name, case in cases.items() if not case.passed]
    if incomplete:
        lines += ["", "#### Checks needing attention", ""]
        for name, case in incomplete[:25]:
            phases = "; ".join(f"{p}={','.join(v)}" for p, v in case.outcomes.items()) or "No execution recorded"
            lines += [f"- {code(name)}: **{case_status(case)}**. {cell(phases)}", *_failure_details(case)]
        if len(incomplete) > 25:
            lines += ["", f"{len(incomplete) - 25} additional checks are retained in the JSON report."]
    lines += ["", "</details>"]
    return "\n".join(lines)


def render(
    reports: dict[str, SuiteCoverage],
    *,
    run_url: str = "",
    source: str = "",
    unavailable: str = "",
    test_outcome: str = "unknown",
    asset_ref: str = "main",
) -> str:
    ref = quote(asset_ref, safe="")
    assets = f"https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/{ref}/docs/assets"
    cases = [c for suite in reports.values() for c in all_cases(suite).values()]
    statuses = Counter(case_status(c) for c in cases)
    failures = sum(statuses[s] for s in ("Test binding rejected", "Test setup/cleanup failed", "Check failed"))
    supported = sum(s.verified for s in reports.values())
    if test_outcome == "failure":
        verdict = (
            f"🔴 Test step failed. {failures} failed contract checks recorded; inspect the run log for other failures."
        )
    elif test_outcome in ("cancelled", "skipped"):
        verdict = "🟠 Test step did not complete. Review missing execution before relying on this report."
    elif unavailable or not reports:
        verdict = "🟠 Evidence unavailable. No application guarantee is certified."
    elif failures:
        verdict = f"🔴 {failures} checks failed. Review failures before relying on these claims."
    elif supported != len(reports):
        verdict = "🟠 Some guarantees lack passing evidence. Review the gaps below."
    else:
        verdict = "✅ All claims in these collected contracts have passing evidence."
    head = [
        f'<a href="{PROJECT}"><picture><source media="(prefers-color-scheme: dark)" srcset="{assets}/sticky-banner-dark.svg">'
        f'<img alt="pytest-obligation: what passed, what is missing, what to fix" src="{assets}/sticky-banner-light.svg" width="640"></picture></a>',
        "",
        f"**{verdict}**",
        "",
        f"**{supported}/{len(reports)} contracts supported** · **{statuses['Passed']}/{len(cases)} checks passed** · "
        f"**{statuses['Test binding rejected']} rejected bindings**",
        "",
        f"Source: {code(source or 'local report')}" + (f" · [Workflow run]({run_url})" if run_url else ""),
        "",
        f"Test step (GitHub): **{cell(test_outcome)}** · contract evidence is scoped to collected suites.",
        "",
    ]
    if unavailable:
        head += [unavailable, ""]
    head += [
        "Application names and reasons are labeled **application**. Guarantee/result labels come from **pytest-obligation**.",
        "",
    ]
    footer = [
        "",
        "<details>",
        "<summary>How to read this report</summary>",
        "",
        "| Label | What you should do |",
        "| --- | --- |",
        "| 🔴 Check failed | Inspect a failed assertion. It may expose application behavior or a wrong test assumption. |",
        "| 🔴 Test binding rejected | Repair the connection to production code. This check cannot support its claim. |",
        "| 🟠 Coverage not assessed | Add bindings and meaningful scenarios, or explicitly exclude the guarantee. |",
        "| 🟠 Known gap declared | Read the application reason; implementation and/or tests may need work. |",
        "| 🟠 Missing execution | Run existing checks that were filtered, skipped, interrupted or not collected. |",
        "| ⚪ Not claimed / not applicable | An application scope decision, not a proved guarantee. |",
        "| ✅ Supported by this run | Declared checks passed; this does not rate every test's quality. |",
        "",
        "The report does not infer that all tests are meaningful, discover undeclared contracts, or change pytest's exit status. "
        "Diagnostic state explains failures; it does not add proof. Keep pytest and coverage-policy checks required.",
        "",
        "</details>",
        "",
        f"[pytest-obligation]({PROJECT}) · [Reading and installing this report]({PROJECT}/blob/{ref}/package/docs/github-action-report.md)",
    ]
    sections = []
    for key, suite in sorted(reports.items()):
        section = _suite(key, suite)
        if len("\n".join([*head, *sections, section, *footer])) > MAX_BODY:
            sections.append(
                "Further contract details omitted to fit GitHub's comment limit. See the full JSON artifact."
            )
            break
        sections.append(section)
    return "\n".join([*head, *sections, *footer])
