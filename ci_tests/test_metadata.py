"""Package descriptions retain UTF-8 text and reject mismatched content."""

import unittest

from scripts.ci.check_metadata import check_metadata


class MetadataTests(unittest.TestCase):
    def test_description_preserves_unicode_and_rejects_changed_readme(self):
        for readme in ("# Plain README", "# Evidence\n\npassed · missing · 修复"):
            with self.subTest(readme=readme):
                raw = (
                    "Metadata-Version: 2.4\nName: pytest-obligation\n"
                    "Version: 1.0.0\nDescription-Content-Type: text/markdown\n\n" + readme
                ).encode("utf-8")
                check_metadata(raw, readme)
                with self.assertRaisesRegex(AssertionError, "description differs"):
                    check_metadata(raw, readme + "\nChanged content")
