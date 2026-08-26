# i18n-testing-2026

**Issue:** A team localizes to 12 languages. The team needs to verify that German text fits in the UI, that Arabic RTL works, that dates format correctly. The team debates visual regression, pseudo-localization, snapshot testing, manual QA. The team needs the 2026 reference for i18n testing.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 test types

1. **Pseudo-localization.** Replace strings with accented/length-extended variants to expose hardcoded strings, truncation, concatenation bugs.
2. **Visual regression per locale.** Screenshot each locale in key states; detect overflow, layout breaks.
3. **RTL/LTR testing.** Mirror UI for Arabic, Hebrew; verify logical properties, icons.
4. **Locale data unit tests.** Assert that `Intl.NumberFormat('de-DE', ...).format(1234.56)` matches expected.
5. **Translation coverage CI gate.** Fail build if any locale is below N% translated.

## The 5-step CI gate pattern

1. Pseudo-loc build on every PR.
2. Visual regression for top 3 locales (en, de, ar) on UI changes.
3. Locale data unit tests for format-dependent code.
4. Translation coverage check (`@formatjs/cli`, `i18next-parser`).
5. Manual review for new locales before launch.

## The 5 anti-patterns

1. **"We'll test in production"** - users find layout breaks.
2. **Pseudo-loc skipped** - hardcoded strings ship in production.
3. **Single locale tested** - German fits, Russian doesn't.
4. **RTL as afterthought** - layout rebuild after launch.
5. **No translation coverage gate** - 30% of strings missing in German.

## Gotchas

- Pseudo-loc `[!!!!]` brackets catch concatenation bugs.
- Length extension 30-50% catches layout issues.
- Visual regression tools (Percy, Chromatic) need locale-aware baselines.
- RTL testing needs `dir="rtl"` toggled in the test environment.
- Some pseudo-loc tools (e.g., `pseudo-localization` npm) need Unicode CLDR data.

## Source URLs (verified 2026-08-10)

- https://formatjs.io/docs/getting-started/message-extraction
- https://www.npmjs.com/package/pseudo-localization
- https://docs.percy.io/
- https://www.chromatic.com/
- https://playwright.dev/docs/accessibility-testing
