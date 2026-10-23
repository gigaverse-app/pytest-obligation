"""Exercise this consumer's real configuration against real Git snapshots."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from pytest_selective.ci import LaneConfig, plan

ROOT = Path(__file__).resolve().parents[1]


class RoutingTests(unittest.TestCase):
    def test_nested_or_new_pytest_collection_policy_forces_every_lane(self):
        for path in ("package/pyproject.toml", "package/.pytest.ini"):
            with self.subTest(path=path):
                self.git("reset", "--hard", self.base)
                self.git("clean", "-fd")
                target = self.repo / path
                if target.exists():
                    target.write_text(
                        target.read_text().replace('testpaths = ["tests"]', 'testpaths = ["other_tests"]')
                    )
                else:
                    target.write_text("[pytest]\ntestpaths = other_tests\n")
                result = plan(self.repo, self.config, self.base, self.commit())
                self.assertTrue(all(result.lanes.values()), result.model_dump_json())
                self.assertIn("fallback", result.reason)

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.temporary.name)
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-xf", "-", "-C", str(cls.repo)], input=archive, check=True)
        # Read working configuration too, so the same tests reproduce the bug before committing its fix.
        config_text = (ROOT / ".github/test-lanes.json").read_text()
        (cls.repo / ".github/test-lanes.json").write_text(config_text)
        cls.config = LaneConfig.model_validate_json(config_text)
        cls.git("init", "-q")
        cls.git("config", "user.email", "ci@example.invalid")
        cls.git("config", "user.name", "CI routing test")
        cls.base = cls.commit()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(["git", *args], cwd=cls.repo, text=True).strip()

    @classmethod
    def commit(cls):
        cls.git("add", "-A")
        cls.git("commit", "-qm", "routing scenario")
        return cls.git("rev-parse", "HEAD")

    def selection(self, path, *, delete=False):
        self.git("reset", "--hard", self.base)
        file = self.repo / path
        if delete:
            file.unlink()
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("a") as output:
                output.write("\n# CI routing scenario\n")
        result = plan(self.repo, self.config, self.base, self.commit())
        self.assertNotIn("fallback", result.reason, result.model_dump_json())
        return {name for name, enabled in result.lanes.items() if enabled}

    def test_prose_does_not_start_runtime_lanes(self):
        for path in ("README.md", "package/README.md", "package/docs/adopting.md"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), set())

    def test_global_environment_changes_keep_full_validation(self):
        for path in ("uv.lock", ".github/workflows/ci.yml", ".github/test-lanes.json"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), set(self.config.lanes))

    def test_other_dependency_installers_keep_every_lane(self):
        for path in ("requirements.txt", "package/requirements-dev.txt", "poetry.lock", "pylock.toml"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), set(self.config.lanes))

    def test_demo_recording_inputs_keep_the_complete_demo_lane(self):
        for path in ("docs/demo.tape", "docs/demo_env.sh"):
            with self.subTest(path=path):
                self.assertEqual(self.selection(path), {"demos"})

    def test_framework_test_and_deletion_keep_its_lane(self):
        test_file = next((self.repo / "package/tests/mongodb").glob("test_*.py")).relative_to(self.repo).as_posix()
        self.assertIn("mongodb", self.selection(test_file))
        self.assertIn("mongodb", self.selection(test_file, delete=True))

    def test_package_code_keeps_external_due_conformance(self):
        self.assertIn("due", self.selection("package/src/pytest_obligation/host.py"))

    def test_evidence_validators_only_start_their_consuming_lanes(self):
        self.assertEqual(
            self.selection("scripts/check_adoption_report.py"),
            # The core guard tests also import this validator; the Python graph must keep them.
            {
                "core",
                "minimum_models",
                "exploration",
                "redis",
                "prefect",
                "demos",
                "saleor",
                "actions",
                "due",
                "typecheck",
            },
        )

    def test_published_actions_only_start_their_consumers(self):
        self.assertEqual(self.selection("check/action.yml"), {"demos", "saleor", "actions"})
        self.assertEqual(self.selection("test/action.yml"), {"actions"})

    def test_python_changes_still_typecheck(self):
        self.assertIn("typecheck", self.selection("package/src/pytest_obligation/host.py"))

    def test_missing_history_and_explicit_full_checkpoint_run_every_lane(self):
        for result in (
            plan(self.repo, self.config, "missing-history", self.base),
            plan(self.repo, self.config, self.base, self.base, full=True),
        ):
            self.assertTrue(all(result.lanes.values()), result.model_dump_json())


if __name__ == "__main__":
    unittest.main()
