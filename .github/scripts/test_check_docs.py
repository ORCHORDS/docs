#!/usr/bin/env python3
"""Regression tests for repository-local documentation validation."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_docs.py")
SPEC = importlib.util.spec_from_file_location("check_docs", SCRIPT)
assert SPEC and SPEC.loader
check_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_docs)


class CheckFrontMatterTests(unittest.TestCase):
    def valid_metadata(self, cycle_days: int = 90) -> dict[str, str]:
        reviewed = date.today()
        return {
            "title": "Example policy",
            "owner": "Documentation",
            "status": "approved",
            "classification": "public",
            "last-reviewed": reviewed.isoformat(),
            "review-cycle": f"{cycle_days} days",
            "next-review": (reviewed + timedelta(days=cycle_days)).isoformat(),
        }

    @property
    def rel(self) -> Path:
        return Path("docs/policy.md")

    def check(self, metadata: dict[str, str]) -> list[str]:
        return check_docs.check_front_matter(self.rel, metadata)

    def test_accepts_valid_metadata_and_supported_review_cycles(self) -> None:
        for cycle_days in (30, 60, 90, 180):
            with self.subTest(cycle_days=cycle_days):
                self.assertEqual(self.check(self.valid_metadata(cycle_days)), [])

    def test_rejects_blank_required_fields(self) -> None:
        for field in check_docs.REQUIRED_FRONT_MATTER:
            with self.subTest(field=field):
                metadata = self.valid_metadata()
                metadata[field] = ""
                self.assertIn(f"{self.rel}: front matter blank: {field}", self.check(metadata))

    def test_rejects_missing_required_field(self) -> None:
        metadata = self.valid_metadata()
        del metadata["owner"]
        self.assertEqual(self.check(metadata), [f"{self.rel}: front matter missing: owner"])

    def test_rejects_yaml_null_and_quoted_empty_values(self) -> None:
        for scalar in ("null", "~", "''", '""'):
            with self.subTest(scalar=scalar):
                text = (
                    "---\n"
                    f"title: {scalar}\n"
                    "owner: Documentation\n"
                    "status: approved\n"
                    "classification: public\n"
                    f"last-reviewed: {date.today().isoformat()}\n"
                    "review-cycle: 30 days\n"
                    f"next-review: {(date.today() + timedelta(days=30)).isoformat()}\n"
                    "---\n"
                )
                parsed = check_docs.parse_front_matter(text)
                assert parsed is not None
                self.assertIn(f"{self.rel}: front matter blank: title", self.check(parsed))

    def test_rejects_unsupported_review_cycle(self) -> None:
        metadata = self.valid_metadata()
        metadata["review-cycle"] = "365 days"
        self.assertIn(f"{self.rel}: invalid review-cycle: 365 days", self.check(metadata))

    def test_rejects_invalid_and_noncanonical_dates(self) -> None:
        for field, value in (
            ("last-reviewed", "2026-02-30"),
            ("next-review", "2026-02-30"),
            ("last-reviewed", "2026-8-02"),
            ("next-review", "2026-08-02T00:00:00"),
        ):
            with self.subTest(field=field, value=value):
                metadata = self.valid_metadata()
                metadata[field] = value
                self.assertIn(f"{self.rel}: invalid {field} date: {value}", self.check(metadata))

    def test_rejects_next_review_before_last_review(self) -> None:
        metadata = self.valid_metadata()
        metadata["next-review"] = (date.today() - timedelta(days=1)).isoformat()
        self.assertIn(f"{self.rel}: next-review must not precede last-reviewed", self.check(metadata))

    def test_rejects_review_cycle_date_mismatch(self) -> None:
        metadata = self.valid_metadata(30)
        metadata["next-review"] = (date.today() + timedelta(days=180)).isoformat()
        self.assertIn(f"{self.rel}: next-review must match review-cycle: 30 days", self.check(metadata))

    def test_rejects_future_last_reviewed(self) -> None:
        metadata = self.valid_metadata(30)
        future = date.today() + timedelta(days=1)
        metadata["last-reviewed"] = future.isoformat()
        metadata["next-review"] = (future + timedelta(days=30)).isoformat()
        self.assertIn(f"{self.rel}: last-reviewed must not be in the future", self.check(metadata))


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

    def test_accepts_balanced_parentheses_in_markdown_destination(self) -> None:
        image = self.root / "docs" / "assets" / "plot(1).png"
        image.parent.mkdir()
        image.touch()
        self.assertEqual(self.check("![Plot](assets/plot(1).png)"), [])

    def test_rejects_missing_markdown_image(self) -> None:
        self.assertEqual(
            self.check("![Banner](missing.jpg)"),
            [f"{Path('docs/page.md')}: broken relative link: missing.jpg"],
        )

    def test_rejects_image_target_that_is_directory(self) -> None:
        (self.root / "docs" / "assets").mkdir()
        self.assertEqual(
            self.check("![Banner](assets)"),
            [f"{Path('docs/page.md')}: broken relative link: assets"],
        )

    def test_accepts_ordinary_link_to_directory(self) -> None:
        (self.root / "docs" / "guide").mkdir()
        self.assertEqual(self.check("[Guide](guide)"), [])

    def test_rejects_missing_quoted_and_unquoted_html_targets(self) -> None:
        for markup in ('<img src="missing.jpg">', "<img src='missing.jpg'>", "<img src=missing.jpg>"):
            with self.subTest(markup=markup):
                self.assertEqual(
                    self.check(markup),
                    [f"{Path('docs/page.md')}: broken relative link: missing.jpg"],
                )

    def test_rejects_html_src_target_that_is_directory(self) -> None:
        (self.root / "docs" / "assets").mkdir()
        self.assertEqual(
            self.check('<img src="assets">'),
            [f"{Path('docs/page.md')}: broken relative link: assets"],
        )

    def test_accepts_quoted_html_target_with_spaces(self) -> None:
        (self.root / "docs" / "hero banner.jpg").touch()
        self.assertEqual(self.check('<img src="hero banner.jpg">'), [])

    def test_does_not_treat_data_href_as_href(self) -> None:
        self.assertEqual(self.check('<div data-href="missing.html">Example</div>'), [])

    def test_ignores_attribute_like_prose_outside_html_tags(self) -> None:
        text = "Use img src=missing.jpg as fallback; preload href=hero.webp for the real tag."
        self.assertEqual(self.check(text), [])

    def test_accepts_external_html_source(self) -> None:
        self.assertEqual(self.check('<img src="https://example.com/banner.jpg">'), [])

    def test_ignores_html_inside_supported_markdown_code(self) -> None:
        examples = (
            '```html\n<img src="missing.jpg">\n```',
            '   ```html\n   <img src="missing.jpg">\n   ```',
            '````html\n<img src="missing.jpg">\n````',
            'Text `<img src="missing.jpg">` example',
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(self.check(text), [])

    def test_accepts_site_root_and_dynamic_html_targets(self) -> None:
        text = (
            '<a href="/app">App</a>\n'
            '<img src="${imageUrl}">\n'
            '<img src="{{ image_url }}">\n'
            '<img src="{% image_url %}">\n'
            '<img src="<% image_url %>">'
        )
        self.assertEqual(self.check(text), [])

    def test_rejects_html_target_escaping_repository(self) -> None:
        self.assertEqual(
            self.check('<a href="../../private.md">Private</a>'),
            [f"{Path('docs/page.md')}: link escapes repository: ../../private.md"],
        )

    def test_rejects_missing_reference_link_and_image_targets(self) -> None:
        text = "[Guide][guide]\n![Banner][banner]\n\n[guide]: missing.md\n[banner]: missing.jpg"
        self.assertEqual(
            self.check(text),
            [
                f"{Path('docs/page.md')}: broken relative link: missing.md",
                f"{Path('docs/page.md')}: broken relative link: missing.jpg",
            ],
        )

    def test_accepts_reference_angle_target_with_spaces(self) -> None:
        (self.root / "docs" / "guide with spaces.md").touch()
        self.assertEqual(self.check("[Guide][guide]\n\n[guide]: <guide with spaces.md>"), [])

    def test_ignores_reference_definition_inside_indented_fence(self) -> None:
        self.assertEqual(self.check("   ```markdown\n   [guide]: missing.md\n   ```"), [])

    def test_rejects_reference_image_target_that_is_directory(self) -> None:
        (self.root / "docs" / "assets").mkdir()
        self.assertEqual(
            self.check("![Banner][banner]\n\n[banner]: assets"),
            [f"{Path('docs/page.md')}: broken relative link: assets"],
        )

    def test_rejects_reference_target_escaping_repository(self) -> None:
        self.assertEqual(
            self.check("[Private][private]\n\n[private]: ../../private.md"),
            [f"{Path('docs/page.md')}: link escapes repository: ../../private.md"],
        )


if __name__ == "__main__":
    unittest.main()
