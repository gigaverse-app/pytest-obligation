from textwrap import dedent

import pytest

from pytest_obligation.coverage.proof_calls import proof_calls


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            """
            from pytest_obligation.profiles.automatic_recovery.sweep import (
                assert_one_failing_row_does_not_stall_the_tick,
            )

            def test_by_hand():
                assert_one_failing_row_does_not_stall_the_tick(name="x")
            """,
            ["assert_one_failing_row_does_not_stall_the_tick"],
        ),
        (
            """
            def test_imported_inside_the_test():
                from pytest_obligation.profiles.automatic_recovery.sweep import (
                    assert_plan_is_index_served as served,
                )
                served(name="x")
            """,
            ["served"],
        ),
        (
            """
            from pytest_obligation.contract import ExtraProof
            from pytest_obligation.profiles.bounded_ownership import (
                assert_the_lease_outlives_the_work,
            )

            def _lease():
                assert_the_lease_outlives_the_work(name="x")

            EXTRA = ExtraProof(name="lease", run=_lease)
            """,
            [],
        ),
        (
            """
            from shop.tests.helpers import assert_sent

            def test_product():
                assert_sent()
            """,
            [],
        ),
        (
            """
            from pytest_obligation.profiles.automatic_recovery import sweep as checks

            def test_through_the_module():
                checks.assert_one_failing_row_does_not_stall_the_tick(name="x")
            """,
            ["assert_one_failing_row_does_not_stall_the_tick"],
        ),
        (
            """
            from pytest_obligation import contract
            from pytest_obligation.profiles.bounded_ownership import (
                assert_the_lease_outlives_the_work,
            )

            def _lease():
                assert_the_lease_outlives_the_work(name="x")

            EXTRA = contract.ExtraProof(name="lease", run=_lease)
            """,
            [],
        ),
        (
            """
            from pytest_obligation.contract import ExtraProof
            from pytest_obligation.profiles.bounded_ownership import (
                assert_the_lease_outlives_the_work,
            )

            def _lease():
                assert_the_lease_outlives_the_work(name="x")

            class TestByHand:
                def _lease(self):
                    assert_the_lease_outlives_the_work(name="x")

            EXTRA = ExtraProof(name="lease", run=_lease)
            """,
            ["assert_the_lease_outlives_the_work"],
        ),
        (
            """
            from pytest_obligation.contract import ExtraProof
            from pytest_obligation.profiles.bounded_ownership import (
                assert_the_lease_outlives_the_work,
            )

            def _lease():
                assert_the_lease_outlives_the_work(name="x")

            LAMBDA = ExtraProof(name="lease", run=lambda: assert_the_lease_outlives_the_work(name="y"))
            POSITIONAL = ExtraProof("lease", _lease)
            """,
            [],
        ),
        (
            """
            import pytest_obligation.profiles.automatic_recovery.sweep

            def test_fully_dotted():
                pytest_obligation.profiles.automatic_recovery.sweep.assert_x(name="x")
            """,
            ["assert_x"],
        ),
        (
            """
            from due.django import conformance as due_work
            from pytest_obligation.profiles import automatic_recovery as recovery

            def test_through_parent_modules():
                due_work.profiles.automatic_recovery.sweep.assert_x(name="x")
                recovery.sweep.assert_y(name="y")
            """,
            ["assert_x", "assert_y"],
        ),
    ],
    ids=[
        "module-import",
        "local-import-alias",
        "extra-proof-runner",
        "not-a-harness-proof",
        "through-a-module-alias",
        "extra-proof-by-attribute",
        "same-name-method-is-not-the-runner",
        "lambda-and-positional-runners",
        "fully-dotted-import",
        "parent-module-aliases",
    ],
)
def test_the_scan_finds_hand_calls_and_spares_extra_proof_runners(source: str, expected: list[str]) -> None:
    assert [call.proof for call in proof_calls("adopter.py", dedent(source))] == expected


def test_reviewed_proof_calls_must_exist_and_have_reasons():
    from pytest_obligation.coverage.proof_calls import assert_declared_proofs

    sources = {
        "test_app.py": "from pytest_obligation.poison import assert_poison_is_isolated\nassert_poison_is_isolated(x)"
    }
    key = ("test_app.py", "assert_poison_is_isolated")
    with pytest.raises(AssertionError, match="unreviewed"):
        assert_declared_proofs(sources, reviewed={})
    assert_declared_proofs(sources, reviewed={key: "checks application-specific reporting alongside the oracle"})
    with pytest.raises(AssertionError, match="stale"):
        assert_declared_proofs({}, reviewed={key: "an old call that was subsequently removed"})


@pytest.mark.parametrize(
    "source",
    [
        "from pytest_obligation.evidence.observation import assert_observation as check\ncheck(actual, expected)",
        "import pytest_obligation.evidence.observation as checks\nchecks.assert_observation(actual, expected)",
        "from due.django import conformance as checks\nchecks.assert_observation(actual, expected)",
    ],
)
def test_observation_equality_is_not_a_standalone_proof(source: str) -> None:
    assert list(proof_calls("test_product.py", source)) == []


@pytest.mark.parametrize(
    ("imports", "wrapper"),
    [
        ("from functools import partial", "partial"),
        ("from functools import partial as bind", "bind"),
        ("import functools", "functools.partial"),
        ("import functools as ft", "ft.partial"),
    ],
)
def test_configured_extra_proof_spares_only_its_runner(imports: str, wrapper: str) -> None:
    source = f"""
{imports}
from pytest_obligation.contract import ExtraProof
from pytest_obligation.poison import assert_poison_is_isolated

def configured(kind):
    assert_poison_is_isolated(kind)

def undeclared():
    assert_poison_is_isolated('other')

EXTRA = ExtraProof('poison', {wrapper}(configured, 'channel'))
"""
    calls = list(proof_calls("adopter.py", source))
    assert [(call.proof, call.line) for call in calls] == [("assert_poison_is_isolated", 10)]


@pytest.mark.parametrize(
    "wrapper",
    [
        "from another_library import partial",
        "def partial(*args): return args",
        "from functools import partial\npartial = another_callable",
    ],
)
def test_an_unrecognized_or_rebound_partial_cannot_hide_a_proof(wrapper: str) -> None:
    source = f"""
{wrapper}
from pytest_obligation.contract import ExtraProof
from pytest_obligation.poison import assert_poison_is_isolated

def configured(kind):
    assert_poison_is_isolated(kind)

EXTRA = ExtraProof('poison', partial(configured, 'channel'))
"""
    assert [call.proof for call in proof_calls("adopter.py", source)] == ["assert_poison_is_isolated"]


@pytest.mark.parametrize(
    "shadow",
    [
        "def configure(partial):\n    return ExtraProof('x', partial(configured))",
        "def partial(*args): return args",
        "from unrelated import partial",
    ],
)
def test_shadowed_partial_is_not_a_declaration_escape(shadow: str) -> None:
    source = f"""
from functools import partial
from pytest_obligation.contract import ExtraProof
from pytest_obligation.poison import assert_poison_is_isolated

def configured():
    assert_poison_is_isolated(history)

{shadow}
EXTRA = ExtraProof('x', partial(configured))
"""
    assert [call.proof for call in proof_calls("adopter.py", source)] == ["assert_poison_is_isolated"]


def test_partial_lambda_and_nested_binding_are_recognized() -> None:
    source = """
from functools import partial
from pytest_obligation.contract import ExtraProof
from pytest_obligation.poison import assert_poison_is_isolated
EXTRA = ExtraProof('x', partial(partial(lambda h: assert_poison_is_isolated(h), history)))
"""
    assert list(proof_calls("adopter.py", source)) == []


def test_replaced_module_partial_does_not_hide_a_proof() -> None:
    source = """
import functools
from pytest_obligation.contract import ExtraProof
from pytest_obligation.poison import assert_poison_is_isolated
functools.partial = another_callable

def configured():
    assert_poison_is_isolated(history)

EXTRA = ExtraProof('x', functools.partial(configured))
"""
    assert [call.proof for call in proof_calls("adopter.py", source)] == ["assert_poison_is_isolated"]
