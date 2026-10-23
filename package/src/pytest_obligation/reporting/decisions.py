"""Keep application defects, missing assessments and intentional scope separate."""

from urllib.parse import urlparse

from pytest_obligation.profiles.coverage import SuiteCoverage

from .evidence import GUARANTEES, all_cases, assessment_status, case_status, cell, code


def ticket_link(ticket: str | None) -> str:
    if not ticket:
        return "Ticket not reported."
    try:
        parsed = urlparse(ticket)
    except ValueError:
        return code(ticket)
    if (
        parsed.scheme in ("https", "http")
        and parsed.netloc
        and not parsed.username
        and not any(c.isspace() or c in '()<>"\\' for c in ticket)
    ):
        return f"[{cell(ticket)}]({ticket})"
    # Issue keys have no universal tracker URL. Adopters can put a full URL in
    # the baseline; never guess a private tracker from an application name.
    return code(ticket)


def decision_sections(suite: SuiteCoverage) -> list[str]:
    lines: list[str] = []
    defects: dict[tuple[str, str | None], list[str]] = {}
    for name, case in all_cases(suite).items():
        if case.debt and case.debt.kind == "known-defect":
            defects.setdefault((case.debt.reason, case.debt.ticket), []).append(f"- {code(name)}: {case_status(case)}")
    if defects:
        lines += ["**Known defects · application-declared expected failures**", ""]
        for (reason, ticket), checks in defects.items():
            lines += [
                f"Application reason: {cell(reason)}",
                "",
                ticket_link(ticket),
                "",
                "<details>",
                f"<summary>{len(checks)} affected checks · execution evidence</summary>",
                "",
                *checks,
                "",
                "</details>",
                "",
            ]
        lines += [
            "These declarations identify known behavior problems; inspect each check's execution status before treating this run as a reproduction.",
            "",
        ]
    categories = (
        ("Known gaps declared by the application", {"known gap"}),
        ("Unassessed guarantees and scenarios", {"not assessed"}),
        ("Deliberate exclusions", {"declined", "not applicable"}),
    )
    for title, states in categories:
        entries = []
        for letter, profile in sorted(suite.profiles.items()):
            label = f"{GUARANTEES.get(letter, profile.title)} ({letter})"
            assessments = [
                (label, profile.assessment),
                *((f"{label} / {family}", assessment) for family, assessment in profile.families.items()),
            ]
            for name, assessment in assessments:
                if assessment.state in states:
                    entries += [
                        f"- **{cell(name)}** · {assessment_status(assessment)}. "
                        f"Application reason: {cell(assessment.because or 'None supplied.')}"
                    ]
        if entries:
            lines += [f"**{title}**", "", *entries, ""]
            if "not assessed" in states:
                lines += [
                    "Bind the production behavior and exercise its invariants, or document why it does not apply.",
                    "",
                ]
            elif "declined" in states:
                lines += [
                    "These are scope decisions, not demonstrated defects. Review their reasons when the application changes.",
                    "",
                ]
    missing = [
        letter
        for letter, profile in suite.profiles.items()
        if profile.assessment.state == "claimed" and not profile.cases
    ]
    if missing:
        lines += [
            "**Claimed guarantees without checks**",
            "",
            f"Add production checks for: {cell(', '.join(missing))}.",
            "",
        ]
    return lines
