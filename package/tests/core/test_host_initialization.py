"""Configured application hosts load only when a proof needs the host."""

import pytest

pytest_plugins = ["pytester"]


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
