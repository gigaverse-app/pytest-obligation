"""Required adopter families cannot disappear, be filtered, or turn into unconditional skips."""

from pathlib import Path

import pytest

from scripts.check_adoption_cases import check_cases


@pytest.mark.parametrize("result", ["passed", "xfail", "missing", "filtered", "skipped", "failed", "error"])
def test_required_adopter_cases(tmp_path: Path, result: str) -> None:
    path = tmp_path / "junit.xml"
    status = {
        "passed": "",
        "xfail": '<skipped type="pytest.xfail"/>',
        "skipped": '<skipped type="pytest.skip"/>',
        "failed": "<failure/>",
        "error": "<error/>",
    }.get(result, "")
    cases = (
        ""
        if result == "missing"
        else (f'<testcase classname="TestWorker" name="proof[edge-blank]">{status}</testcase>')
    )
    if result == "filtered":
        cases = '<testcase classname="TestWorker" name="unrelated"/>'
    path.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    if result in ("passed", "xfail"):
        check_cases(path, ["*TestWorker*proof*"])
    else:
        with pytest.raises(AssertionError):
            check_cases(path, ["*TestWorker*proof*"])


@pytest.mark.parametrize("missing", [None, "assert_first_execution_has_visible_effect", "assert_replay_converges"])
def test_replay_evidence_requires_each_canonical_proof(tmp_path: Path, missing: str | None) -> None:
    from pytest_obligation.profiles.harmless_replay import REPLAY_SAFETY_PROOFS
    from scripts.check_adoption_cases import check_replays

    cases = "".join(
        f'<testcase classname="Demo" name="REPLAY_SAFE_EXECUTION-image-{proof.__name__}"/>'
        for proof in REPLAY_SAFETY_PROOFS
        if proof.__name__ != missing
    )
    report = tmp_path / "replays.xml"
    report.write_text(f"<testsuite>{cases}</testsuite>")
    if missing:
        with pytest.raises(AssertionError, match="no executed adopter cases"):
            check_replays(report, ["Demo*REPLAY_SAFE_EXECUTION-image"])
    else:
        check_replays(report, ["Demo*REPLAY_SAFE_EXECUTION-image"])
