# cldr-data-2026

**Issue:** A team ships a localized app. The German date format is wrong. The Arabic number representation is English. The currency symbol is in the wrong position. The team hardcoded "dd/mm/yyyy" and "$%d" because they didn't know CLDR exists.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Every locale-specific data point — date format, number format, currency symbol position, first day of week, plural rules, sort order — is in CLDR. Hand-rolling these is error-prone. The 2026 release is CLDR 48.2 (March 2026).

## Root cause

CLDR (Common Locale Data Repository) is the Unicode consortium's curated locale data set. The 2026 release covers 800+ locales, 100+ modern, 5 scripts each, 305 regional variants. Every major i18n library (ICU, Intl APIs, ICU4J, ICU4C, Java, .NET, JavaScript via ECMA-402) consumes CLDR data.

## The 2026 release state

- **Latest:** CLDR 48.2 released 2026-03-17
- **Previous:** CLDR 48.1 (2026-01-08), CLDR 48 (2025-10-29)
- **Coverage:** 104 modern locales, 13 moderate, 57 basic (174 total)
- **JSON package:** unicode-cldr/cldr-json
- **Spec:** UTS #35 (LDML — Locale Data Markup Language)
- **Plural rules:** ECMA-402 Intl.PluralRules uses CLDR plural categories
- **MessageFormat 2:** CLDR 47 made MF2 spec-stable

Every i18n library ships with a CLDR version. Pin the version, document it, and update on a known schedule.

## The 5 CLDR data categories

CLDR provides 5 categories of locale data that every localized app needs.

1. **Numbers** — decimal separator, grouping separator, digit shapes, percent, currency format (symbol position, spacing), negative format
2. **Dates and times** — short/medium/long/full date and time formats, AM/PM markers, day-of-week names, month names, calendar systems
3. **Time zones** — IANA timezone IDs, city names, metazone names, exemplar cities, daylight saving patterns
4. **Plurals** — CLDR plural categories (zero, one, two, few, many, other) per locale
5. **Collations** — sort order, case folding, accent handling per locale

Don't hand-roll any of these. Use the library that wraps CLDR.

## The locale data access pattern

```javascript
// JavaScript: use Intl APIs (built on CLDR 48 in 2026)
const dateFmt = new Intl.DateTimeFormat('de-DE', {
  dateStyle: 'full',
  timeStyle: 'short'
});
console.log(dateFmt.format(new Date()));  // "Montag, 10. August 2026 um 12:34"

// Use BCP 47 locale tags, not custom strings
const fmt = new Intl.NumberFormat('ar-EG', {
  style: 'currency',
  currency: 'USD'
});
console.log(fmt.format(1234.5));  // "US$ ١٬٢٣٤٫٥٠" (Arabic-Indic digits)

const pluralRules = new Intl.PluralRules('ar-EG');
console.log(pluralRules.select(0));   // "zero"
console.log(pluralRules.select(1));   // "one"
console.log(pluralRules.select(2));   // "two"
console.log(pluralRules.select(10));  // "many"
```

The Intl APIs are CLDR-backed, no setup required. For backend (Node, Python, Java), use the CLDR JSON package or the ICU library.

## The CLDR 48 new features (2025-2026)

CLDR 48 added rational number formats (`5½`), relative date+time combinations ("tomorrow at 12:30"), compact number format refinements, and clarified the `main` vs `rearguard` TZDB data source choice for timezones.

- **Rational numbers** — `5½` is now a first-class format, not a custom hack
- **Relative date+time combinations** — locale patterns for "tomorrow at 12:30" (separate pattern from fixed dates)
- **Compact number formats** — refined for 30+ locales (`1.2K` vs `1,200`)
- **TZDB data source** — implementations can now use either `main` or `rearguard` IANA TZDB
- **Flexible date formats** — additional variants for languages with different conventions

## The pin-and-track pattern

```json
// package.json — pin CLDR version in dependency
{
  "dependencies": {
    "intl-messageformat": "^10.5.0",  // bundles CLDR 48
    "cldr-core": "^48.2.0",
    "cldr-dates-full": "^48.2.0",
    "cldr-numbers-full": "^48.2.0",
    "cldr-plurals-full": "^48.2.0"
  }
}
```

For backend services, document the ICU version: `intl-messageformat`, Python `babel`, Java `jdk.charsets`, .NET `ICU.NET`. Pin in lockfile. Update quarterly; the CLDR team releases 2-4 times per year.

## The 5 anti-patterns

1. **Hand-rolling date format strings** ("dd/mm/yyyy") instead of using `Intl.DateTimeFormat`. CLDR has the locale-correct format.
2. **Hardcoding the plural categories** (e.g., "1 item / 2 items") instead of using `Intl.PluralRules`. CLDR has 6 categories for Arabic; English has 2.
3. **Concatenating currency symbols** ("$" + amount) instead of using `Intl.NumberFormat` with `style: 'currency'`. Symbol position, spacing, and decimal handling differ per locale.
4. **Shipping without a CLDR pin.** Different CLDR versions have different data. A user reporting "Arabic looks wrong in production" needs the CLDR version.
5. **Skipping locale fallback.** When a user requests `fr-CA` and you only have `fr`, fall back gracefully. `Intl` APIs do this automatically; hand-rolled lookups often don't.

## The locale fallback pattern

```javascript
// Resolved locale: 'fr-CA' -> 'fr' if 'fr-CA' data missing
const fmt = new Intl.DateTimeFormat(['fr-CA', 'fr'], { dateStyle: 'long' });
console.log(fmt.resolvedOptions().locale);  // "fr" (fell back)

// For translation lookup:
function getTranslation(key, locale) {
  const locales = [locale, ...getParentLocales(locale), 'en'];
  for (const l of locales) {
    const bundle = bundles[l];
    if (bundle && bundle[key]) return bundle[key];
  }
  return key;  // last-resort: return the key itself
}
```

Always have a fallback chain. Document the chain.

## Verification

The tell that CLDR is being used:

- `Intl.DateTimeFormat` / `Intl.NumberFormat` / `Intl.PluralRules` (or backend equivalent) is the only place dates/numbers are formatted
- The CLDR / ICU version is pinned in lockfile
- Pseudo-loc tests verify the formatting layer works without real translation
- A locale fallback chain is explicit and tested

The tell it isn't:

- A `formatDate` function with hand-rolled `"dd/mm/yyyy"` and `if (locale === 'de')` branches
- Hardcoded currency symbols (`"$"`)
- Manual plural form selection (`if (count === 1) ... else ...`)
- Different dates for "us-en" vs "en-gb" hardcoded per locale

## Gotchas

- **CLDR 48 changed some patterns** for fr_CH (grouping separator to apostrophe). Update and re-test.
- **ICU/CLDR versioning can drift.** Java JDK 17 has CLDR 41; JDK 21 has CLDR 45; Node 22 has CLDR 47; Node 24 has CLDR 48. Document the version.
- **Right-to-left locales need extra data.** Arabic, Hebrew need Bidi handling beyond CLDR. See `i18n/rtl-bidi-handling-2026.md`.
- **Plural categories are not just for English.** Arabic has 6 categories, Welsh has 6, Russian has 4. Use `Intl.PluralRules`, not `if/else`.
- **Time zones are not in CLDR.** IANA TZDB is a separate data source. CLDR uses IANA IDs but adds localized city names. Pin the IANA TZDB version separately.

## Related

- `i18n/Intl-PluralRules-2026.md` — plural category API
- `i18n/number-currency-formatting-2026.md` — Intl.NumberFormat deep dive
- `i18n/timezone-iana-temporal-2026.md` — IANA TZDB and Temporal
- `i18n/icu-message-format.md` — MessageFormat on top of CLDR plural rules

## Source URLs (verified 2026-08-10)

- https://cldr.unicode.org/index/downloads
- https://cldr.unicode.org/downloads/cldr-48
- https://cldr.unicode.org/downloads/cldr-47
- https://www.unicode.org/releases/
- https://cldr-smoke.unicode.org/spec/main/ldml/tr35-dates.html
- https://github.com/unicode-cldr/cldr-json
- https://messageformat.unicode.org/ — MF2 spec, part of CLDR 47+
- https://www.unicode.org/reports/tr35/ — UTS #35 LDML
