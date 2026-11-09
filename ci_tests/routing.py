"""A real-Git snapshot of this repository, planned the way CI's `plan-work` step plans it.

Shared by the routing tests; not itself a test module, so no test imports another.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ci_esta.testing.lane_inference import resolve
from ci_esta.testing.work_plan import plan_work

ROOT = Path(__file__).resolve().parents[1]
LANE_FILE = ".github/test-lanes.json"
# Copied from the working tree, so the same tests reproduce a routing bug before its fix is committed.
WORKING_CONFIGURATION = (LANE_FILE, ".github/workflows/ci.yml")
# A probe line each edited file can hold without changing what it means to its own parser.
PROBES = {".json": "\n", ".md": "\nCI routing scenario\n", ".cjs": "\n// CI routing scenario\n"}


class RoutingSnapshot(unittest.TestCase):
    """Commits edits to a snapshot of HEAD and reads the lanes CI would run for them."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.temporary.name)
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-xf", "-", "-C", str(cls.repo)], input=archive, check=True)
        for path in WORKING_CONFIGURATION:
            shutil.copyfile(ROOT / path, cls.repo / path)
        cls.git("init", "-q")
        cls.git("config", "user.email", "ci@example.invalid")
        cls.git("config", "user.name", "CI routing test")
        cls.git("config", "core.autocrlf", "false")
        cls.base = cls.commit()
        cls.lanes = set(cls.resolved(cls.base, cls.base).config.lanes)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(["git", *args], cwd=cls.repo, text=True).strip()

    @classmethod
    def commit(cls):
        cls.git("add", "-A")
        cls.git("commit", "-qm", "routing scenario", "--allow-empty")
        return cls.git("rev-parse", "HEAD")

    @classmethod
    def resolved(cls, base, head):
        """The lanes plan-work plans with: the workflow's, extended by the committed lane file."""
        return resolve(cls.repo, base, head, cls.repo / LANE_FILE)

    def plan(self, base, head, full=False):
        resolved = self.resolved(base, head)
        return plan_work(self.repo, resolved.config, base, head, full=full, rules=resolved.rules)

    def reset(self):
        self.git("reset", "-q", "--hard", self.base)
        self.git("clean", "-qfd")

    def selection(self, *paths, delete=False):
        """Lanes selected by one commit that edits (or deletes) every path."""
        self.reset()
        for path in paths:
            file = self.repo / path
            if delete:
                file.unlink()
            else:
                file.parent.mkdir(parents=True, exist_ok=True)
                with file.open("a", encoding="utf-8", newline="\n") as output:
                    output.write(PROBES.get(file.suffix, "\n# CI routing scenario\n"))
        result = self.plan(self.base, self.commit())
        self.assertNotIn("fallback", result.reason, result.model_dump_json())
        return {name for name, enabled in result.lanes.items() if enabled}
