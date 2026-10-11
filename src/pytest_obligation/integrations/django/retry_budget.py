"""Inspect Django selections for counter budgets contradicting profile J non-applicability.

This deliberately recognizes only integer column comparisons with attempt/retry/rearm
names. It does not certify the absence of application-level or annotated budgets.
"""

import re
from collections.abc import Callable
from typing import Any

from django.db.models import IntegerField, QuerySet
from django.db.models.expressions import Col
from django.db.models.lookups import Lookup
from django.db.models.sql.where import WhereNode

#: Integer columns that count one obligation's executions, retries or re-arms.
_RETRY_COUNTER = re.compile(r"attempt|retr(?:y|ies)|rearm", re.IGNORECASE)
#: The comparisons a selection makes against such a counter's budget ("fewer than N attempts").
_BUDGET_COMPARISONS = frozenset({"lt", "lte", "gt", "gte"})


def retry_budget_filters(selection: QuerySet[Any]) -> list[str]:
    """Every ``field__comparison`` the selection's WHERE clause makes on a retry counter, negated or not."""
    found: set[str] = set()
    pending: list[object] = [selection.query.where]
    while pending:
        node = pending.pop()
        if isinstance(node, WhereNode):
            pending.extend(node.children)
        elif (
            isinstance(node, Lookup)
            and node.lookup_name in _BUDGET_COMPARISONS
            and isinstance(node.lhs, Col)
            and isinstance(node.lhs.target, IntegerField)
            and _RETRY_COUNTER.search(node.lhs.target.name)
        ):
            found.add(f"{node.lhs.target.name}__{node.lookup_name}")
    return sorted(found)


def assert_selection_has_no_retry_budget(name: str, due_work: Callable[[], QuerySet[Any]]) -> None:
    """
    Profile J ``NotApplicable`` is refused while the production selection enforces a retry budget.

    ``NotApplicable`` says no execution budget exists. A recovery selection that compares an
    attempt, retry or re-arm counter with a limit is that budget: the community membership
    contract once declared J not applicable while its sweep selected ``attempts__lt=10``, and the
    exhausted rows the budget leaves behind went unproven. A time column (``retry_at``) is not a
    counter and does not count.
    """
    budget = retry_budget_filters(due_work())
    assert not budget, (
        f"{name}: profile J (Job Retry Limits) is declared NotApplicable, but the production selection "
        f"due_work() filters on {budget}, a retry budget. Claim profile J with a `retry=` BoundedRetry binding "
        f"over the same selection, or Decline it with the reason the counter is not a retry limit"
    )
