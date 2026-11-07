"""Required source proof, exact runtime enrollment and fresh generated API replay."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".artifacts/source-contracts"


def run(arguments: list[str], name: str) -> None:
    result = subprocess.run(arguments, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUTPUT / f"{name}.log").write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{name} failed ({result.returncode}); see {OUTPUT / (name + '.log')}:\n{result.stdout}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate", action="store_true", help="prove and refresh generated artifacts after an intentional source edit"
    )
    parser.add_argument("--quint", type=Path, help="optional exact-version Quint executable")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result_path = OUTPUT / "results.json"
    result_path.write_text(json.dumps({"status": "running"}) + "\n")
    try:
        action = "generate" if args.generate else "check"
        run([sys.executable, "-m", "veripy", "project", action, "veripy-project.json", "--json"], "source-proof")
        # This independent fixed inventory cannot turn green by pytest selection,
        # deselection, skips, or removal of one parametrized rejection control.
        junit = OUTPUT / "runtime.xml"
        shutil.rmtree(OUTPUT / "backend", ignore_errors=True)
        junit.unlink(missing_ok=True)
        run(
            [sys.executable, "-m", "pytest", "verification_tests/source_contracts", "-q", f"--junitxml={junit}"],
            "runtime",
        )
        cases = list(ET.parse(junit).getroot().iter("testcase"))
        required = json.loads((ROOT / "scripts/source_contracts/required-tests.json").read_text())
        observed = sorted(case.attrib["name"] for case in cases)
        if not required or observed != required or any(list(case) for case in cases):
            raise RuntimeError(f"runtime enrollment/outcomes changed: expected {required}, observed {observed}")
        command = [sys.executable, "scripts/quint/replay.py", "--topic", "report-merge"]
        if args.quint:
            command += ["--quint", str(args.quint.resolve())]
        run(command, "generated-replay")
        manifest = json.loads((ROOT / "veripy-project.json").read_text())
        paths = {
            "veripy-project.json",
            "scripts/source_contracts/required-tests.json",
            "scripts/source_contracts/mutations.py",
            "scripts/source_contracts/check.py",
        }
        for target in manifest["targets"]:
            paths.update([target["source"], *target["dependencies"], target["sidecar"]])
        hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(paths)}
        result_path.write_text(
            json.dumps(
                {
                    "status": "verified",
                    "runtime_tests": observed,
                    "sha256": hashes,
                    "theorem": "conditional validation-rejection frame and structural identity/evidence effects",
                    "runtime": "independent real Pydantic histories; fresh Quint traces; source mutation controls",
                },
                indent=2,
            )
            + "\n"
        )
        print(f"Verified report-merge source, {len(cases)} API tests and fresh Quint replay; evidence {result_path}")
    except Exception as error:
        result_path.write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise


if __name__ == "__main__":
    main()
