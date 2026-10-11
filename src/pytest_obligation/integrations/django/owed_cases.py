"""Django owed-row case generation for both public contract surfaces."""

from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

import pytest
from django.db.models import Model

from pytest_obligation.contract import (
    Claim,
    ContractCase,
    ObligationContract,
    Profile,
    ScheduledSelection,
    _entered,
    _proof_runner,
)
from pytest_obligation.host import current_host
from pytest_obligation.integrations.django.edge_values import CandidateEdge, model_edges
from pytest_obligation.integrations.django.owed_rows import (
    NOTHING_ENDS_A_FAILURE,
    OWED_ROW_PROOFS,
    EdgeFamily,
    OwedRowNotHandled,
    OwedRowProof,
    OwedRows,
    assert_a_soft_time_limit_ends_the_loop,
    assert_owed_row_bindings_are_production_bound,
    assert_the_loop_isolates_a_poisoned_row,
    assert_the_tick_dispatches_owed_rows_in_selection_order,
    assert_valid_owed_row_leaves_the_selection,
    failure_ends_of_sweep,
    owed_rows_of_sweep,
)
from pytest_obligation.models import HarnessModel
from pytest_obligation.poison import poison_gap, poison_gap_names, stop_gap, stop_gap_names
from pytest_obligation.profiles.automatic_recovery import (
    assert_a_soft_time_limit_ends_the_tick,
    assert_one_poisoned_identity_does_not_stall_the_tick,
)


def owed_row_edges(contract: ObligationContract) -> tuple[CandidateEdge, ...]:
    return model_edges(contract.owed_model) if contract.owed_model is not None else ()


def _owed_row_runner(
    sweep_factory: Callable[[], Any],
    model: type[Model],
    proof: OwedRowProof,
    edge: CandidateEdge,
    *,
    retries_bounded: bool,
) -> Callable[[], None]:
    def run() -> None:
        with _entered(sweep_factory) as sweep:
            ends = failure_ends_of_sweep(sweep, retries_bounded=retries_bounded)
            proof(sweep.name, sweep.due_work, EdgeFamily(model=model), edge, owed_rows_of_sweep(sweep, model), ends)

    return run


def retries_are_bounded(contract: ObligationContract) -> bool:
    """Only a gapless J claim proves persistently failing work ends at its budget."""
    disposition = contract.profiles[Profile.J]
    return isinstance(disposition, Claim) and not disposition.gaps


def _owed_row_cases(contract: ObligationContract) -> list[Any]:
    """Two cases per database-legal edge value of the swept model (see :mod:`.owed_rows`)."""
    edges = owed_row_edges(contract)
    if not edges:
        return []
    assert contract.sweep is not None and contract.owed_model is not None
    disposition = contract.profiles[Profile.A]
    assert isinstance(disposition, Claim)
    params: list[Any] = []
    for name, proof in OWED_ROW_PROOFS.items():
        for edge in edges:
            key = f"{name}[{edge.id}]"
            marks: list[Any] = list(current_host().database_marks(True))
            if reason := disposition.gaps.get(key):
                # Only the invariant's own failure is the gap; a broken example still fails.
                marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=OwedRowNotHandled))
            case = ContractCase(
                id=f"{Profile.A.case_prefix}-{key}",
                profile=Profile.A,
                family="owed-row-admissibility",
                run=_owed_row_runner(
                    contract.sweep, contract.owed_model, proof, edge, retries_bounded=retries_are_bounded(contract)
                ),
                fixtures=contract.fixtures,
            )
            params.append(pytest.param(case, id=case.id, marks=marks))
    return params


#: Profile A's invariant 12, generated for a light contract's loop under the same case id.
_LOOP_POISON_CASE = assert_one_poisoned_identity_does_not_stall_the_tick.__name__
#: Profile A's invariant 12b (the same seam raising Celery's soft limit), likewise.
_LOOP_STOP_CASE = assert_a_soft_time_limit_ends_the_tick.__name__


def _named_failure_gap(gaps: Mapping[str, str], proof: str) -> tuple[str, type[AssertionError]] | None:
    """
    The ``"<proof>[<kind>]"`` gap declared on invariant 12 or 12b, as (reason, the failure it expects).

    Each proof resolves against its own failures: both name a ``dropped`` kind.
    """
    if proof == _LOOP_POISON_CASE:
        return poison_gap(gaps, proof)
    if proof == _LOOP_STOP_CASE:
        return stop_gap(gaps, proof)
    return None


class _OwedRowEdgeCase(HarnessModel):
    key: str
    proof: OwedRowProof
    family: EdgeFamily
    edge: CandidateEdge


def _owed_row_edge_cases(selection: ScheduledSelection) -> list[_OwedRowEdgeCase]:
    """Every per-edge owed-row case of a light contract; collection and gap-key validation share this list."""
    return [
        _OwedRowEdgeCase(key=f"{proof_name}[{family_name}-{edge.id}]", proof=proof, family=family, edge=edge)
        for proof_name, proof in OWED_ROW_PROOFS.items()
        for family_name, family in selection.owed_edges.items()
        for edge in model_edges(family.model)
    ]


def owed_row_case_keys(selection: ScheduledSelection) -> list[str]:
    return [case.key for case in _owed_row_edge_cases(selection)]


def _owed_row_selection_cases(selection: ScheduledSelection) -> list[Any]:
    """The light contract's owed-row proofs: guard and controls first, then the poison case, then two per edge."""
    if selection.owed_rows is None:
        return []
    name, due_work = selection.name, selection.due_work
    checks: list[tuple[str, Callable[[OwedRows], None], type[AssertionError] | None]] = [
        (
            assert_owed_row_bindings_are_production_bound.__name__,
            partial(assert_owed_row_bindings_are_production_bound, name),
            None,
        ),
        (
            assert_valid_owed_row_leaves_the_selection.__name__,
            partial(assert_valid_owed_row_leaves_the_selection, name, due_work),
            None,
        ),
        (
            assert_the_tick_dispatches_owed_rows_in_selection_order.__name__,
            partial(assert_the_tick_dispatches_owed_rows_in_selection_order, name, due_work),
            None,
        ),
        (_LOOP_POISON_CASE, partial(assert_the_loop_isolates_a_poisoned_row, name, due_work), None),
        (_LOOP_STOP_CASE, partial(assert_a_soft_time_limit_ends_the_loop, name, due_work), None),
    ]
    checks.extend(
        (
            case.key,
            lambda rows, case=case: case.proof(name, due_work, case.family, case.edge, rows, NOTHING_ENDS_A_FAILURE),
            OwedRowNotHandled,
        )
        for case in _owed_row_edge_cases(selection)
    )
    params: list[Any] = []
    for case_id, check, invariant_failure in checks:
        # On-commit handoffs (a dispatcher scheduled after commit) are only visible with real commits.
        marks: list[Any] = list(current_host().database_marks(True))
        if declared := _named_failure_gap(selection.gaps, case_id):
            # Only the one failure the gap names; another failure or a broken binding still fails.
            reason, failure = declared
            marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=failure))
        elif reason := selection.gaps.get(case_id):
            assert invariant_failure is not None, f"{case_id} is unwaivable; __post_init__ rejects its gap"
            # Only the invariant's own failure is the gap; a broken binding or control still fails.
            marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=invariant_failure))
        case = ContractCase(id=case_id, run=_proof_runner(selection.owed_rows, check), fixtures=selection.fixtures)
        params.append(pytest.param(case, id=case.id, marks=marks))
    return params


def owed_row_gap_names(contract: ObligationContract | ScheduledSelection) -> set[str]:
    if isinstance(contract, ObligationContract):
        return {f"{proof}[{edge.id}]" for edge in owed_row_edges(contract) for proof in OWED_ROW_PROOFS}
    if contract.owed_rows is None:
        return set()
    return set(owed_row_case_keys(contract)) | poison_gap_names(_LOOP_POISON_CASE) | stop_gap_names(_LOOP_STOP_CASE)


def owed_row_cases(contract: ObligationContract | ScheduledSelection) -> list[Any]:
    return (
        _owed_row_cases(contract) if isinstance(contract, ObligationContract) else _owed_row_selection_cases(contract)
    )
