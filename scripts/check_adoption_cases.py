"""Require executed adopter cases, including selection suites and extras outside A–J reports."""

import argparse
import xml.etree.ElementTree as ET
from fnmatch import fnmatchcase
from pathlib import Path

from pytest_obligation.profiles.harmless_replay import REPLAY_SAFETY_PROOFS


def check_cases(path: Path, required: list[str]) -> None:
    cases = list(ET.parse(path).iter("testcase"))
    for pattern in required:
        matching = [case for case in cases if fnmatchcase(f"{case.get('classname')}::{case.get('name')}", pattern)]
        assert matching, f"{pattern}: no executed adopter cases"
        for case in matching:
            identity = f"{case.get('classname')}::{case.get('name')}"
            assert case.find("failure") is None and case.find("error") is None, f"{identity}: failed execution"
            for skipped in case.findall("skipped"):
                assert skipped.get("type") == "pytest.xfail", f"{identity}: skipped rather than exercised"


def check_replays(path: Path, prefixes: list[str]) -> None:
    """Require every canonical replay proof for each independent named effect."""
    check_cases(path, [f"{prefix}-{proof.__name__}*" for prefix in prefixes for proof in REPLAY_SAFETY_PROOFS])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--case", action="append", default=[], help="glob against classname::test name")
    parser.add_argument("--replay", action="append", default=[], help="glob prefix before a replay proof name")
    arguments = parser.parse_args()
    if not arguments.case and not arguments.replay:
        parser.error("declare --case or --replay evidence")
    check_cases(arguments.report, arguments.case)
    check_replays(arguments.report, arguments.replay)
    print(f"Validated {len(arguments.case)} case patterns and {len(arguments.replay)} complete replay bindings")


if __name__ == "__main__":
    main()
