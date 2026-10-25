"""A compact PR sticky: conclusions first, application vocabulary explicitly attributed."""

import re
from html import escape

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


#: Breaks what GitHub turns into a mention, an issue cross-reference or a link.
_INERT = "\u200b"
_AUTOLINK_WWW = re.compile(r"(?i)\b(www)(\.)")
_PATH_NUMBER = re.compile(r"/(?=\d)")


def inert(text: str) -> str:
    """Application text GitHub cannot act on: no @mention, issue or PR reference, or bare URL."""
    # GitHub decodes HTML entities before it finds these, so "&#64;team" still pings the team. A zero-width
    # space after "@" and "#", inside "://", after "www" and between "/" and a number (owner/repo/issues/N
    # and /pull/N are cross-referenced with or without a host) stops each one; checked with GitHub's
    # Markdown API, POST /markdown. Text inside a Markdown link is not scanned, so link text needs only escaping.
    text = text.replace("@", "@" + _INERT).replace("#", "#" + _INERT).replace("://", ":" + _INERT + "//")
    text = _PATH_NUMBER.sub("/" + _INERT, text)
    return _AUTOLINK_WWW.sub(r"\1" + _INERT + r"\2", text)


def link_text(value: str) -> str:
    """Escape text for a Markdown link's label: entities neutralize table delimiters, emphasis and links."""
    return (
        "".join(f"&#{ord(c)};" if c in "|`[]*_@\\" else escape(c) for c in value)
        .replace("\n", "<br>")
        .replace("\r", "")
    )


def cell(value: str, limit: int = 700) -> str:
    return link_text(inert(value if len(value) <= limit else value[:limit] + "…"))


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
    if case.debt and case.debt.kind == "known-defect" and "xfail" in case.outcomes.get("call", ()):
        return "Known expected failure"
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


def advice(profile: ProfileCoverage) -> str:
    statuses = {case_status(c) for c in profile.cases.values()}
    if "Test binding rejected" in statuses:
        return "Repair the test binding. This rejected check provides no evidence for the claim."
    if "Test setup/cleanup failed" in statuses:
        return "Repair the test environment or fixture; rerun the affected checks."
    if statuses & {"Check failed", "Known expected failure"}:
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
    result = {key: value for group in suite.case_groups() for key, value in group.items()}
    # Optional exploration disabled by selection does not invalidate fixed-history proofs.
    result.update({f"exploration:{k}": v for k, v in (suite.exploration or {}).items() if v.selected})
    return result


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
