from pathlib import Path

import pytest

from pytest_obligation.debt import assert_debt_baseline


def seed(root: Path, ticket: str = "ENG-123") -> None:
    (root / "test_domain.py").write_text("class TestDomain: pass\n")
    (root / "due_work_debt_baseline.yaml").write_text(
        "suites:\n- suite: test_domain.TestDomain\n  debt:\n"
        f"  - case: missing-recovery\n    kind: known-defect\n    ticket: {ticket}\n    reason: existing bug\n"
    )


def test_global_debt_audit_rejects_a_removed_suite_even_when_it_cannot_be_collected(tmp_path: Path) -> None:
    seed(tmp_path)
    assert_debt_baseline(tmp_path)
    (tmp_path / "test_domain.py").write_text("class TestRenamed: pass\n")
    with pytest.raises(AssertionError, match="no longer exists"):
        assert_debt_baseline(tmp_path)


def test_global_debt_audit_does_not_allow_new_or_reusable_unticketed_slots(tmp_path: Path) -> None:
    seed(tmp_path, "TODO")
    with pytest.raises(AssertionError, match="reviewed ceiling 0"):
        assert_debt_baseline(tmp_path)
    assert_debt_baseline(tmp_path, unticketed_ceiling=1)
    seed(tmp_path)
    with pytest.raises(AssertionError, match="allowances must be lowered"):
        assert_debt_baseline(tmp_path, unticketed_ceiling=1)
