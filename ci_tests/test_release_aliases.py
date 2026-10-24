"""Exercise the actual release step against a local Git remote."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ReleaseAliasTests(unittest.TestCase):
    def test_stable_actions_advance_without_rewinding_or_crossing_major_two(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
        script = workflow["jobs"]["move-major-tag"]["steps"][-1]["run"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            checkout = root / "checkout"
            subprocess.run(["git", "clone", str(remote), str(checkout)], check=True, capture_output=True)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()

            git("config", "user.name", "Release test")
            git("config", "user.email", "release@example.invalid")

            def release(tag):
                git("commit", "--allow-empty", "-m", f"chore: release {tag}")
                git("tag", tag)
                return git("rev-parse", "HEAD")

            def promote(tag):
                result = subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", script],
                    cwd=checkout,
                    env={**os.environ, "TAG": tag},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            def alias(name):
                return git("ls-remote", "origin", f"refs/tags/{name}").split()[0]

            first = release("v0.16.0")
            promote("v0.16.0")
            self.assertEqual(alias("v0"), first)
            self.assertEqual(alias("v1"), first)
            second = release("v0.16.1")
            promote("v0.16.1")
            self.assertEqual(alias("v1"), second)
            promote("v0.16.0")
            self.assertEqual(alias("v0"), second)
            self.assertEqual(alias("v1"), second)
            stable = release("v1.0.0")
            promote("v1.0.0")
            self.assertEqual(alias("v1"), stable)
            major_two = release("v2.0.0")
            promote("v2.0.0")
            self.assertEqual(alias("v2"), major_two)
            self.assertEqual(alias("v1"), stable)
