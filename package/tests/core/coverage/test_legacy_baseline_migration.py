import subprocess
from pathlib import Path

import pytest

from pytest_obligation.coverage.cli import _previous_baseline
from pytest_obligation.coverage.config import LegacyBaseline
from pytest_obligation.coverage.scan import baseline_growth


def test_migration_reads_reviewed_git_policy_not_the_edit_being_validated(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\n")
    policy = tmp_path / "policy.py"
    policy.write_text("LEGACY = {'sample.old': 1}\nUNPROVEN = frozenset({'sample.cache'})\n")
    git("add", ".")
    git("commit", "-qm", "test: reviewed policy")
    reviewed = git("rev-parse", "HEAD")
    policy.write_text("LEGACY = {'sample.old': 1, 'sample.proof_removed': 1}\nUNPROVEN = frozenset({'sample.cache'})\n")
    spec = LegacyBaseline(path="policy.py", mappings=("LEGACY",), sets=("UNPROVEN",))
    previous = _previous_baseline(tmp_path, reviewed, spec)
    assert previous is not None
    assert previous == {"sample.old": 1, "sample.cache": 1}
    assert baseline_growth({**previous, "sample.proof_removed": 1}, previous) == ["sample.proof_removed"]
    assert not baseline_growth({"sample.old": 1}, previous)
    with pytest.raises(ValueError, match="unavailable"):
        _previous_baseline(tmp_path, reviewed, LegacyBaseline(path="missing.py"))
