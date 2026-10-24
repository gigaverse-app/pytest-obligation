"""Cache identity changes with collection inputs, not unrelated edits or venv files."""

import subprocess
from pathlib import Path

import pytest

from pytest_obligation.reporting.cache_key import fingerprint


def test_collection_key_tracks_source_lock_new_files_and_runtime(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("version = 1\n")
    (tmp_path / "uv.lock").write_text("locked dependencies")
    (tmp_path / "README.md").write_text("prose")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    inputs = ["src", "uv.lock"]
    initial = fingerprint(tmp_path, inputs, "python3.14;pytest")
    (tmp_path / "README.md").write_text("changed prose")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/pyproject.toml").write_text("not a collection input")
    assert fingerprint(tmp_path, inputs, "python3.14;pytest") == initial
    assert fingerprint(tmp_path, inputs, "python3.13;pytest") != initial
    (tmp_path / "src/app.py").write_text("version = 2\n")
    changed_source = fingerprint(tmp_path, inputs, "python3.14;pytest")
    assert changed_source != initial
    (tmp_path / "uv.lock").write_text("new locked dependencies")
    changed_lock = fingerprint(tmp_path, inputs, "python3.14;pytest")
    assert changed_lock != changed_source
    (tmp_path / "src/another.py").write_text("new application")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/another.py"], check=True)
    assert fingerprint(tmp_path, inputs, "python3.14;pytest") != changed_lock


@pytest.mark.parametrize("invalid", ["../outside", "/absolute", "src/**", "missing"])
def test_invalid_cache_inputs_cannot_produce_reusable_identity(tmp_path: Path, invalid: str) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    with pytest.raises(ValueError):
        fingerprint(tmp_path, [invalid], "context")
