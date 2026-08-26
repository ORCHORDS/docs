# CLDR exemplar characters for resource coverage

**Issue:** A font, keyboard, search index, or test corpus is declared to “support a locale” after covering only ASCII or every Unicode character seen in one translation file. Both shortcuts miss ordinary language characters or produce unbounded assets.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Use version-pinned CLDR exemplar sets as one input to coverage planning. Distinguish main, auxiliary, number, punctuation, person-name punctuation, and index exemplars; each answers a different resource question. Expand UnicodeSet expressions with a maintained library and record the CLDR version, locale inheritance, and tailored additions.

For font subsetting, union translated content, required UI symbols, locale exemplars, fallback glyphs, and shaping marks, then validate with real text. For keyboards or index headings, use the matching exemplar type rather than the main alphabet. Preserve an escape/fallback path for names, loanwords, scientific content, and user-generated text outside the set.

## Verification

Test inherited locales, combining sequences, digraph/index labels, auxiliary letters, non-Latin digits, punctuation, mixed-script names, newly added CLDR characters, and fallback-font activation. Diff expanded sets during CLDR upgrades and review size changes.

## Gotchas

Exemplars are neither an allowlist for user input nor a complete language repertoire. They are locale data for typical use, can change by CLDR release, and do not prove that a font shapes the script correctly.

## Sources

- Unicode Consortium, [LDML Part 2: General — exemplar characters](https://unicode.org/reports/tr35/tr35-general.html#Exemplars)
- Unicode Consortium, [CLDR release data](https://cldr.unicode.org/index/downloads)
