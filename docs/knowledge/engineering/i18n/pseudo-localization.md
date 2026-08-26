# pseudo-localization

**Issue:** A team ships to 15 languages. Layout breaks in German (text 30% longer), in Arabic (RTL), in Japanese (mixed scripts). Each language hits a different bug; the team fixes 15 bugs in 15 languages. The cycle repeats every feature.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A UI string that fits in English overflows in German. A field that handles English name input crashes on Cyrillic. A form that respects LTR text breaks when the user's name starts with Arabic. These are caught late, by real translators, and fixed per language.

## Root cause

Localization bugs are not translation bugs. They are i18n bugs: hardcoded strings that bypass the translation function, layout that doesn't expand for longer text, font fallbacks that miss character ranges, and direction handling that doesn't mix LTR/RTL. These are bugs the English string can never expose.

Without pseudo-localization, these bugs surface only when real translations land, often weeks or months into the localization cycle. By then, fixing one is archaeology.

## What pseudo-localization does

Pseudo-localization transforms the source string into a fake language that simulates how it will look after translation, without needing an actual translator. Three transformations are applied:

1. **Character substitution.** Replace ASCII letters with visually similar accented equivalents: `a` → `à`, `e` → `ë`, `o` → `ö`. Preserves readability for developers while testing font fallback and character rendering.
2. **String expansion.** Pad each string to simulate longer text. German runs 30% longer than English; Finnish 40-50%. Wrap with boundary markers (e.g., `[...]` or `⟦...⟧`) so missing translations are visually obvious.
3. **RTL mirroring** (for the bidirectional pseudo-locale). Mirror text to simulate right-to-left reading order. Catches layout bugs before Arabic/Hebrew testing.

Example: `"Welcome to our application"` becomes `"[Ẃëĺçöṁë ţö öüŕ àṗṗľïčàţïöñ]"` (accented + brackets) or `"[Weeelcooomee tooo ouuur aaappliiicaaatiiioon]"` (expanded + brackets).

The accented form tests character encoding and font fallback. The expanded form tests layout. The bracketed form tests the translation function itself — any string without brackets was bypassed by `t()` or `i18n.t()`.

## The 80% rule

Pseudo-localization catches approximately 80% of i18n bugs before any real translation exists. Teams that skip it wait for real translations, ship untested code, and then fix the same bugs 15 times across 15 languages.

The bugs pseudo-localization catches:

- Hardcoded strings that don't get replaced (they show up as English while everything else has brackets)
- Text truncation (expansion reveals layout breaks)
- Character encoding issues (accented characters render or don't)
- RTL layout issues (if using RTL pseudo-locale)
- String concatenation in user-facing copy
- Untranslated text in user-generated content paths
- Font fallbacks missing ranges
- Time/date/number formatting assumptions

## The expansion rates

| Language | Expansion from English |
|---|---|
| Chinese (Simplified) | 20-30% shorter (chars); wider glyphs |
| Japanese | similar to Chinese; mixed scripts |
| Korean | 15-25% shorter |
| Spanish, Portuguese, Italian | 15-25% longer |
| French | 20-30% longer |
| German | 30-40% longer |
| Russian | 30-40% longer |
| Finnish, Turkish | 40-50% longer (agglutinative) |
| Arabic | similar length; different visual weight |
| Vietnamese | similar length; taller glyphs due to diacritics |

The design rule: design for 40% expansion. If your UI works in a 40%-expanded pseudo-translation, it works in almost every real language.

## The implementation patterns

**iOS:** Xcode scheme run options include "Double-Length Pseudolanguage" and "Accented Pseudolanguage." Set in the scheme editor; no code change.

**Android:** Set `android.enablePseudoLocalesInDebugBuilds=true` in `gradle.properties`. Generates `en-XA` (accented + expansion) and `ar-XB` (bidirectional) pseudo-locales automatically.

**Web (pseudo-l10n or i18n-pseudo npm package):**

```bash
npm install -D pseudo-l10n
pseudo-l10n src/locales/en.json src/locales/pseudo-en.json --expansion=30
pseudo-l10n src/locales/en.json src/locales/pseudo-ar.json --rtl
```

```json
// package.json
{
  "scripts": {
    "pseudo": "pseudo-l10n src/locales/en.json src/locales/pseudo-en.json",
    "pseudo:rtl": "pseudo-l10n src/locales/en.json src/locales/pseudo-ar.json --rtl"
  }
}
```

```yaml
# .github/workflows/test.yml
- name: Generate pseudo-locales
  run: |
    npm install -g pseudo-l10n
    pseudo-l10n src/locales/en.json src/locales/pseudo-en.json
- name: Run i18n tests
  run: npm run test:i18n
```

## The CI gate pattern

Generate the pseudo-locale as part of the build, then run the existing end-to-end test suite against it. No new tests needed — just point existing tests at the pseudo-locale.

```yaml
# .github/workflows/i18n.yml
- name: Run E2E against pseudo-locale
  env:
    LOCALE: qps-ploc    # pseudo-locale code
    BASE_URL: http://localhost:3000
  run: npm run test:e2e
- name: Check for untransformed strings
  run: node scripts/check-hardcoded-strings.js
```

The check script searches rendered DOM for strings that should have brackets but don't, flagging hardcoded user-facing text. Any new untransformed string is a regression.

## The seven strategies

i18n-pseudo provides 7 transformation strategies:

| Strategy | Tests |
|---|---|
| Accented characters | Font fallback, UTF-8 encoding |
| Text expansion | Layout overflow, truncation |
| Brackets/wrappers | Translation function coverage |
| Bidi/RTL | Layout direction bugs |
| Mirrored | Visual regression in mixed content |
| Combined | Maximum coverage in one pass |
| Custom expansion % | Specific language target |

Run the maximum preset in CI. Use specific strategies in development for targeted debugging.

## Verification

The tell that pseudo-localization is working:

- A pseudo-locale is in the language switcher during development (and removed before production)
- CI runs E2E tests against the pseudo-locale on every PR
- A new engineer adding UI text sees the missing brackets in their first pseudo-locale run
- Layout fits at 40% expansion; no truncation, no overflow

The tell it isn't:

- "We'll test with German when we have German translations" (German lands 6 weeks after the feature)
- A bug is found per language after each translation lands
- Layout fits in English and breaks in every other language

## Gotchas

- **Remove the pseudo-locale before production.** It is a development artifact; users should not see `[Ẃëĺçöṁë]`.
- **Design for 40% expansion, not 30%.** German is 30-40%; Finnish is 40-50%. The 40% number is the safer target.
- **Expansion padding must be inside the brackets.** If the brackets are tight but the inside is unpadded, layout still overflows.
- **ICU arguments and HTML tags must pass through unchanged.** Pseudo-localizers that touch `{count}` or `<b>` produce unparseable strings. Test with a real ICU/HTML/printf sample.
- **Pseudo-localization catches i18n bugs, not translation bugs.** A wrong translation is still wrong after pseudo-localization. Real translators are still required for content correctness.
- **Customize the expansion % per locale.** A pseudo-locale for German is 30% expansion; for Finnish 50%.

## Related

- `i18n/icu-message-format.md` — the message format pseudo-locale preserves
- `i18n/rtl-bidi-handling.md` — RTL pseudo-locale surfaces direction bugs
- `i18n/locale-negotiation.md` — choosing which pseudo-locale to enable

## Source URLs (verified 2026-08-10)

- https://www.drizz.dev/post/localization-testing-for-mobile-apps
- https://l10n.dev/help/pseudo-localization
- https://i18nagent.ai/en/guides/pseudo-localization-testing
- https://helpmetest.com/blog/pseudo-localization-testing/
- https://www.wayline.io/tools/pseudolocalization-generator
