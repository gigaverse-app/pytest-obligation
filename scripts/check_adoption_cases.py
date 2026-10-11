"""Require executed adopter cases, including selection suites and extras outside A–J reports."""

import argparse
import xml.etree.ElementTree as ET
from fnmatch import fnmatchcase
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--case", action="append", required=True, help="glob against classname::test name")
    arguments = parser.parse_args()
    check_cases(arguments.report, arguments.case)
    print(f"Validated executed adoption for {len(arguments.case)} required case patterns")


if __name__ == "__main__":
    main()
