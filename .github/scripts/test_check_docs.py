#!/usr/bin/env python3
"""Regression tests for repository-local documentation links."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_docs.py")
SPEC = importlib.util.spec_from_file_location("check_docs", SCRIPT)
assert SPEC and SPEC.loader
check_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_docs)


class CheckLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_root = check_docs.ROOT
        check_docs.ROOT = self.root
        (self.root / "docs").mkdir()
        self.page = self.root / "docs" / "page.md"

    def tearDown(self) -> None:
        check_docs.ROOT = self.original_root
        self.temp_dir.cleanup()

    def check(self, text: str) -> list[str]:
        self.page.write_text(text, encoding="utf-8")
        return check_docs.check_links(self.page, text)

    def test_accepts_existing_markdown_image(self) -> None:
        image = self.root / "assets" / "banner.jpg"
        image.parent.mkdir()
        image.touch()

        self.assertEqual(self.check("![Banner](../assets/banner.jpg)"), [])

    def test_rejects_missing_markdown_image(self) -> None:
        errors = self.check("![Banner](missing.jpg)")

        self.assertEqual(errors, [f"{Path('docs/page.md')}: broken relative link: missing.jpg"])

    def test_rejects_missing_html_source(self) -> None:
        errors = self.check('<img src="missing.jpg" alt="Banner">')

        self.assertEqual(errors, [f"{Path('docs/page.md')}: broken relative link: missing.jpg"])

    def test_accepts_external_html_source(self) -> None:
        self.assertEqual(self.check('<img src="https://example.com/banner.jpg">'), [])

    def test_ignores_html_inside_fenced_code(self) -> None:
        self.assertEqual(self.check('```html\n<img src="missing.jpg">\n```'), [])

    def test_accepts_site_root_and_dynamic_html_targets(self) -> None:
        text = '<a href="/app">App</a>\n<img src="${imageUrl}">'

        self.assertEqual(self.check(text), [])

    def test_rejects_html_target_escaping_repository(self) -> None:
        errors = self.check('<a href="../../private.md">Private</a>')

        self.assertEqual(errors, [f"{Path('docs/page.md')}: link escapes repository: ../../private.md"])


if __name__ == "__main__":
    unittest.main()
