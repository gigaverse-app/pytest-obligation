"""A real pytest session cannot go green by deleting generated native contract cases."""

import pytest

from tests.core.contract.child_suites import COLLECTION_SOURCE as SOURCE
from tests.core.contract.child_suites import run_collection_session as run


@pytest.mark.parametrize(
    "replacement",
    [
        'delattr(TestDebt, "test_safety_contract")',
        "TestDebt.test_safety_contract = lambda self: None",
    ],
)
def test_removed_or_replaced_generated_method_fails_collection(tmp_path, replacement):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_contract.py").write_text(SOURCE + "\n" + replacement + "\n")
    result = run(tmp_path, "--collect-only", "test_contract.py")
    assert result.returncode != 0
    assert "lost collected proofs" in result.stdout + result.stderr


def test_broad_and_narrow_selectors_still_require_the_whole_class(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_contract.py").write_text(SOURCE)
    (tmp_path / "conftest.py").write_text("""
def pytest_pycollect_makeitem(collector, name, obj):
    if name == "test_safety_contract":
        obj.pytestmark = [mark for mark in obj.pytestmark if mark.name != "parametrize"]
        import pytest
        obj.pytestmark.append(pytest.mark.parametrize("case", []))
""")
    result = run(tmp_path, "--collect-only", "test_contract.py", "test_contract.py::TestDebt")
    assert result.returncode != 0
    assert "lost collected proofs" in result.stdout + result.stderr
