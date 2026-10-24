"""Join actual collected nodeids to existing pytest JUnit outcomes."""

from pathlib import Path

from _pytest.junitxml import mangle_test_address

from .inventory import ApplicationInventory


def skipped_tests(inventory: ApplicationInventory, paths: list[Path]) -> int | None:
    from defusedxml.ElementTree import parse

    if any(app.nodeids is None for app in inventory.applications.values()):
        return None
    observed: dict[tuple[str, str], bool] = {}
    for path in paths:
        for case in parse(path).iter("testcase"):
            identity = (case.get("classname", ""), case.get("name", ""))
            # A completed attempt must not turn back into a skip on a repeated
            # report; failures/errors were attempted too, and remain failures.
            skip = case.find("skipped")
            attempted = (
                skip is None
                or skip.get("type") == "pytest.xfail"
                or case.find("failure") is not None
                or case.find("error") is not None
            )
            observed[identity] = observed.get(identity, False) or attempted
    expected: set[tuple[str, str]] = set()
    for app in inventory.applications.values():
        for nodeid in app.nodeids or []:
            address = mangle_test_address(nodeid)
            expected.add((".".join(address[:-1]), address[-1]))
    return sum(not observed.get(identity, False) for identity in expected)
