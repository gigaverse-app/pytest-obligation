"""Reuse current-revision nodeids; collect only application files still missing."""

import argparse
import glob
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .inventory import ApplicationInventory, discover


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-path", action="append", required=True)
    parser.add_argument("--input", default="", help="Current-run nodeid list or selector JSON glob")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--collection-key", default="", help="Content identity permitting cross-revision reuse")
    parser.add_argument("--pytest-command", default="", help="Empty plans only; otherwise collect missing files")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    inventory = discover(Path.cwd(), args.application_path).model_copy(
        update={"revision": args.revision, "collection_key": args.collection_key}
    )
    reused = False
    if args.output.exists():
        try:
            previous = ApplicationInventory.model_validate_json(args.output.read_bytes())
        except (OSError, ValueError):
            previous = None
        if previous is not None and (
            previous.collection_key == args.collection_key
            if args.collection_key
            else previous.revision == args.revision
        ):
            inventory = inventory.model_copy(
                update={
                    "applications": {
                        key: app.model_copy(update={"nodeids": previous.applications[key].nodeids})
                        if key in previous.applications
                        and previous.applications[key].name == app.name
                        and previous.applications[key].source == app.source
                        else app
                        for key, app in inventory.applications.items()
                    }
                }
            )
            reused = all(app.nodeids is not None for app in inventory.applications.values())
    nodeids: set[str] = set()
    for value in sorted(glob.glob(args.input, recursive=True)) if args.input else []:
        payload = json.loads(Path(value).read_bytes())
        if not isinstance(payload, (dict, list)) or not all(isinstance(key, str) for key in payload):
            raise ValueError("Collection input must be a nodeid list or mapping")
        nodeids.update(payload)
    if nodeids:
        reused = False  # Fresh current-run collection takes precedence over cached metadata.

    def apply_nodeids() -> None:
        for key, app in list(inventory.applications.items()):
            module = app.source.path.removesuffix(".py").replace("/", ".")
            class_name = key.removeprefix(module + ".").replace(".", "::")
            prefix = f"{app.source.path}::{class_name}::"
            found = sorted(nodeid for nodeid in nodeids if nodeid.startswith(prefix))
            if found:
                inventory.applications[key] = app.model_copy(update={"nodeids": found})

    apply_nodeids()
    missing = sorted({app.source.path for app in inventory.applications.values() if app.nodeids is None})
    if missing and args.pytest_command:
        with tempfile.TemporaryDirectory(prefix="obligation-collection-") as directory:
            output = Path(directory) / "nodeids.json"
            environment = {
                **os.environ,
                "OBLIGATION_COLLECTION_OUTPUT": str(output),
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")])
                ),
            }
            # --collect-only is unconditional. No fixtures or test bodies run.
            command = [
                *shlex.split(args.pytest_command),
                "--collect-only",
                "-q",
                "-p",
                "_nodeids_plugin",
                *missing,
            ]
            result = subprocess.run(command, env=environment, timeout=args.timeout, check=False)
            if result.returncode not in (0, 5) or not output.is_file():
                raise RuntimeError("Application collection failed; no complete inventory was recorded")
            nodeids.update(json.loads(output.read_bytes()))
            apply_nodeids()
    required = any(app.nodeids is None for app in inventory.applications.values())
    if any(app.nodeids is not None for app in inventory.applications.values()):
        inventory = inventory.model_copy(
            update={
                "limitations": [
                    "Application discovery uses static declarations; dynamic suites may be absent. "
                    "Test counts come from pytest collection, which does not establish passing evidence.",
                    *inventory.limitations[1:],
                ]
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(inventory.model_dump_json(indent=2))
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a") as stream:
            stream.write(
                f"required={str(required).lower()}\ninventory-path={args.output}\nreused={str(reused).lower()}\n"
            )
    print(
        f"Application inventory: {len(inventory.applications)} suites, "
        f"{sum(len(app.nodeids or []) for app in inventory.applications.values())} collected tests; "
        f"collection required: {required}; reused: {reused}"
    )


if __name__ == "__main__":
    main()
