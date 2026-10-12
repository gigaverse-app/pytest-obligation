"""Polling proofs over the existing catalog's real SQLite reconciliation loop.

Run with the Django integration installed and tests.django.settings: the shared
row oracle observes Django writes as well as provider calls, even though this
application's durable owners live in SQLite.
"""

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import pytest

# The project's own `test` action collects this directory without the Django extra, as it
# skips Hypothesis-only cases; the django jobs run it with tests.django.settings.
pytest.importorskip("django")

from adopter_app.catalog import Catalog  # noqa: E402
from test_bindings import application  # noqa: E402

from pytest_obligation.integrations.django.owed_rows import (  # noqa: E402
    OwedRows,
    assert_a_polled_row_is_served_and_stays_selected,
    assert_the_loop_isolates_a_poisoned_row,
)
from pytest_obligation.poison import PoisonSwitch, PoisonUnreported  # noqa: E402


@contextmanager
def catalog_polling() -> Iterator[tuple[Catalog, OwedRows]]:
    with application() as state:
        catalog = state.catalog
        reads: Counter[int] = Counter()
        dispatched: list[int] = []
        switch = PoisonSwitch()
        read = catalog.read

        def checked_read(identity: int) -> str:
            dispatched.append(identity)
            switch.check(identity)
            reads[identity] += 1
            return read(identity)

        catalog.read = checked_read

        def make_owed() -> int:
            identity = catalog.admit("red")
            # Acknowledged owners still need remote reads: a late old write can undo them.
            catalog.execute(identity)
            return identity

        yield (
            catalog,
            OwedRows(
                make_owed=make_owed,
                identity_of=lambda identity: identity,
                execute=lambda identity: catalog.read(identity),
                run_tick=catalog.recover,
                dispatched_ids=lambda: dispatched,
                effect_calls_for=lambda identity: reads[identity],
                poison=switch.poisoned,
            ),
        )


def test_acknowledged_catalog_owners_are_polled_on_every_tick() -> None:
    with catalog_polling() as (catalog, rows):
        assert_a_polled_row_is_served_and_stays_selected("catalog remote reconciliation", catalog.eligible, rows)


def test_a_failed_catalog_read_is_isolated_and_reported_on_every_tick() -> None:
    with catalog_polling() as (catalog, rows):
        assert_the_loop_isolates_a_poisoned_row("catalog remote reconciliation", catalog.eligible, rows, polling=True)


@pytest.mark.parametrize("silent_from", [1, 2])
def test_suppressing_a_catalog_failure_cannot_pass_the_polling_proof(silent_from: int) -> None:
    with catalog_polling() as (catalog, rows):
        ticks = 0

        def silent_tick() -> None:
            nonlocal ticks
            ticks += 1
            if ticks < silent_from:
                catalog.recover()
            else:
                with suppress(ExceptionGroup):
                    catalog.recover()

        with pytest.raises(PoisonUnreported):
            assert_the_loop_isolates_a_poisoned_row(
                "catalog remote reconciliation",
                catalog.eligible,
                rows.model_copy(update={"run_tick": silent_tick}),
                polling=True,
            )
