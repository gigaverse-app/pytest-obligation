"""Opt-in fixture validation catches dormant adopter errors before setup, including xdist."""

from pathlib import Path

import pytest

from .test_due_work_verify import _run


@pytest.mark.parametrize("parallel", [False, True])
def test_skipped_missing_fixture_fails_collection_but_resolved_fixture_passes(tmp_path: Path, parallel: bool) -> None:
    if parallel:
        pytest.importorskip("xdist")
    source = """import pytest
@pytest.mark.skip(reason="external provider lane")
def test_provider(provider): pass
"""
    (tmp_path / "test_provider.py").write_text(source)
    arguments = ("-n", "2") if parallel else ()
    assert _run(tmp_path, *arguments).returncode == 0
    broken = _run(tmp_path, "--due-work-check-fixtures", *arguments)
    assert broken.returncode != 0
    assert "test_provider.py::test_provider: provider" in broken.stdout + broken.stderr
    (tmp_path / "conftest.py").write_text("import pytest\n@pytest.fixture\ndef provider(): return 1\n")
    repaired = _run(tmp_path, "--due-work-check-fixtures", *arguments)
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr


@pytest.mark.parametrize("indirect", [False, True])
def test_only_indirect_parameters_require_fixtures(tmp_path: Path, indirect: bool) -> None:
    (tmp_path / "test_parameters.py").write_text(f"""import pytest
@pytest.mark.skip(reason="external provider lane")
@pytest.mark.parametrize("provider", [1], indirect={indirect!r})
def test_provider(provider): pass
""")
    result = _run(tmp_path, "--due-work-check-fixtures")
    assert (result.returncode != 0) == indirect, result.stdout + result.stderr


def test_deselected_missing_fixture_does_not_fail_a_targeted_run(tmp_path: Path) -> None:
    (tmp_path / "test_parameters.py").write_text("def test_other(missing): pass\ndef test_selected(): pass\n")
    result = _run(tmp_path, "--due-work-check-fixtures", "-k", "selected")
    assert result.returncode == 0, result.stdout + result.stderr
