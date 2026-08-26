# i18n-localization-testing

**Issue:** Internationalization bugs are structural: a hardcoded string buried in a component, a layout that breaks when German text runs 35 percent longer than English, a plural form that produces "1 items" in Polish where the language has six plural categories, a date parsed as month/day when the locale says day/month, or a currency rendered with the wrong symbol after a rounding change. These defects are cheap to prevent with automated checks in the first weeks of a project and brutally expensive to retrofit after translation budgets have been spent — QA guides consistently estimate pseudo-localization alone catches roughly 80 percent of localization bugs before any translator is invoiced. Yet most teams ship with no i18n tests at all because the surface area feels large. The engineering problem is a compact set of automated layers: string externalization audits, pseudo-localization smoke tests, ICU message validation, locale-aware formatting assertions, and RTL rendering checks, each targeted at a distinct bug class.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Bug classes and the test that catches each

1. **Hardcoded strings — extraction audit.** A lint rule (eslint-plugin-i18n, a custom AST check, or a script diffing string literals against the message catalog) fails CI when user-visible text appears outside the catalog. This is the single highest-leverage check; guides from Crowdin and SimpleLocalize rank hardcoded strings as the most common i18n mistake in real codebases.
2. **Layout breakage — pseudo-localization.** A build step wraps and pads every message (accented characters, bracket delimiters, 30-40 percent expansion) so untranslated truncation, overflow, and clipped buttons are visible in every screenshot and component test without paying for translation. If the pseudo-localized build renders wrong, every real locale will render wrong.
3. **Plural/gender grammar — ICU MessageFormat validation.** Messages using ICU syntax must compile and must enumerate every plural category the target locale requires (Russian and Polish need few/many/other, Arabic needs six categories). A catalog test parses each message with Intl MessageFormat across all supported locales and fails on parse errors or missing categories that would silently render "other" for every count.
4. **Number/date/currency drift — Intl snapshot assertions.** Unit tests assert the exact formatted output of currency, date, and number formatting per locale (1.234,56 € versus €1,234.56) using the runtime's own Intl implementation, catching regressions when locale data, currency codes, or rounding logic change.
5. **Mirror-image layout — RTL smoke tests.** Rendering key screens with a pseudo-RTL locale in component or E2E tests catches icons, margins, and directional CSS that don't flip. Logically-flipped punctuation and truncation direction are frequent escapees here.

## Message catalog integrity

1. **Key parity across locales.** A catalog diff test fails when a key exists in the source locale but is missing from any target, treating translation gaps as build failures rather than runtime fallback surprises. Decide policy explicitly: fail on missing, or fail only on missing-with-no-fallback.
2. **Placeholder and tag consistency.** Every message using variables like name or count must use identical placeholder names and inline markup tags in every locale. Mismatched placeholders crash formatters or leak literal tokens to users; a structural comparison test catches what translators' eyes miss.
3. **Interpolation fuzzing.** Feed placeholder values containing unicode, bidirectional control characters, markup, and very long strings through the formatter to verify escaping and to surface injection paths; untranslated user data concatenated into localized templates is a real XSS vector.
4. **Fallback chain verification.** Assert the resolved message hierarchy (locale, language, default) so a missing regional translation falls back intentionally and observably, rather than to a raw key shown to users.

## Making i18n tests cheap to run

1. **Locale matrix in component tests, not E2E.** Run the full locale matrix (en, de, ar, ja, pl at minimum: long, RTL, multi-plural, wide-glyph) in fast component/Storybook tests, and reserve E2e runs for one pseudo-localized pass plus one RTL pass over the golden paths. Visual-regression tools like Percy handle per-locale baselines natively.
2. **Freeze locale data in tests.** Pin ICU/CLDR versions and timezone overrides ( vitest fake timers or a fixed TZ env ) so formatting snapshots don't flip when the Node runtime updates its bundled locale database mid-CI.
3. **Catalog as compiled artifact.** Compile catalogs (formatjs compile, lingui compile) in CI with a check that committed compiled output matches source messages, making runtime lookup failures impossible and diff review trivial.
4. **Translation-in-the-loop smoke.** Before a release, run pseudo-localization again plus a mechanical back-translation spot check on the ten highest-traffic screens; this validates that the localization pipeline (extraction, upload, merge) still round-trips, which is where process bugs hide.

## Common anti-patterns

1. **Testing only in English.** An all-English suite certifies nothing about i18n; the minimum viable layer is the extraction audit plus one pseudo-localized E2E run, which together cost under a day to add.
2. **Concatenating translated fragments.** Building sentences by joining translated pieces ("Welcome" + name + "to" + product) breaks in every language with different word order; tests that assert full-sentence messages with placeholders make this anti-pattern impossible to reintroduce silently.
3. **Assuming string length in tests.** Tests that assert truncated text or fixed-width containers with English assumptions fail legitimately under expansion — that failure is the feature working; fix the layout, not the test.
4. **Screenshot-only locale checks.** Visual diffs catch layout breakage but not wrong plural forms or wrong number formatting, which render identically-shaped text; pair screenshots with ICU and Intl assertions.
