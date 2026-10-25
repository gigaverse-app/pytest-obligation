"""Fingerprint declared collection inputs without installing or importing the application."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def fingerprint(root: Path, inputs: list[str], context: str) -> str:
    for value in inputs:
        path = Path(value)
        # anchor, not is_absolute(): on Windows a rooted path without a drive is not absolute.
        if path.anchor or ".." in path.parts or any(char in value for char in "*?[]:"):
            raise ValueError("Cache inputs must be literal repository-relative paths")
    files = subprocess.check_output(["git", "ls-files", "-z", "--", *inputs], cwd=root).decode().split("\0")
    names = sorted(set(filter(None, files)))
    if not names:
        raise ValueError("No tracked collection inputs found")
    digest = hashlib.sha256(
        json.dumps(["inventory-v1", sorted(inputs), context, platform.system(), platform.machine()]).encode()
    )
    # Version the cache by the actual reporter implementation, including the
    # portable nodeid plugin. A floating action tag is not an implementation ID.
    sources = [("reporter/" + path.name, path) for path in sorted(Path(__file__).parent.glob("*.py"))]
    sources += [("repository/" + name, root / name) for name in names]
    for name, path in sources:
        digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return "obligation-inventory-v1-" + digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", default="")
    parser.add_argument("--context", default="")
    args = parser.parse_args()
    inputs = [line.strip() for line in args.inputs.splitlines() if line.strip()]
    key = ""
    if inputs:
        try:
            key = fingerprint(Path.cwd(), inputs, args.context)
        except (OSError, ValueError, subprocess.CalledProcessError):
            print("::warning::Inventory cache identity unavailable; using fresh collection.")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(f"key={key}\n")
    print(key or "Inventory caching disabled")


if __name__ == "__main__":
    main()
