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
