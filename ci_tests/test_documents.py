import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_docs import missing_links


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
