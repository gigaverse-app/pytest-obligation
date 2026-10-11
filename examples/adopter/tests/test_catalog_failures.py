"""Sensitivity controls: break application behavior, then replay the generated failure."""

from collections.abc import Callable
from typing import Any

import pytest
from adopter_app.catalog import Catalog
from test_bindings import catalog_contract, recovery_failures

from pytest_obligation.interleavings import HistoryTrace, InterleavingFailure, replay_history
from pytest_obligation.poison import PoisonDropped, PoisonStalled, PoisonUnreported, StopRequestIsolated


def forget_remote_drift(original: Callable[..., None]) -> Callable[..., None]:
    """Mutation: trust local acknowledgements, even after a late remote request overwrites them."""

    def initialize(self: Catalog, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.read = lambda identity: self.reserved(identity)[1]

    return initialize


def discard_earlier_receipts(original: Callable[..., None]) -> Callable[..., None]:
    """Mutation: a later partial provider result replaces facts that were already committed."""

    def initialize(self: Catalog, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self.db.execute("CREATE TRIGGER replace_receipts BEFORE INSERT ON receipts BEGIN DELETE FROM receipts; END")

    return initialize


@pytest.mark.parametrize(
    "family, mutation",
    [
        ("in_flight", forget_remote_drift),
        ("evidence_confluence", discard_earlier_receipts),
    ],
)
def test_generated_histories_detect_and_replay_application_defects(
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    mutation: Callable[..., Any],
) -> None:
    contract = catalog_contract("sensitivity control")
    scenarios = contract.in_flight if family == "in_flight" else contract.evidence_confluence
    scenario = next(iter(scenarios.values()))
    monkeypatch.setattr(Catalog, "__init__", mutation(Catalog.__init__))
    failure = None
    for history in scenario.histories():
        try:
            scenario.run(history)
        except InterleavingFailure as error:
            failure = error
            break
    assert failure is not None, "the generated catalog never exposed the deliberate application defect"
    trace = HistoryTrace.model_validate_json(failure.__notes__[-1])
    # JSON round-trip and fresh SQL state: reproduction needs neither the original
    # process state nor Hypothesis. The precise invariant must fail again.
    with pytest.raises(InterleavingFailure) as replayed:
        replay_history(scenario, trace)
    assert replayed.value.invariant == failure.invariant


def test_optional_search_runs_the_actual_catalog() -> None:
    pytest.importorskip("hypothesis")
    from pytest_obligation.interleavings.exploration.hypothesis import explore

    scenario = catalog_contract("search control").in_flight["catalog revisions"]
    explore(scenario, max_examples=30, max_steps=20)


@pytest.mark.parametrize(
    "defect, expected",
    [
        ("abort", PoisonStalled),
        ("drop", PoisonDropped),
        ("silence", PoisonUnreported),
        ("isolate-stop", StopRequestIsolated),
    ],
)
def test_recovery_proofs_reject_broken_application_loops(
    monkeypatch: pytest.MonkeyPatch, defect: str, expected: type[AssertionError]
) -> None:
    def broken_recovery(catalog: Catalog) -> None:
        failures = []
        for identity in catalog.eligible():
            try:
                catalog.execute(identity)
            except Exception as error:
                if defect == "abort":
                    raise
                if defect == "drop":
                    with catalog.db:
                        catalog.db.execute("DELETE FROM obligations WHERE id=?", (identity,))
                failures.append(error)
        if failures and defect != "silence":
            raise ExceptionGroup("failed recovery", failures)

    monkeypatch.setattr(Catalog, "recover", broken_recovery)
    with pytest.raises(expected):
        recovery_failures(stop=defect == "isolate-stop")


def test_catalog_declaration_names_its_application_under_a_framework_host() -> None:
    from pytest_obligation.host import Host, current_host, hosted

    # Framework jobs have not enrolled adopter_app when they import the shared declaration.
    framework = Host(production_packages=frozenset({"unrelated_framework"}))
    with hosted(framework):
        contract = catalog_contract("catalog under framework host")
        assert current_host() is framework
        for proof in contract.extras:
            proof.run()
