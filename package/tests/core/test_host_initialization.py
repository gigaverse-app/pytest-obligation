"""Configured application hosts load only when a proof needs the host."""

import pytest


@pytest.mark.parametrize("resolve", [False, True], ids=["unused", "resolved"])
@pytest.mark.parametrize("previous", ["host", "factory"], ids=["manual-host", "manual-factory"])
@pytest.mark.parametrize("collection_error", [False, True], ids=["success", "collection-error"])
def test_independent_sessions_restore_the_previous_manual_host(
    pytester: pytest.Pytester, resolve: bool, previous: str, collection_error: bool
) -> None:
    pytester.makepyfile(
        application="""
from pytest_obligation.host import Host
host = Host(production_packages={"application"})
""",
        test_first="def test_first(): pass\n"
        if not resolve
        else """
from pytest_obligation.host import current_host
def test_first():
    assert current_host().production_packages == {"application"}
""",
    )
    if collection_error:
        test = pytester.path / "test_first.py"
        test.write_text(
            test.read_text(encoding="utf-8") + "\nraise RuntimeError('collection failed')\n", encoding="utf-8"
        )
    first = pytester.makeini("[pytest]\npythonpath = .\ndue_work_harness_host = application:host\n")
    second = pytester.path / "second.ini"
    second.write_text("[pytest]\n", encoding="utf-8")
    script = pytester.makepyfile(
        runner=f"""
import pytest
from pytest_obligation.host import Host, configure, current_host
manual = Host(production_packages={{"manual"}})
calls = []
def factory():
    calls.append(True)
    return manual
configure({"factory" if previous == "factory" else "manual"})
assert pytest.main(["-q", "-c", {str(first)!r}, "test_first.py"]) == {2 if collection_error else 0}
assert calls == [], "restoration must not eagerly resolve the previous factory"
assert pytest.main(["-q", "-c", {str(second)!r}, "test_second.py"]) == 0
assert current_host() is manual
"""
    )
    pytester.makepyfile(
        test_second="""
from pytest_obligation.host import current_host
def test_second():
    assert current_host().production_packages == {"manual"}
"""
    )
    assert pytester.runpython(script).ret == 0


def test_unrelated_tests_do_not_import_the_configured_application(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\ndue_work_harness_host = unavailable_application.testing:host\n")
    pytester.makepyfile("def test_plain():\n    assert 2 + 2 == 4\n")
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1)


@pytest.mark.parametrize("attribute", ["make_host", "host"])
def test_host_resolves_once_before_a_contract_reads_it(pytester: pytest.Pytester, attribute: str) -> None:
    pytester.makeini(f"[pytest]\npythonpath = .\ndue_work_harness_host = application:{attribute}\n")
    pytester.makepyfile(
        application="""
from pytest_obligation.host import Host
host = Host(production_packages={"application"})
calls = 0

def make_host():
    global calls
    calls += 1
    return host
"""
    )
    pytester.makepyfile(f"""
import sys
from pytest_obligation.host import current_host
assert "application" not in sys.modules
first = current_host()
assert first.production_packages == {{"application"}}

def test_cached_host():
    import application
    assert current_host() is first
    assert application.calls == {int(attribute == "make_host")}
""")
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=1)


def test_a_required_broken_host_still_fails(pytester: pytest.Pytester) -> None:
    pytester.makeini("[pytest]\ndue_work_harness_host = unavailable_application.testing:host\n")
    pytester.makepyfile("from pytest_obligation.host import current_host\nhost = current_host()\n")
    result = pytester.runpytest_subprocess("-q")
    assert result.ret != 0
    assert "ModuleNotFoundError" in result.stdout.str()
