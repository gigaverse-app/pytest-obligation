"""Generate pinned Quint traces and replay them against current-checkout production APIs."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
VERSION = "0.33.1"


class ReplayMismatch(AssertionError):
    """The implementation observation differs from a generated model state."""


def decode(value: Any) -> Any:
    """Decode the ITF data types used by the maintained contracts."""
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        if "#bigint" in value:
            return int(value["#bigint"])
        if "#set" in value:
            return sorted((decode(item) for item in value["#set"]), key=lambda item: json.dumps(item, sort_keys=True))
        if "#tup" in value:
            return decode(value["#tup"])
        if "#map" in value:
            return {str(decode(key)): decode(item) for key, item in value["#map"]}
        if any(key.startswith("#") and key != "#meta" for key in value):
            raise ValueError(f"unsupported ITF value: {value}")
        return {key: decode(item) for key, item in value.items() if key != "#meta"}
    return value


def canonical(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted((canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def command(arguments: list[str], log: Path, *, cwd: Path = ROOT, timeout: float | None = 180) -> None:
    """Run one step with merged output logged; a failure carries the output for CI logs."""
    result = subprocess.run(
        arguments, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log}: {' '.join(arguments)}\n{result.stdout}")


def production_modules() -> dict[str, str]:
    modules = {}
    source = (ROOT / "package/src").resolve()
    for name, module in tuple(sys.modules.items()):
        if name == "pytest_obligation" or name.startswith("pytest_obligation."):
            path = getattr(module, "__file__", None)
            if path is None or not Path(path).resolve().is_relative_to(source):
                raise RuntimeError(f"production import escaped current checkout: {name}: {path}")
            modules[name] = str(Path(path).resolve().relative_to(ROOT))
    if not modules:
        raise RuntimeError("adapter imported no production pytest_obligation module")
    return modules


def load_adapter(path: Path) -> Any:
    name = "quint_adapter_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load adapter {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fingerprints(topic: Path, manifest: dict[str, Any]) -> dict[str, str]:
    paths = [
        topic / "manifest.json",
        topic / manifest["model"],
        topic / manifest["adapter"],
        topic / manifest["historical"],
        TOOL / "replay.py",
        TOOL / "package.json",
        TOOL / "package-lock.json",
    ]
    paths.extend(ROOT / path for path in manifest["sources"])
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def replay(path: Path, manifest: dict[str, Any], module: Any, mutant: str | None = None) -> set[str]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    states = trace.get("states", [])
    if len(states) < 2:
        raise ValueError(f"missing or empty generated trace: {path}")
    covered = set()
    with tempfile.TemporaryDirectory(prefix="quint-replay-") as directory:
        adapter = module.create(ROOT, Path(directory), mutant)
        try:
            for index, raw in enumerate(states):
                state = decode(raw)
                event, expected = state["event"], state["observed"]
                op = event["op"]
                if op not in manifest["actions"]:
                    raise ValueError(f"undeclared action {op!r} in {path}")
                adapter.apply(event)
                actual = canonical(adapter.observe())
                production_modules()
                covered.add(op)
                if actual != expected:
                    raise ReplayMismatch(
                        json.dumps(
                            {
                                "trace": str(path),
                                "state": index,
                                "event": event,
                                "expected": expected,
                                "actual": actual,
                                "mutant": mutant,
                            },
                            sort_keys=True,
                        )
                    )
        finally:
            adapter.close()
    return covered


def generate(topic: Path, manifest: dict[str, Any], output: Path, quint: Path) -> list[Path]:
    model = topic / manifest["model"]
    command([str(quint), "typecheck", str(model)], output / "typecheck.log")
    bounds = manifest["bounds"]
    common = ["--main", manifest["module"], "--backend", "typescript", "--seed", str(bounds["seed"])]
    for witness in manifest["witnesses"]:
        prefix = output / ("witness-" + witness)
        command(
            [
                str(quint),
                "test",
                str(model),
                *common,
                "--match",
                "^" + witness + "$",
                "--max-samples",
                "1",
                "--out-itf",
                str(prefix) + "-{seq}.itf.json",
            ],
            output / (witness + ".log"),
        )
        if not list(output.glob(prefix.name + "-*.itf.json")):
            raise RuntimeError(f"Quint generated no trace for required witness {witness}")
    command(
        [
            str(quint),
            "run",
            str(model),
            *common,
            "--invariant",
            manifest["invariant"],
            "--max-samples",
            str(bounds["max_samples"]),
            "--max-steps",
            str(bounds["max_steps"]),
            "--n-traces",
            str(bounds["n_traces"]),
            "--out-itf",
            str(output / "sample-{seq}.itf.json"),
        ],
        output / "simulation.log",
    )
    if len(list(output.glob("sample-*.itf.json"))) != bounds["n_traces"]:
        raise RuntimeError("Quint did not emit the required number of sampled traces")
    return sorted(output.glob("*.itf.json"))


def run_topic(topic: Path, output: Path, quint: Path | None, trace: Path | None) -> dict[str, Any]:
    manifest = json.loads((topic / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != 1 or not manifest["actions"] or not manifest["witnesses"] or not manifest["mutants"]:
        raise ValueError(f"incomplete maintained manifest: {topic}")
    for source in manifest["sources"]:
        if not (ROOT / source).is_file():
            raise ValueError(f"manifest source missing: {source}")
    historical = topic / manifest["historical"]
    if hashlib.sha256(historical.read_bytes()).hexdigest() != manifest["historical_sha256"]:
        raise ValueError(f"historical audit model changed: {historical}")
    module = load_adapter(topic / manifest["adapter"])
    traces = [trace] if trace else generate(topic, manifest, output, quint)  # type: ignore[arg-type]
    covered = set()
    for path in traces:
        covered.update(replay(path, manifest, module))
    if not trace and covered != set(manifest["actions"]):
        raise RuntimeError(f"unreached actions: {set(manifest['actions']) - covered}")
    detected = {}
    if not trace:
        for mutant in manifest["mutants"]:
            for path in traces:
                try:
                    replay(path, manifest, module, mutant)
                except ReplayMismatch as error:
                    detected[mutant] = json.loads(str(error))
                    break
            else:
                raise RuntimeError(f"semantic mutation survived all generated traces: {mutant}")
    return {
        "topic": topic.name,
        "traces": len(traces),
        "actions": sorted(covered),
        "mutations": detected,
        "bounds": manifest["bounds"],
        "production_modules": production_modules(),
        "sha256": fingerprints(topic, manifest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", action="append")
    parser.add_argument("--quint", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/quint")
    parser.add_argument("--replay", type=Path, help="replay one saved ITF trace; requires exactly one --topic")
    args = parser.parse_args()
    if args.replay and (not args.topic or len(args.topic) != 1):
        parser.error("--replay requires exactly one topic")
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "package/src"))
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result: dict[str, Any] = {
        "mode": "replay-only" if args.replay else "generate-and-replay",
        "expected_quint": VERSION,
        "quint": None,
        "status": "running",
        "source_trace": str(args.replay.resolve()) if args.replay else None,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "topics": [],
    }
    result_path = args.output / "results.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        topics = sorted((ROOT / "docs/quint").glob("*/manifest.json"))
        if args.topic:
            topics = [path for path in topics if path.parent.name in args.topic]
            if {path.parent.name for path in topics} != set(args.topic):
                raise ValueError("requested maintained topic is missing")
        if not topics:
            raise ValueError("no maintained Quint manifests discovered")
        result["source_hashes"] = {
            path.parent.name: fingerprints(path.parent, json.loads(path.read_text(encoding="utf-8"))) for path in topics
        }
        quint = args.quint or TOOL / "node_modules/.bin/quint"
        if not args.replay:
            if not quint.is_file() and not args.quint:
                command(["npm", "ci", "--prefix", str(TOOL), "--ignore-scripts"], args.output / "npm.log")
            version = subprocess.check_output([str(quint), "--version"], text=True).strip()
            if version != VERSION:
                raise RuntimeError(f"Quint version mismatch: expected {VERSION}, got {version}")
            result["quint"] = version
        for path in topics:
            output = args.output / path.parent.name
            if output.exists() and not args.replay:
                # Stale traces must never satisfy a missing-generation check.
                import shutil

                shutil.rmtree(output)
            output.mkdir(parents=True, exist_ok=True)
            result["topics"].append(run_topic(path.parent, output, quint, args.replay))
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["failure"] = {"type": type(error).__name__, "detail": str(error)}
        if isinstance(error, ReplayMismatch):
            result["failure"]["mismatch"] = json.loads(str(error))
        try:
            result["production_modules"] = production_modules()
        except RuntimeError as import_error:
            result["import_attestation_error"] = str(import_error)
        raise
    finally:
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"head": result["head"], "topics": [(t["topic"], t["traces"]) for t in result["topics"]]}))


if __name__ == "__main__":
    main()
