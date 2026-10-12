"""Compile Django selection-completeness declarations, loading Hypothesis only on opt-in."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from functools import partial
from typing import Any

from pytest_obligation.contract import (
    Claim,
    ContractCase,
    ObligationContract,
    Profile,
    ScheduledSelection,
    _claims_recovery,
    _entered,
    _selection_gaps,
)
from pytest_obligation.integrations.django.owed_cases import retries_are_bounded


def selection_completeness_cases(contract: ObligationContract | ScheduledSelection) -> list[Any]:
    # This optional dependency is needed only when an adopter requests the generated proof.
    from pytest_obligation.integrations.django import selection_completeness as proof

    if isinstance(contract, ScheduledSelection):

        @contextmanager
        def enter() -> Iterator[proof.CompletenessBinding]:
            assert contract.owed_rows is not None
            with _entered(contract.owed_rows) as rows:
                yield proof.CompletenessBinding.of_rows(
                    contract.name,
                    contract.due_work,
                    rows,
                    state_fields=contract.state_fields,
                    excluded_states=contract.excluded_states,
                )

        return _cases(
            prefix="",
            profile=None,
            enter=enter,
            gaps=contract.gaps,
            transactional=True,
            commits=False,
            fixtures=contract.fixtures,
        )
    assert isinstance(contract, ObligationContract) and _claims_recovery(contract)

    @contextmanager
    def enter() -> Iterator[proof.CompletenessBinding]:
        assert contract.sweep is not None
        with _entered(contract.sweep) as sweep:
            yield proof.completeness_of_sweep(
                sweep, contract.owed_model or sweep.due_work().model, retries_bounded=retries_are_bounded(contract)
            )

    claim = contract.profiles[Profile.A]
    assert isinstance(claim, Claim)
    return _cases(
        prefix=f"{Profile.A.case_prefix}-",
        profile=Profile.A,
        enter=enter,
        gaps=claim.gaps,
        transactional=contract.transactional,
        commits=contract.transactional,
        fixtures=contract.fixtures,
    )


def _cases(
    *,
    prefix: str,
    profile: Profile | None,
    enter: Callable[[], AbstractContextManager[Any]],
    gaps: Mapping[str, str],
    transactional: bool,
    commits: bool,
    fixtures: tuple[str, ...],
) -> list[Any]:
    """The Hypothesis case, then one strict xfail per declared combination (see :mod:`.selection_completeness`)."""
    from pytest_obligation.integrations.django.selection_completeness import (
        GAP_FAILURES,
        assert_declared_gap_still_fails,
        assert_selection_is_complete,
    )
    from pytest_obligation.integrations.django.selection_completeness import PROOF_NAME as SELECTION_COMPLETENESS_PROOF

    _SELECTION_BUDGET_FIXTURES = ("due_work_selection_budget",)
    declared, _malformed = _selection_gaps(gaps)

    def run() -> None:
        # A transactional binding's tick needs autocommit; its examples commit instead of rolling back.
        assert_selection_is_complete(enter, gaps=declared, commits=commits)

    params: list[Any] = []
    case = ContractCase(
        id=f"{prefix}{SELECTION_COMPLETENESS_PROOF}",
        profile=profile,
        family="selection-completeness",
        run=run,
        fixtures=(*fixtures, *_SELECTION_BUDGET_FIXTURES),
    )
    params.append(case.parameter(transactional=transactional))
    for gap in declared:
        case = ContractCase(
            id=f"{prefix}{gap}",
            profile=profile,
            family="selection-completeness",
            run=partial(assert_declared_gap_still_fails, enter, gap, commits=commits),
            fixtures=fixtures,
        )
        # Only the invariant's own failure is the gap; a broken binding or example still fails.
        params.append(case.parameter(transactional=transactional, gap=gaps[gap], raises=GAP_FAILURES))
    return params
