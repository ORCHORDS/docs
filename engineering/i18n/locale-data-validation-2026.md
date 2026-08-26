# locale-data-validation-2026

**Issue:** A team ships a multilingual app. A translator adds a new locale `xx-YY` (a fake locale). The build doesn't catch it. The locale shows up in the language selector. The user picks it. The page is empty.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Locale data is the metadata about locales: codes, names, scripts, regions, currencies, formatting rules. Validating this data at build time and runtime prevents empty-locale bugs and CLDR mismatches.

## Root cause

A locale code is a BCP 47 tag. CLDR is the canonical source. A 2026 production app should validate that every locale it claims to support is in CLDR with the expected coverage level.

## The 5 locale data fields

A locale has 5 canonical data fields.

1. **Code** — BCP 47 tag (e.g., `fr-CA`, `zh-Hans-CN`, `pt-BR`)
2. **Display name** — human-readable name in the locale's own language (autonym) or in English
3. **Script** — writing system (Latn, Cyrl, Arab, Hans, Hant, etc.)
4. **Region** — country code (CA, US, BR, etc.) — optional
5. **Number/currency/date formatting** — CLDR-backed locale-specific rules

The 5 fields cover the 2026 minimum locale data.

## The 4-step validation pattern

1. **Validate the locale code** — match against BCP 47 regex
2. **Check CLDR coverage** — Modern, Moderate, or Basic per CLDR's coverage level
3. **Validate the data** — display name exists, currency code is ISO 4217, etc.
4. **Test rendering** — actually use the locale; verify Intl APIs work

The 4 steps catch most locale data issues at build time.

## The BCP 47 regex

```javascript
// RFC 5646 BCP 47 language tag regex
const BCP47_REGEX = /^(
  (([A-Za-z]{2,3}(-[A-Za-z]{3}(-[A-Za-z]{3})){0,2})|[A-Za-z]{4}|[A-Za-z]{5,8})  # language
  (-(?:[A-Za-z]{4}))?                                                              # script
  (-(?:[A-Za-z]{2}|[0-9]{3}))?                                                      # region
  (-(?:[A-Za-z0-9]{5,8}))*                                                          # variant
  (-[0-9A-WY-Za-wy-z]+)*                                                            # extension
  (-x(?:[A-Za-z0-9]{1,8}))*                                                          # private-use
)$/x;

function isValidLocale(code) {
  return BCP47_REGEX.test(code);
}

isValidLocale('fr-CA');     // true
isValidLocale('xx-YY');     // false
isValidLocale('zh-Hans-CN'); // true
isValidLocale('en');        // true
```

The regex is the canonical validator for BCP 47 tags. Use it at every entry point.

## The CLDR coverage check

```typescript
import supportedLocales from '@cldr-json/core/supported-locales.json';

interface CLDRAvailability {
  coverage: 'modern' | 'moderate' | 'basic' | 'core' | 'unavailable';
}

function getCLDRCoverage(locale: string): CLDRAvailability {
  return supportedLocales[locale]?.coverage || 'unavailable';
}
```

The 2026 production pattern: only claim Modern coverage for locales CLDR marks as Modern. Claiming more is a lie; users get translation gaps.

## The 5 validation rules

| Field | Validation | Source |
|---|---|---|
| Code | matches BCP 47 regex | RFC 5646 |
| Display name | non-empty string in target locale's autonym | CLDR |
| Script | valid ISO 15924 code | CLDR / UAX #24 |
| Region | valid ISO 3166-1 alpha-2 | ISO 3166 |
| Currency | valid ISO 4217 code | ISO 4217 |

The 5 rules catch most locale data issues.

## The 5 anti-patterns

1. **No validation; trust user input.** A typo in the locale code ships to production.
2. **Hard-coded locale data.** `const SUPPORTED = ['en', 'fr']`; missed a locale; QA doesn't catch it.
3. **Mixing case in locale codes.** `en-US` vs `en-us`; CLDR uses canonical case.
4. **Inventing locale codes.** `xx-YY` doesn't exist in CLDR; the app will fail.
5. **No CLDR coverage check.** Claiming "we support Spanish" without checking if CLDR has Modern coverage for `es`.

## The 4 build-time checks

Add to CI / build pipeline.

1. **Linter:** every locale code in `supportedLocales` matches BCP 47
2. **Coverage check:** every locale in `supportedLocales` has CLDR coverage >= `Moderate` (or your minimum)
3. **Data validation:** every locale has display name, currency, region
4. **Render test:** every locale can format a number, a date, a currency (smoke test)

The 4 build-time checks catch most issues before deploy.

## The 5 production data sources

| Source | Use | License |
|---|---|---|
| CLDR (cldr-json npm) | canonical locale data | Unicode license |
| @cspell/dict-en / similar | spellcheck in locale | various |
| restcountries / countries | country codes | MIT |
| ISO 3166 / 4217 lists | country / currency codes | public |
| i18n-iso-countries npm | countries with translations | MIT |

The 5 sources cover the 2026 production needs.

## The 4-step runtime validation

For runtime (not just build time):

1. **Sanitize the input locale** — match against supported set
2. **Resolve to a supported locale** — via `Intl.LocaleMatcher`
3. **Cache the resolved locale** — per session
4. **Fall back to default** — if no match, use the app's default locale

The 4-step runtime validation is the 2026 production pattern.

## The 5 best practices

1. **Validate at every entry point.** API endpoints, query params, cookies, URLs.
2. **Use canonical case.** `en-US`, not `en-us` or `EN-US`.
3. **Pin locale data version.** Document which CLDR version; update quarterly.
4. **Test with the locale's own script.** Arabic UI in Arabic; Japanese UI in Japanese.
5. **Store locale data in a single source of truth.** A JSON file, a database table, or generated from CLDR.

## The 4 build-time lint example

```javascript
// scripts/lint-locales.js
import supportedLocales from './config/locales.json';
import cldr from '@cldr-json/core';

const errors = [];

for (const locale of supportedLocales) {
  // 1. BCP 47 regex
  if (!isValidLocale(locale.code)) {
    errors.push(`Invalid locale code: ${locale.code}`);
  }
  // 2. CLDR coverage
  const coverage = cldr.availableLocales[locale.code];
  if (!coverage || coverage === 'unavailable') {
    errors.push(`Locale not in CLDR: ${locale.code}`);
  }
  // 3. Display name
  if (!locale.displayName || locale.displayName.length === 0) {
    errors.push(`Missing display name: ${locale.code}`);
  }
  // 4. Currency
  if (locale.currency && !isValidCurrency(locale.currency)) {
    errors.push(`Invalid currency: ${locale.currency} for ${locale.code}`);
  }
}

if (errors.length > 0) {
  console.error(errors.join('\n'));
  process.exit(1);
}
```

The 4 checks catch most issues; run in CI.

## The 4 things to test

For each supported locale:

1. **Render a number** — `Intl.NumberFormat(locale).format(1234.56)` — verify no NaN
2. **Format a date** — `Intl.DateTimeFormat(locale).format(new Date())` — verify output
3. **Format a currency** — `Intl.NumberFormat(locale, {style: 'currency', currency}).format(...)` — verify symbol
4. **Sort with collator** — `new Intl.Collator(locale).compare('a', 'b')` — verify behavior

The 4 runtime tests catch CLDR + Intl integration issues.

## Verification

The tell that locale data validation is real:

- BCP 47 regex at every entry point
- CLDR coverage check at build time
- Display name, currency, region for every supported locale
- Smoke test rendering for every locale
- Build fails on missing or invalid locale data

The tell it isn't:

- "Just hard-code the locales"
- No CLDR coverage check
- No smoke test rendering
- Locales that fail silently in production
- `xx-YY` or other invalid codes in production

## Gotchas

- **Case matters.** `en-US` is correct; `en-us` is invalid (lowercase region).
- **Script is optional but matters.** `sr` is ambiguous (Latin or Cyrillic); use `sr-Latn` or `sr-Cyrl`.
- **Region can be a number for UN/Locales.** `es-419` = Latin American Spanish; 419 is the UN M.49 code.
- **Private-use subtags** (`x-...`) are for internal use; not in CLDR.
- **CLDR coverage is per-locale, not per-script.** `zh-Hans` may be Modern; `zh` may be Basic.

## Related

- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/locale-negotiation.md` — fallback chain
- `i18n/icu-message-format.md` — message format
- `i18n/character-encoding-utf-8-2026.md` — encoding

## Source URLs (verified 2026-08-10)

- https://datatracker.ietf.org/doc/html/rfc5646 — RFC 5646 BCP 47
- https://www.rfc-editor.org/rfc/rfc4647 — RFC 4647 Matching
- https://cldr.unicode.org/ — CLDR
- https://cldr.unicode.org/index/cldr-spec/coverage-levels — coverage levels
- https://www.iso.org/iso-3166-country-codes.html — ISO 3166
- https://www.iso.org/iso-4217-currency-codes.html — ISO 4217
- https://www.unicode.org/reports/tr35/ — UTS #35 LDML
- https://www.npmjs.com/package/@cldr-json/core — CLDR JSON npm
- https://www.npmjs.com/package/i18n-iso-countries — i18n-iso-countries
- https://github.com/wooorm/bcp-47 — bcp-47 npm
