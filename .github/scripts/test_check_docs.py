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


class CheckFrontMatterTests(unittest.TestCase):
    def valid_metadata(self) -> dict[str, str]:
        return {
            "title": "Example policy",
            "owner": "Documentation",
            "status": "approved",
            "classification": "public",
            "last-reviewed": "2026-08-27",
            "review-cycle": "90 days",
            "next-review": "2026-11-25",
        }

    def check(self, **changes: str) -> list[str]:
        metadata = self.valid_metadata()
        metadata.update(changes)
        return check_docs.check_front_matter(Path("docs/policy.md"), metadata)

    @property
    def rel(self) -> Path:
        return Path("docs/policy.md")

    def test_accepts_valid_metadata_and_supported_review_cycles(self) -> None:
        for cycle in ("30 days", "60 days", "90 days", "180 days"):
            with self.subTest(cycle=cycle):
                self.assertEqual(self.check(**{"review-cycle": cycle}), [])

    def test_rejects_blank_required_fields(self) -> None:
        for field in check_docs.REQUIRED_FRONT_MATTER:
            with self.subTest(field=field):
                errors = self.check(**{field: ""})
                self.assertIn(f"{self.rel}: front matter blank: {field}", errors)

    def test_rejects_missing_required_field(self) -> None:
        metadata = self.valid_metadata()
        del metadata["owner"]

        self.assertEqual(
            check_docs.check_front_matter(Path("docs/policy.md"), metadata),
            [f"{self.rel}: front matter missing: owner"],
        )

    def test_rejects_unsupported_review_cycle(self) -> None:
        self.assertEqual(
            self.check(**{"review-cycle": "365 days"}),
            [f"{self.rel}: invalid review-cycle: 365 days"],
        )

    def test_accepts_valid_leap_date(self) -> None:
        self.assertEqual(
            self.check(**{"last-reviewed": "2028-02-29", "next-review": "2028-02-29"}),
            [],
        )

    def test_rejects_invalid_and_noncanonical_dates(self) -> None:
        for field, value in (
            ("last-reviewed", "2026-02-30"),
            ("next-review", "2026-02-30"),
            ("last-reviewed", "2026-8-02"),
            ("next-review", "2026-08-02T00:00:00"),
        ):
            with self.subTest(field=field, value=value):
                self.assertIn(
                    f"{self.rel}: invalid {field} date: {value}",
                    self.check(**{field: value}),
                )

    def test_rejects_next_review_before_last_review(self) -> None:
        self.assertEqual(
            self.check(**{"last-reviewed": "2026-08-27", "next-review": "2026-08-26"}),
            [f"{self.rel}: next-review must not precede last-reviewed"],
        )

    def test_accepts_equal_review_dates(self) -> None:
        self.assertEqual(
            self.check(**{"last-reviewed": "2026-08-27", "next-review": "2026-08-27"}),
            [],
        )


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

    def test_rejects_missing_reference_link_and_image_targets(self) -> None:
        text = "[Guide][guide]\n![Banner][banner]\n\n[guide]: missing.md\n[banner]: missing.jpg"

        self.assertEqual(
            self.check(text),
            [
                f"{Path('docs/page.md')}: broken relative link: missing.md",
                f"{Path('docs/page.md')}: broken relative link: missing.jpg",
            ],
        )

    def test_accepts_existing_reference_target(self) -> None:
        (self.root / "docs" / "guide.md").touch()

        self.assertEqual(self.check("[Guide][guide]\n\n[guide]: guide.md"), [])

    def test_accepts_external_reference_target(self) -> None:
        self.assertEqual(
            self.check("[Project][project]\n\n[project]: https://example.com/project"),
            [],
        )

    def test_ignores_reference_definition_inside_fenced_code(self) -> None:
        self.assertEqual(self.check("```markdown\n[guide]: missing.md\n```"), [])

    def test_rejects_reference_target_escaping_repository(self) -> None:
        errors = self.check("[Private][private]\n\n[private]: ../../private.md")

        self.assertEqual(errors, [f"{Path('docs/page.md')}: link escapes repository: ../../private.md"])


if __name__ == "__main__":
    unittest.main()
