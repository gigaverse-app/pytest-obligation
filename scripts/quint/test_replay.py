"""Negative controls consume real generated ITF traces and the production adapters."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.quint import replay


class ReplayControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(replay.ROOT / "package/src"))
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        cls.topics = sorted((replay.ROOT / "docs/quint").glob("*/manifest.json"))
        if not cls.topics:
            raise RuntimeError("no maintained topics for negative controls")

    def generated(self, topic: Path) -> Path:
        traces = sorted((replay.ROOT / ".artifacts/quint" / topic.name).glob("*.itf.json"))
        self.assertTrue(traces, "run scripts/quint/replay.py first; controls require generated evidence")
        return traces[0]

    def test_changed_observation_in_real_generated_trace_is_rejected(self) -> None:
        for path in self.topics:
            with self.subTest(topic=path.parent.name), tempfile.TemporaryDirectory() as directory:
                manifest = json.loads(path.read_text())
                payload = json.loads(self.generated(path.parent).read_text())
                payload["states"][0]["observed"] = {"deliberately_wrong_observation": True}
                altered = Path(directory) / "altered.itf.json"
                altered.write_text(json.dumps(payload), encoding="utf-8")
                adapter = replay.load_adapter(path.parent / manifest["adapter"])
                with self.assertRaises(replay.ReplayMismatch):
                    replay.replay(altered, manifest, adapter)

    def test_empty_trace_is_a_failure(self) -> None:
        path = self.topics[0]
        manifest = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.itf.json"
            empty.write_text('{"states": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty generated trace"):
                replay.replay(empty, manifest, object())

    def test_missing_generation_cannot_pass_on_quint_exit_status_alone(self) -> None:
        path = self.topics[0]
        manifest = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(replay, "command"):
            with self.assertRaisesRegex(RuntimeError, "generated no trace"):
                replay.generate(path.parent, manifest, Path(directory), Path("quint"))

    def test_missing_tool_overwrites_stale_success_with_setup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = output / "results.json"
            result.write_text('{"status": "passed"}', encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(replay.TOOL / "replay.py"),
                    "--topic",
                    self.topics[0].parent.name,
                    "--quint",
                    str(output / "missing-quint"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(run.returncode, 0)
            evidence = json.loads(result.read_text())
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["failure"]["type"], "FileNotFoundError")
            self.assertIsNone(evidence["quint"])

    def test_mutation_setup_exception_does_not_count_as_detection(self) -> None:
        path = self.topics[0]
        manifest = json.loads(path.read_text())
        adapter = replay.load_adapter(path.parent / manifest["adapter"])
        create = adapter.create

        def fail_mutant(root, work, mutant=None):
            if mutant:
                raise RuntimeError("deliberate mutation setup failure")
            return create(root, work, mutant)

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(replay, "load_adapter", return_value=adapter),
                patch.object(replay, "generate", return_value=[self.generated(path.parent)]),
                patch.object(adapter, "create", side_effect=fail_mutant),
            ):
                # Supply a full real trace set to satisfy action coverage first.
                traces = sorted((replay.ROOT / ".artifacts/quint" / path.parent.name).glob("*.itf.json"))
                with patch.object(replay, "generate", return_value=traces):
                    with self.assertRaisesRegex(RuntimeError, "mutation setup failure"):
                        replay.run_topic(path.parent, Path(directory), Path("quint"), None)

    def test_historical_model_hash_is_required(self) -> None:
        path = self.topics[0]
        manifest = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as directory:
            topic = Path(directory)
            (topic / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (topic / manifest["historical"]).write_text("// edited historical evidence\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "historical audit model changed"):
                replay.run_topic(topic, topic, Path("quint"), None)


if __name__ == "__main__":
    unittest.main()
