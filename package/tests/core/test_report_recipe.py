"""The documented separate-job wiring binds every consumer to one resolved commit."""
# gv:test-dependency: package/docs/github-action-report.md

import os
import subprocess
from pathlib import Path

import pytest
import yaml

DOC = Path(__file__).resolve().parents[2] / "docs/github-action-report.md"


def _recipe() -> dict:
    section = DOC.read_text().split("<!-- separate-report-jobs:start -->", 1)[1]
    return yaml.safe_load(section.split("```yaml", 1)[1].split("```", 1)[0])


@pytest.mark.parametrize("policy", ["head", "merge", "branch", "push"])
def test_split_jobs_keep_the_commit_resolved_before_a_branch_moves(tmp_path: Path, policy: str) -> None:
    jobs = _recipe()["jobs"]
    source = jobs["source"]
    checkout = next(step for step in source["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ inputs.ref || github.event.pull_request.head.sha || github.sha }}"
    assert source["outputs"]["revision"] == "${{ steps.commit.outputs.revision }}"
    resolve = next(step for step in source["steps"] if step.get("id") == "commit")

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("commit", "--allow-empty", "-qm", "head")
    head = git("rev-parse", "HEAD")
    git("branch", "chosen", head)
    git("commit", "--allow-empty", "-qm", "merge")
    merge = git("rev-parse", "HEAD")
    target = {"head": head, "merge": merge, "branch": "chosen", "push": merge}[policy]
    git("checkout", "--detach", target)
    output = tmp_path / "outputs"
    subprocess.run(
        ["bash", "-e", "-c", resolve["run"]], cwd=tmp_path, check=True, env={**os.environ, "GITHUB_OUTPUT": str(output)}
    )
    revision = output.read_text().strip().removeprefix("revision=")
    git("branch", "-f", "chosen", merge)
    assert revision == (head if policy in ("head", "branch") else merge)
    assert head != merge
    for name in ("tests", "inventory", "report"):
        job = jobs[name]
        assert "source" in job["needs"]
        checkout = next(step for step in job["steps"] if "actions/checkout@" in step.get("uses", ""))
        assert checkout["with"]["ref"] == "${{ needs.source.outputs.revision }}", name
    assert set(jobs["report"]["needs"]) == {"source", "tests", "inventory"}
    assert all("report" not in jobs[name]["needs"] for name in ("tests", "inventory"))
