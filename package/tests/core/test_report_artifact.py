"""A trusted publisher re-renders the staged artifact from data alone, and reaches the same report."""

import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pytest_obligation.profiles.coverage import (
    Assessment,
    CaseEvidence,
    ProfileCoverage,
    SourceLocation,
    SuiteCoverage,
)
from pytest_obligation.reporting import __main__ as report_cli
from pytest_obligation.reporting import republish
from pytest_obligation.reporting.artifact import MANIFEST, MARKDOWN, REPORTS, RenderManifest, load, stage
from pytest_obligation.reporting.inventory import Application, ApplicationInventory

HEAD = "a" * 40
MERGE = "b" * 40
PASSED = {"setup": ["passed"], "call": ["passed"], "teardown": ["passed"]}


def _suite(name: str, outcomes: dict[str, list[str]]) -> SuiteCoverage:
    case = CaseEvidence(family="derive", collected=True, selected=True, outcomes=outcomes)
    return SuiteCoverage(
        name=name,
        source=SourceLocation(path="tests/test_orders.py", line=3),
        profiles={
            "F": ProfileCoverage(title="discovery", assessment=Assessment(state="claimed"), cases={"derive": case})
        },
    )


def _evidence(root: Path) -> None:
    adapter = TypeAdapter(dict[str, SuiteCoverage])
    (root / "shard-1.json").write_bytes(adapter.dump_json({"tests.test_orders.TestOrders": _suite("Orders", PASSED)}))
    failed = {"setup": ["passed"], "call": ["failed"], "teardown": ["passed"]}
    (root / "shard-2.json").write_bytes(
        adapter.dump_json({"tests.test_refunds.TestRefunds": _suite("Refunds", failed)})
    )
    inventory = ApplicationInventory(
        revision=MERGE,
        applications={
            f"tests.test_{name.lower()}.Test{name}": Application(
                name=name,
                source=SourceLocation(path=f"tests/test_{name.lower()}.py", line=3),
                nodeids=[f"tests/test_{name.lower()}.py::Test{name}::test_contract[{case}]" for case in "ab"],
            )
            for name in ("Orders", "Refunds", "Invoices")
        },
    )
    (root / "inventory.json").write_text(inventory.model_dump_json())
    for shard, name in enumerate(("orders", "refunds"), start=1):
        cases = "".join(
            f'<testcase classname="tests.test_{name}.Test{name.title()}" name="test_contract[{case}]"/>'
            for case in "ab"
        )
        (root / f"junit-{shard}.xml").write_text(
            f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>'
        )


def _report(root: Path, *extra: str) -> str:
    report_cli.main(
        [
            "--input",
            str(root / "shard-*.json"),
            "--output",
            str(root / "original" / "report.md"),
            "--source",
            f"PR head {HEAD} · workflow commit {MERGE} · run 7 · attempt 2",
            "--run-url",
            "https://github.com/owner/app/actions/runs/7/attempts/2",
            "--repository-url",
            "https://github.com/owner/app",
            "--asset-ref",
            "v1",
            "--revision",
            MERGE,
            "--stage-artifact",
            str(root / "artifact"),
            *extra,
        ]
    )
    return (root / "original" / "report.md").read_text(encoding="utf-8")


def _republish(artifact: Path, output: Path) -> str:
    republish.main(
        [
            "--artifact",
            str(artifact),
            "--output",
            str(output),
            "--head-sha",
            HEAD,
            "--run-id",
            "7",
            "--run-attempt",
            "2",
            "--run-url",
            "https://github.com/owner/app/actions/runs/7/attempts/2",
            "--repository-url",
            "https://github.com/owner/app",
            "--asset-ref",
            "v1",
        ]
    )
    return output.read_text(encoding="utf-8")


SCENARIOS = {
    "complete": ["--expected-reports", "2", "--test-outcome", "failure", "--graphics"],
    "collected and joined to JUnit": [
        "--expected-reports",
        "2",
        "--test-outcome",
        "success",
        "--inventory",
        "{root}/inventory.json",
        "--collection-revision",
        MERGE,
        "--junit-input",
        "{root}/junit-*.xml",
        "--graphics",
    ],
    "missing shard": ["--expected-reports", "3", "--test-outcome", "success"],
    "stale inventory": ["--inventory", "{root}/inventory.json", "--collection-revision", HEAD],
    "JUnit requested but absent": [
        "--inventory",
        "{root}/inventory.json",
        "--collection-revision",
        MERGE,
        "--junit-input",
        "{root}/absent-*.xml",
        "--test-outcome",
        "success",
    ],
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_republished_report_is_the_report_the_run_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    _evidence(tmp_path)
    original = _report(tmp_path, *(value.format(root=tmp_path) for value in SCENARIOS[scenario]))
    # Evidence stays identical; only identity changes to facts the publisher can verify itself.
    expected = original.replace(f" · workflow commit {MERGE}", "").replace(f"/blob/{MERGE}/", f"/blob/{HEAD}/")
    assert _republish(tmp_path / "artifact", tmp_path / "republished.md") == expected
    if scenario == "collected and joined to JUnit":
        assert 'alt="2 skipped tests"' in original


def test_republish_never_reads_the_markdown_the_pull_request_uploaded(tmp_path: Path) -> None:
    _evidence(tmp_path)
    original = _report(tmp_path, "--expected-reports", "2")
    (tmp_path / "artifact" / MARKDOWN).write_text("[approve](https://evil.example) @everyone <img src=x>")
    body = _republish(tmp_path / "artifact", tmp_path / "republished.md")
    assert body == original.replace(f" · workflow commit {MERGE}", "").replace(f"/blob/{MERGE}/", f"/blob/{HEAD}/")
    assert "evil.example" not in body


@pytest.mark.parametrize(
    "manifest",
    [
        None,
        "{broken",
        '{"version": 2, "expected_reports": 0, "test_outcome": "success", "graphics": false}',
        '{"expected_reports": 0, "test_outcome": "passed", "graphics": false}',
        '{"expected_reports": 0, "test_outcome": "success", "graphics": false, "revision": "main](https://x)"}',
    ],
)
def test_untrusted_manifest_is_rejected_and_never_turns_green(tmp_path: Path, manifest: str | None) -> None:
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success")
    path = tmp_path / "artifact" / MANIFEST
    if manifest is None:
        path.unlink()
    else:
        path.write_text(manifest)
    body = _republish(tmp_path / "artifact", tmp_path / "republished.md")
    assert "Evidence unavailable" in body
    assert "no valid render manifest" in body
    assert "@everyone" not in body and "https://x" not in body


def test_a_field_this_version_does_not_know_is_dropped_and_never_rendered(tmp_path: Path) -> None:
    """A newer report step's manifest still renders here; its unknown field never reaches the report."""
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success")
    path = tmp_path / "artifact" / MANIFEST
    manifest = json.loads(path.read_text())
    path.write_text(json.dumps({**manifest, "comment": "@everyone", "added_in_a_later_version": True}))
    body = _republish(tmp_path / "artifact", tmp_path / "republished.md")
    assert "no valid render manifest" not in body
    assert "@everyone" not in body
    assert "Orders" in body and "Refunds" in body


@pytest.mark.parametrize("title", ["", "Celery main"])
def test_a_later_optional_field_is_written_only_when_set(tmp_path: Path, title: str) -> None:
    """Older publishers refuse unknown fields; a manifest without a title reads exactly as it did before titles."""
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success", "--title", title)
    written = json.loads((tmp_path / "artifact" / MANIFEST).read_text())
    assert ("title" in written) == bool(title)
    assert set(written) - {"title"} == {
        "version",
        "expected_reports",
        "test_outcome",
        "graphics",
        "revision",
        "junit",
        "inventory_unavailable",
    }


def test_an_unreadable_manifest_keeps_the_report_graphics(tmp_path: Path) -> None:
    """How the report looks is not evidence: the unavailable report still uses the glyphs."""
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success", "--graphics")
    (tmp_path / "artifact" / MANIFEST).unlink()
    body = _republish(tmp_path / "artifact", tmp_path / "republished.md")
    assert "no valid render manifest" in body
    assert "report-glyphs/" in body


def test_staged_evidence_is_read_from_fixed_names_only(tmp_path: Path) -> None:
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success")
    artifact = tmp_path / "artifact"
    # Files the layout does not name are ignored, wherever the uploader put them.
    (artifact / "planted.json").write_text("{}")
    (artifact / REPORTS / "notes.txt").write_text("{}")
    staged = load(artifact)
    assert [path.name for path in staged.reports] == ["0001.json", "0002.json"]
    assert staged.manifest == RenderManifest(expected_reports=2, test_outcome="success", graphics=False, revision=MERGE)


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs a privilege on Windows")
def test_symlinked_evidence_is_not_followed(tmp_path: Path) -> None:
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success")
    artifact = tmp_path / "artifact"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({}))
    (artifact / REPORTS / "0002.json").unlink()
    (artifact / REPORTS / "0002.json").symlink_to(outside)
    assert [path.name for path in load(artifact).reports] == ["0001.json"]


def test_staging_refuses_a_directory_with_other_content(tmp_path: Path) -> None:
    (tmp_path / "leftover.json").write_text("{}")
    manifest = RenderManifest(expected_reports=0, test_outcome="skipped", graphics=False)
    with pytest.raises(ValueError, match="not empty"):
        stage(tmp_path, manifest, reports=[], junit=[], inventory=None, markdown="")


@pytest.mark.parametrize("option,value", [("--head-sha", "main"), ("--run-id", "0"), ("--run-attempt", "1; rm -rf /")])
def test_publisher_identity_arguments_are_strict(tmp_path: Path, option: str, value: str) -> None:
    arguments = {"--head-sha": HEAD, "--run-id": "7", "--run-attempt": "1", option: value}
    with pytest.raises(SystemExit):
        republish.main(
            ["--artifact", str(tmp_path), "--output", str(tmp_path / "out.md")]
            + [item for pair in arguments.items() for item in pair]
        )


def _archive(root: Path, extra: tuple[str | zipfile.ZipInfo, bytes] | None = None) -> Path:
    """Use the real producer before changing one part of its transport envelope."""
    _evidence(root)
    _report(root, "--expected-reports", "2", "--test-outcome", "failure")
    archive = root / "evidence.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in (root / "artifact").rglob("*"):
            if path.is_file():
                output.write(path, path.relative_to(root / "artifact").as_posix())
        if extra:
            output.writestr(*extra)
    return archive


def test_archive_preserves_the_producers_evidence(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    assert _republish(archive, tmp_path / "from-zip.md") == _republish(
        tmp_path / "artifact", tmp_path / "from-directory.md"
    )


@pytest.mark.parametrize(
    "name", ["../outside.json", "/outside.json", "reports/../outside.json", "reports\\outside.json"]
)
def test_unsafe_archive_paths_produce_an_unavailable_report(tmp_path: Path, name: str) -> None:
    archive = _archive(tmp_path, (name, b"{}"))
    body = _republish(archive, tmp_path / "out.md")
    assert "Evidence unavailable" in body
    assert not (tmp_path / "outside.json").exists()


def test_archive_symlinks_are_rejected(tmp_path: Path) -> None:
    link = zipfile.ZipInfo("reports/link.json")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    body = _republish(_archive(tmp_path, (link, b"/etc/passwd")), tmp_path / "out.md")
    assert "Evidence unavailable" in body


def test_duplicate_archive_entries_are_rejected(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="Duplicate name"):
        archive = _archive(tmp_path, (MANIFEST, b"{}"))
    assert "Evidence unavailable" in _republish(archive, tmp_path / "out.md")


@pytest.mark.parametrize("budget", ["MAX_MEMBERS", "MAX_EXPANDED_BYTES", "MAX_REPORT_BYTES", "MAX_JUNIT_BYTES"])
def test_archive_budgets_are_enforced_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    from pytest_obligation.reporting import artifact

    archive = _archive(tmp_path, ("junit/0001.xml", b"<testsuites/>"))
    monkeypatch.setattr(artifact, budget, 1)
    assert "Evidence unavailable" in _republish(archive, tmp_path / "out.md")


def test_a_producer_cannot_claim_github_identity(tmp_path: Path) -> None:
    _evidence(tmp_path)
    _report(tmp_path, "--expected-reports", "2", "--test-outcome", "success")
    manifest = tmp_path / "artifact" / MANIFEST
    settings = json.loads(manifest.read_text())
    settings["revision"] = "d" * 40
    manifest.write_text(json.dumps(settings))
    body = _republish(tmp_path / "artifact", tmp_path / "out.md")
    assert "Test step (GitHub)" not in body
    assert "Test step (reported): **success**" in body
    assert "workflow commit " + "d" * 40 not in body
    assert "/blob/" + "d" * 40 not in body
    assert "/blob/" + HEAD in body
