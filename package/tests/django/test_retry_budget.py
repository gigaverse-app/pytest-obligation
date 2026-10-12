"""Reject profile J non-applicability when a Django selection has a retry counter budget."""

from datetime import timedelta
from typing import Any

import pytest
from django.db import models
from django.test.utils import isolate_apps
from django.utils import timezone

from pytest_obligation.contract import Claim, NotApplicable, ObligationContract, Profile, contract_cases
from pytest_obligation.integrations.django.retry_budget import retry_budget_filters
from pytest_obligation.profiles.automatic_recovery import DueWorkSweep

WHY = "root control: unrelated profiles are outside this proof"

with isolate_apps("pytest_obligation"):

    class CountedWork(models.Model):
        """Columns named like retry counters, of both kinds: integer counters and a retry time."""

        attempts = models.PositiveIntegerField(default=0)
        rearm_count = models.PositiveIntegerField(default=0)
        retry_at = models.DateTimeField(null=True)
        payload = models.CharField(max_length=40)

        class Meta:
            app_label = "tests"


# --- Profile J NotApplicable against a retry budget -----------------------------------------


@pytest.mark.parametrize(
    ("selection", "budget"),
    [
        pytest.param(lambda: CountedWork.objects.filter(attempts__lt=3), ["attempts__lt"], id="attempts-limit"),
        pytest.param(lambda: CountedWork.objects.exclude(rearm_count__gte=2), ["rearm_count__gte"], id="negated"),
        pytest.param(lambda: CountedWork.objects.filter(attempts=0), [], id="first-attempt-equality"),
        pytest.param(lambda: CountedWork.objects.filter(retry_at__lte=timezone.now()), [], id="retry-time"),
        pytest.param(lambda: CountedWork.objects.filter(payload__lt="m"), [], id="other-column"),
    ],
)
def test_a_retry_budget_is_a_counter_comparison_in_the_selection(selection: Any, budget: list[str]) -> None:
    assert retry_budget_filters(selection()) == budget


def _budgeted_sweep() -> DueWorkSweep:
    # ARRANGE — no rows; the guard reads the selection's WHERE clause only.
    # REAL PRODUCTION — none; this root self-test stands in for an adopter's sweep.
    # EXTERNAL SEAM — none; nothing is dispatched.
    # OBSERVE — the generated J row inspects due_work() and nothing else.
    return DueWorkSweep(
        name="budgeted self-test sweep",
        due_work=lambda: CountedWork.objects.filter(attempts__lt=10, retry_at__lte=timezone.now()),
        run_tick=lambda: 0,
        make_owed=lambda **_: None,
        make_terminal=lambda **_: [],
        recovery_delay=timedelta(0),
        page_size=None,
    )


def _unbudgeted_sweep() -> DueWorkSweep:
    # ARRANGE — no rows; the guard reads the selection's WHERE clause only.
    # REAL PRODUCTION — none; this root self-test stands in for an adopter's sweep.
    # EXTERNAL SEAM — none; nothing is dispatched.
    # OBSERVE — the generated J row inspects due_work() and nothing else.
    return _budgeted_sweep().model_copy(
        update={"due_work": lambda: CountedWork.objects.filter(retry_at__lte=timezone.now())}
    )


def _retry_row(sweep: Any) -> Any:
    profiles: dict[Profile, Any] = {profile: NotApplicable(WHY) for profile in Profile}
    contract = ObligationContract(
        name="J self-test",
        profiles={**profiles, Profile.A: Claim()},
        sweep=sweep,
    )
    return next(param for param in contract_cases(contract) if param.id == "BOUNDED_RETRY-not_applicable")


def test_a_j_not_applicable_row_refuses_a_sweep_that_keeps_a_retry_budget() -> None:
    row = _retry_row(_budgeted_sweep)
    assert isinstance(row.values[0].assessment, NotApplicable)
    assert [mark.name for mark in row.marks] == ["django_db"]
    with pytest.raises(AssertionError, match=r"filters on \['attempts__lt'\], a retry budget"):
        row.values[0].run()


def test_a_j_not_applicable_row_accepts_a_sweep_without_one() -> None:
    _retry_row(_unbudgeted_sweep).values[0].run()
