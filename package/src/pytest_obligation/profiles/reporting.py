"""Optional pytest evidence for full contracts and narrower scheduled-selection suites."""

import os
from collections.abc import Generator
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest

from .coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage

_REPORT = pytest.StashKey[dict[str, SuiteCoverage]]()
_ITEMS = pytest.StashKey[dict[str, tuple[str, str]]]()
_EXPLORATION_ITEMS = pytest.StashKey[dict[str, tuple[str, str]]]()
_START = pytest.StashKey[float]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_START] = perf_counter()


def _record(config: pytest.Config, suite: str, case_id: str, *, selected: bool = False) -> None:
    report = config.stash[_REPORT][suite]
    for cases in (*report.case_groups(), report.exploration or {}):
        if case_id in cases:
            evidence = cases[case_id]
            evidence.collected = True
            evidence.selected |= selected


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> Generator[None]:
    """Capture expected/collected coverage before filtering, then record actual selection."""
    if not (
        config.getoption("due_work_profile_report", default=None) or config.getoption("due_work_summary", default=False)
    ):
        yield
        return
    # These declarations have already been imported by selected suites. Keeping
    # imports here avoids adding domain models to the global plugin import path.
    from ..contract import (
        Claim,
        ContractCase,
        Disposition,
        ObligationContract,
        SafetyContract,
        ScheduledSelection,
        convergence_assessments,
        declared_debt,
        disposition_label,
        safety_contract_cases,
        scheduled_selection_cases,
        suite_cases,
    )
    from ..debt import DebtBaseline, load_baseline
    from .catalog import Profile

    baseline_path = config.getoption("due_work_debt_baseline") or config.getini("due_work_debt_baseline")
    baseline = load_baseline(config.rootpath, baseline=Path(baseline_path)) if baseline_path else DebtBaseline()

    reports: dict[str, SuiteCoverage] = {}
    names: dict[str, tuple[str, str]] = {}
    exploration_names: dict[str, tuple[str, str]] = {}
    for item in items:
        if not isinstance(item, pytest.Function) or item.cls is None:
            continue
        contract = getattr(item.cls, "__due_work_contract__", None) or getattr(item.cls, "__safety_contract__", None)
        if not isinstance(contract, (ObligationContract, SafetyContract, ScheduledSelection)):
            continue
        suite = f"{item.cls.__module__}.{item.cls.__qualname__}"
        if suite not in reports:

            def assessment(disposition: Disposition) -> Assessment:
                return Assessment(
                    state=disposition_label(disposition),
                    because=None if isinstance(disposition, Claim) else disposition.because,
                )

            if isinstance(contract, ScheduledSelection):
                # This is its own limited scope, never a full profile A claim.
                profiles = {
                    "selection": ProfileCoverage(
                        title="Scheduled selection and loop",
                        assessment=Assessment(state="claimed"),
                        families={
                            "schedule evidence": Assessment(
                                state="declined" if contract.unscheduled_because else "claimed",
                                because=contract.unscheduled_because,
                            )
                        },
                    )
                }
            else:
                profiles = {
                    profile.name: ProfileCoverage(title=profile.title, assessment=assessment(disposition))
                    for profile, disposition in contract.profiles.items()
                }
            if isinstance(contract, ObligationContract):
                profiles[Profile.E.name].families = {
                    family.name: assessment(disposition)
                    for family, disposition in convergence_assessments(contract).items()
                }
                parameters = suite_cases(contract, covers=getattr(item.cls, "__due_work_sources__", ()))
            elif isinstance(contract, SafetyContract):
                parameters = safety_contract_cases(contract)
            else:
                parameters = scheduled_selection_cases(contract)
            tickets = {(entry.case, entry.kind): entry.ticket for entry in baseline.of(suite)}
            debt = {
                entry.case: entry.model_copy(update={"ticket": tickets.get((entry.case, entry.kind))})
                for entry in declared_debt(parameters)
            }
            additional_cases: dict[str, CaseEvidence] = {}
            for parameter in parameters:
                case = parameter.values[0]
                if isinstance(contract, ScheduledSelection) and case.id != "schedule_evidence-declined":
                    profiles["selection"].cases[case.id] = CaseEvidence(family=case.family, debt=debt.get(case.id))
                    continue
                if case.profile is None or case.assessment_only:
                    additional_cases[case.id] = CaseEvidence(family=case.family, debt=debt.get(case.id))
                    continue
                for profile in (case.profile, *case.related_profiles):
                    profiles[profile.name].cases[case.id] = CaseEvidence(family=case.family, debt=debt.get(case.id))
            from .source import contract_source

            reports[suite] = SuiteCoverage(
                name=contract.name,
                profiles=profiles,
                additional_cases=additional_cases,
                source=contract_source(item.cls, contract, Path(os.environ.get("GITHUB_WORKSPACE", config.rootpath))),
                exploration=None if isinstance(contract, ScheduledSelection) else {},
            )
        if item.get_closest_marker("due_work_exploration") and hasattr(item, "callspec"):
            scenario = str(item.callspec.params["interleaving_name"])
            case_id = f"hypothesis-{scenario}"
            exploration = reports[suite].exploration
            assert exploration is not None
            exploration[case_id] = CaseEvidence(family=scenario)
            exploration_names[item.nodeid] = (suite, case_id)
        if hasattr(item, "callspec") and "case" in item.callspec.params:
            case = item.callspec.params["case"]
            assert isinstance(case, ContractCase), "generated profile test must carry the canonical case"
            names[item.nodeid] = (suite, case.id)
    config.stash[_REPORT] = reports
    config.stash[_ITEMS] = names
    config.stash[_EXPLORATION_ITEMS] = exploration_names
    routes = {**names, **exploration_names}
    for suite, case_id in routes.values():
        _record(config, suite, case_id)
    yield
    for item in items:
        if item.nodeid in routes:
            _record(config, *routes[item.nodeid], selected=True)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Read the final normalized outcome, including teardown and strict known failures."""
    report = yield
    route = item.config.stash.get(_ITEMS, {}).get(item.nodeid) or item.config.stash.get(_EXPLORATION_ITEMS, {}).get(
        item.nodeid
    )
    if route is None:
        return report
    suite, case_id = route
    outcome = report.outcome
    if getattr(report, "wasxfail", None) is not None:
        outcome = "xpass" if report.passed else "xfail"
    suite_report = item.config.stash[_REPORT][suite]
    for cases in (*suite_report.case_groups(), suite_report.exploration or {}):
        if case_id in cases:
            cases[case_id].outcomes.setdefault(report.when, []).append(outcome)
            cases[case_id].durations.append(report.duration)
            if report.failed and call.excinfo is not None:
                from .failures import failure_evidence

                cases[case_id].failures.append(failure_evidence(call.excinfo.value, report.when))
    return report


def merge_reports(target: dict[str, SuiteCoverage], incoming: dict[str, SuiteCoverage]) -> None:
    """Merge distributed evidence only when workers agree on the same declaration and expected cases."""
    for suite, report in incoming.items():
        if suite not in target:
            target[suite] = report
            continue
        current = target[suite]
        assert current.source == report.source, f"{suite}: workers disagree on source location"
        assert (current.exploration is None) == (report.exploration is None)
        assert current.name == report.name and current.profiles.keys() == report.profiles.keys()
        for letter, profile in report.profiles.items():
            existing = current.profiles[letter]
            assert (existing.title, existing.assessment, existing.families, existing.cases.keys()) == (
                profile.title,
                profile.assessment,
                profile.families,
                profile.cases.keys(),
            ), f"{suite}/{letter}: workers disagree on expected profile coverage"
        for existing_cases, incoming_cases in zip(
            (*current.case_groups(), current.exploration or {}),
            (*report.case_groups(), report.exploration or {}),
            strict=True,
        ):
            assert existing_cases.keys() == incoming_cases.keys(), f"{suite}: workers disagree on expected checks"
            for case_id, case in incoming_cases.items():
                old = existing_cases[case_id]
                assert old.debt == case.debt, f"{suite}/{case_id}: workers disagree on declared debt"
                assert old.family == case.family
                old.collected |= case.collected
                old.selected |= case.selected
                for phase, outcomes in case.outcomes.items():
                    old.outcomes.setdefault(phase, []).extend(outcomes)
                old.failures.extend(case.failures)
                old.durations.extend(case.durations)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: object) -> None:
    """The dynamic xdist boundary returns metadata only, with no application values."""
    incoming = {
        name: SuiteCoverage.model_validate(value)
        for name, value in node.workeroutput.get("due_work_profiles", {}).items()
    }
    merge_reports(node.config.stash.setdefault(_REPORT, {}), incoming)


def pytest_sessionfinish(session: pytest.Session) -> None:
    destination = session.config.getoption("due_work_profile_report", default=None)
    from pathlib import Path

    from pydantic import TypeAdapter

    reports = session.config.stash.get(_REPORT, {})
    started = session.config.stash.get(_START, None)
    for report in reports.values():
        report.session_seconds = perf_counter() - started if started is not None else None
    # Computed verdicts are regenerated after xdist merging, never trusted as input.
    serialized = {name: report.model_dump(round_trip=True) for name, report in reports.items()}
    worker_output = getattr(session.config, "workeroutput", None)
    if worker_output is not None:
        worker_output["due_work_profiles"] = serialized
        return
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(TypeAdapter(dict[str, SuiteCoverage]).dump_json(reports, indent=2))


def _case_status(case: CaseEvidence) -> str:
    if case.passed:
        return "passed"
    if not case.collected:
        return "not collected"
    if not case.selected:
        return "deselected"
    phases = ", ".join(
        f"{phase}={','.join(case.outcomes.get(phase, [])) or 'missing'}" for phase in ("setup", "call", "teardown")
    )
    return f"incomplete ({phases})"


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Render the merged evidence without changing pytest's selection or exit status."""
    if not terminalreporter.config.getoption("due_work_summary", default=False):
        return
    reports = terminalreporter.config.stash.get(_REPORT, {})
    if not reports:
        return
    terminalreporter.section("due-work-harness: contract evidence (collected suites only)")
    for suite, report in sorted(reports.items()):
        verdict = "VERIFIED" if report.verified else "UNVERIFIED"
        terminalreporter.line(
            f"  {verdict}: {report.name} [{suite}]", green=report.verified, yellow=not report.verified
        )
        for letter, profile in sorted(report.profiles.items()):
            decision = "VERIFIED" if profile.verified else profile.assessment.state
            if decision == "claimed":
                decision = "UNVERIFIED (claimed)"
            reason = f"; {profile.assessment.because}" if profile.assessment.because else ""
            passed = sum(case.passed for case in profile.cases.values())
            terminalreporter.line(
                f"    {letter} {profile.title}: {decision}; {passed}/{len(profile.cases)} passed{reason}"
            )
            for family, assessment in sorted(profile.families.items()):
                reason = f"; {assessment.because}" if assessment.because else ""
                terminalreporter.line(f"      {family}: {assessment.state}{reason}")
            for case_id, case in sorted(profile.cases.items()):
                if not case.passed:
                    terminalreporter.line(f"      {case_id}: {_case_status(case)}")
        for case_id, case in sorted(report.additional_cases.items()):
            if not case.passed:
                terminalreporter.line(f"    {case_id}: {_case_status(case)}")
