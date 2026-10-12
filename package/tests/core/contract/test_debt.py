"""
Generated expected failures are debt the baseline must mirror; a J NotApplicable is checked against the sweep.

The session plugin's selection rules (whole suite, keyword subset, node-id narrowing) run in child
sessions: ``durable_work/tests/conformance/test_conformance_collection_debt.py``. These tests cover
what the plugin calls: the debt a declaration generates and the comparison with the baseline.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pytest_obligation.contract import (
    Adoption,
    ExtraProof,
    KnownGap,
    NotAssessed,
    ObligationContract,
    Profile,
    declared_debt,
    due_work_contract_suite,
    suite_cases,
)
from pytest_obligation.debt import (
    BASELINE,
    UNTICKETED,
    UPDATE_ENVIRONMENT,
    DebtEntry,
    debt_mismatch,
    load_baseline,
)
from tests.core.contract.declarations import (
    REFERENCE_CONTRACT,
    SELF_TEST_NO_PRODUCTION,
    annotated_missing_extra,
)

SUITE = "tests.self_test.TestSuite"
DEFECT = "self-test: a known production defect"


def _legacy_reference() -> ObligationContract:
    """The reference contract with one KnownGap disposition and one gapped extra, as the specimen declares them."""
    return REFERENCE_CONTRACT.model_copy(
        update=dict(
            adoption=Adoption.LEGACY,
            profiles={**REFERENCE_CONTRACT.profiles, Profile.A: KnownGap(DEFECT)},
            extras=REFERENCE_CONTRACT.extras
            + (
                ExtraProof(
                    name="known-broken-extra",
                    run=annotated_missing_extra,
                    gap=DEFECT,
                    no_production_callable_because=SELF_TEST_NO_PRODUCTION,
                ),
            ),
        )
    )


def _plant(root: Path, entries: list[DebtEntry]) -> None:
    document = {"suites": [{"suite": SUITE, "debt": [entry.model_dump(exclude_none=True) for entry in entries]}]}
    (root / BASELINE).parent.mkdir(parents=True, exist_ok=True)
    (root / BASELINE).write_text(yaml.safe_dump(document), encoding="utf-8")


# --- The debt a declaration generates -------------------------------------------------------


def test_declared_debt_is_exactly_the_generated_strict_xfails() -> None:
    """Every xfail-marked case is debt and nothing else is, whatever gap shape produced the mark."""
    params = suite_cases(_legacy_reference())
    xfailed = {param.id for param in params if any(mark.name == "xfail" for mark in param.marks)}
    debt = declared_debt(params)
    assert [entry.case for entry in debt] == [param.id for param in params if param.id in xfailed]
    assert {"A-known_gap", "extra-known-broken-extra"} <= xfailed


def test_not_assessed_rows_are_binding_debt_and_every_other_gap_a_known_defect() -> None:
    params = suite_cases(_legacy_reference())
    assessments = {param.id: param.values[0].assessment for param in params}
    debt = {entry.case: entry for entry in declared_debt(params)}
    binding = {case for case, assessment in assessments.items() if isinstance(assessment, NotAssessed)}
    assert binding and {case for case, entry in debt.items() if entry.kind == "binding-debt"} == binding
    assert all(debt[case].reason == assessments[case].because for case in binding)
    assert (debt["A-known_gap"].kind, debt["A-known_gap"].reason) == ("known-defect", DEFECT)
    assert (debt["extra-known-broken-extra"].kind, debt["extra-known-broken-extra"].reason) == ("known-defect", DEFECT)


# --- Comparison with the baseline -----------------------------------------------------------


def _debt() -> list[DebtEntry]:
    return declared_debt(suite_cases(_legacy_reference()))


def _ticketed(entries: list[DebtEntry]) -> list[DebtEntry]:
    return [entry.model_copy(update={"ticket": "BE-1"}) if entry.kind == "known-defect" else entry for entry in entries]


def test_a_matching_baseline_has_no_mismatch(tmp_path: Path) -> None:
    _plant(tmp_path, _ticketed(_debt()))
    assert debt_mismatch(SUITE, _debt(), tmp_path) is None


def test_reasons_are_informational(tmp_path: Path) -> None:
    _plant(tmp_path, [entry.model_copy(update={"reason": "reworded"}) for entry in _ticketed(_debt())])
    assert debt_mismatch(SUITE, _debt(), tmp_path) is None


def test_a_new_expected_failure_is_refused_with_the_entry_to_add(tmp_path: Path) -> None:
    *recorded, added = _ticketed(_debt())
    _plant(tmp_path, recorded)
    message = debt_mismatch(SUITE, _debt(), tmp_path)
    assert message is not None and "New expected failures (1)" in message
    assert f"case: {added.case}" in message and "Stale" not in message
    assert "bind the profile's production seam" in message


def test_an_entry_whose_expected_failure_is_gone_is_stale(tmp_path: Path) -> None:
    gone = DebtEntry(case="A-removed-gap", kind="known-defect", ticket="BE-2", reason=DEFECT)
    _plant(tmp_path, [*_ticketed(_debt()), gone])
    message = debt_mismatch(SUITE, _debt(), tmp_path)
    assert message is not None and "Stale entries (1)" in message and "- A-removed-gap" in message
    assert "New expected failures" not in message


def test_a_changed_kind_is_a_mismatch(tmp_path: Path) -> None:
    entries = _ticketed(_debt())
    first = next(index for index, entry in enumerate(entries) if entry.kind == "binding-debt")
    entries[first] = entries[first].model_copy(update={"kind": "known-defect", "ticket": "BE-3"})
    _plant(tmp_path, entries)
    message = debt_mismatch(SUITE, _debt(), tmp_path)
    assert message is not None and "declared binding-debt, baselined known-defect" in message


@pytest.mark.parametrize(
    ("ticket", "refused"),
    [
        pytest.param(None, "needs the issue key or URL of its fix", id="missing"),
        pytest.param("soon", "is not a issue key or URL", id="not-a-key"),
        pytest.param(UNTICKETED, None, id="imported-untracked"),
    ],
)
def test_a_known_defect_names_its_ticket(tmp_path: Path, ticket: str | None, refused: str | None) -> None:
    entries = [
        entry.model_copy(update={"ticket": ticket}) if entry.kind == "known-defect" else entry for entry in _debt()
    ]
    _plant(tmp_path, entries)
    message = debt_mismatch(SUITE, _debt(), tmp_path)
    if refused is None:
        assert message is None
    else:
        assert message is not None and refused in message


def test_update_mode_rewrites_the_suite_and_keeps_surviving_tickets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = DebtEntry(case="A-removed-gap", kind="known-defect", ticket="BE-2", reason=DEFECT)
    _plant(tmp_path, [*_ticketed(_debt())[:-1], stale])
    monkeypatch.setenv(UPDATE_ENVIRONMENT, "update")
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert debt_mismatch(SUITE, _debt(), tmp_path) is None
    monkeypatch.delenv(UPDATE_ENVIRONMENT)
    rewritten = load_baseline(tmp_path).of(SUITE)
    assert [entry.case for entry in rewritten] == [entry.case for entry in _debt()]
    tickets = {entry.case: entry.ticket for entry in rewritten}
    assert tickets["A-known_gap"] == "BE-1" and tickets["extra-known-broken-extra"] is None
    assert b"\r\n" not in (tmp_path / BASELINE).read_bytes()


def test_the_generated_suite_carries_its_own_check(tmp_path: Path) -> None:
    """The decorator attaches the comparison keyed by the suite class, so the plugin imports nothing."""

    @due_work_contract_suite(REFERENCE_CONTRACT)
    class TestReference:
        pass

    # The plugin reads the same dynamic attribute; it is installed by the decorator, not declared on a type.
    check: Callable[[Path], str | None] = getattr(TestReference, "__due_work_debt__")  # noqa: B009 - decorator metadata
    message = check(tmp_path)
    assert message is not None
    assert message.startswith(f"{TestReference.__module__}.{TestReference.__qualname__}: ")
    assert f"New expected failures ({len(declared_debt(suite_cases(REFERENCE_CONTRACT)))})" in message
