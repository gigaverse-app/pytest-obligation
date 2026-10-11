from pathlib import Path

import pytest

from pytest_obligation.coverage import scan

from .builders import write_project


@pytest.mark.parametrize(
    "decorator_module, valid",
    [
        ("due.django.conformance.suite", True),
        ("application_tests", False),
    ],
)
def test_due_effect_suite_accounts_for_exact_producer(tmp_path: Path, decorator_module: str, valid: bool):
    report = scan(
        write_project(
            tmp_path,
            {
                "shop/orders.py": """
            from django.db import transaction
            def place():
                transaction.on_commit(notify)
            obligation = build_capability()
        """,
                "tests/test_orders.py": f"""
            from shop.orders import place, obligation
            from pytest_obligation import DueWorkSource
            from {decorator_module} import effect_contract_suite
            @effect_contract_suite(obligation, examples=examples, covers=(DueWorkSource(place),))
            class TestOrders:
                pass
        """,
            },
        )
    )
    if valid:
        assert not report.problems
        assert report.dispositions["shop.orders.place"].how == "covered"
    else:
        assert report.problems
        assert "shop.orders.place" not in report.dispositions
