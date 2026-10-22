import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_docs import missing_links
from scripts.ci.check_metadata import check_metadata


class DocumentChecks(unittest.TestCase):
    def test_links_validate_real_files_but_not_example_code_or_remote_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("# Guide")
            readme = root / "README.md"
            readme.write_text(
                "[Guide](guide.md#anchor)\n[Web](https://example.org)\n```md\n[Example](consumer.md)\n```\n"
            )
            self.assertEqual(missing_links(readme), [])
            (root / "guide.md").unlink()
            self.assertEqual(len(missing_links(readme)), 1)

    def test_distribution_description_must_match_current_readme(self):
        raw = b"Name: pytest-obligation\nDescription-Content-Type: text/markdown\n\n# Current README\n"
        check_metadata(raw, "# Current README\n")
        with self.assertRaisesRegex(AssertionError, "differs"):
            check_metadata(raw, "# Stale README\n")
