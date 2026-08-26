# intl-api-workers-edge-formatting

**Issue:** Using the JavaScript Intl API in Cloudflare Workers for
           number, date, and currency formatting at the edge — runtime
           Intl support, locale data availability, and mobile rendering
           consistency
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Teams want to format numbers, currencies, and dates at the edge
(in a Cloudflare Worker) to avoid sending raw values to the client
for client-side formatting.  The Workers V8 runtime exposes Intl,
but locale coverage, constructor behavior, and ICU data size differ
from browser and Node.js environments.

## Context

Cloudflare Workers run on V8 isolates compiled with a subset of ICU
data to keep binary size small.  Since Workers runtime version 2022-03
(and confirmed through 2026), the built-in ICU bundle includes the
most common locales but excludes some regional variants.  The Intl
API surface is the same as in modern browsers, but the underlying
locale data set is not identical.

## Workers Intl runtime coverage

```
┌──────────────────────────────┬───────────┬──────────────────────┐
│ Intl constructor             │ Available │ Notes                │
├──────────────────────────────┼───────────┼──────────────────────┤
│ Intl.NumberFormat            │ Yes       │ Full                 │
│ Intl.DateTimeFormat          │ Yes       │ Full                 │
│ Intl.RelativeTimeFormat      │ Yes       │ Full                 │
│ Intl.PluralRules             │ Yes       │ Full                 │
│ Intl.Collator                │ Yes       │ Limited locale data  │
│ Intl.ListFormat              │ Yes       │ Full                 │
│ Intl.Segmenter               │ Yes       │ grapheme only        │
│ Intl.DurationFormat          │ Stage 3   │ Not yet in Workers   │
│ Intl.Locale                  │ Yes       │ Full                 │
└──────────────────────────────┴───────────┴──────────────────────┘
```

Use `Intl.NumberFormat.supportedLocalesOf(locales)` at Worker startup
to detect which requested locales are natively supported; fall back to
`'en'` for unsupported ones rather than letting the runtime silently
substitute.

## Number formatting

```js
function formatNumber(value, locale, options = {}) {
  // Guard: fall back to 'en' if locale not supported
  const supported = Intl.NumberFormat.supportedLocalesOf([locale]);
  const resolvedLocale = supported.length ? locale : 'en';

  return new Intl.NumberFormat(resolvedLocale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    ...options,
  }).format(value);
}

// Examples:
// formatNumber(1234567.89, 'de')  → "1.234.567,89"
// formatNumber(1234567.89, 'en')  → "1,234,567.89"
// formatNumber(1234567.89, 'ar')  → "١٬٢٣٤٬٥٦٧٫٨٩"  (Arabic-Indic)
```

Arabic-Indic numerals are the default for `ar` locale.  If your
mobile rendering pipeline expects ASCII digits (e.g. for downstream
parsing), pass `numberingSystem: 'latn'` via `Intl.Locale`:

```js
const locale = new Intl.Locale('ar', { numberingSystem: 'latn' });
new Intl.NumberFormat(locale).format(1234);  // "1,234"
```

## Currency formatting

```js
function formatCurrency(amount, currency, locale) {
  return new Intl.NumberFormat(locale, {
    style:                 'currency',
    currency,
    currencyDisplay:       'symbol',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// formatCurrency(9.99, 'USD', 'en-US')   → "$9.99"
// formatCurrency(9.99, 'EUR', 'de-DE')   → "9,99 €"
// formatCurrency(9.99, 'JPY', 'ja-JP')   → "¥10"  (JPY: 0 decimals)
// formatCurrency(9.99, 'CHF', 'de-CH')   → "CHF 9.99"
```

Note: `Intl.NumberFormat` knows JPY has 0 minor units; do **not**
hardcode decimal counts per currency.  The formatter is the source
of truth.

```
┌──────────────┬────────────────────┬────────────────────────────┐
│ Currency     │ Decimal digits     │ Workers behavior           │
├──────────────┼────────────────────┼────────────────────────────┤
│ USD, EUR     │ 2                  │ Correct                    │
│ JPY, KRW     │ 0                  │ Correct                    │
│ KWD, BHD     │ 3                  │ Correct                    │
│ CLF          │ 4 (rarely used)    │ Correct                    │
└──────────────┴────────────────────┴────────────────────────────┘
```

## Date and time formatting

```js
function formatDate(date, locale, options = {}) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeZone:  'UTC',
    ...options,
  }).format(date);
}

// formatDate(new Date('2026-08-22'), 'en-US')
//   → "Aug 22, 2026"
// formatDate(new Date('2026-08-22'), 'de-DE')
//   → "22. Aug. 2026"
// formatDate(new Date('2026-08-22'), 'ja-JP')
//   → "2026年8月22日"
```

Always specify `timeZone` explicitly.  Workers do not inherit a system
timezone; the default is UTC.  If the user's timezone is known (from
`cf.timezone` or a stored preference), pass it here:

```js
function formatLocalDate(date, locale, ianaTimezone) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle:  'medium',
    timeStyle:  'short',
    timeZone:   ianaTimezone ?? 'UTC',
  }).format(date);
}
```

## Mobile rendering consistency

Mobile email clients, mobile browsers, and native webviews all
render Intl-formatted strings differently:

- **Right-to-left numerals in email**: Arabic-Indic digits rendered
  by the Workers formatter are correct Unicode but some mobile email
  clients (Outlook for Android, Samsung Email) force LTR digit layout
  inside `<td>` elements without explicit `dir="rtl"`.  Prefer
  `numberingSystem: 'latn'` for transactional email bodies and use
  native numerals only in app UI.

- **Narrow no-break space in French**: `fr` locale formats large
  numbers with U+202F (narrow no-break space) as the thousands
  separator.  Some mobile email clients strip or re-encode this
  character during quoted-printable conversion, rendering `1 234`
  as `1 234` with a regular space or `1?234` with a replacement
  character.  Use `useGrouping: false` for email, or replace U+202F
  with a regular non-breaking space (U+00A0) post-format.

- **iOS Safari Intl quirks**: Pre-iOS 17 Safari has a known bug with
  `Intl.DateTimeFormat` and the `timeZone` option for some Pacific
  timezones.  Since Workers formats at the server and returns a
  string, this iOS bug is bypassed — the client receives pre-formatted
  text and does not invoke Intl locally.

- **Compact number notation on mobile**: `notation: 'compact'` is
  useful for mobile screens:

```js
new Intl.NumberFormat('en', { notation: 'compact' }).format(1200000);
// → "1.2M"

new Intl.NumberFormat('de', { notation: 'compact' }).format(1200000);
// → "1,2 Mio."
```

  Workers supports `notation: 'compact'` for all included locales.

## Locale data gaps in Workers ICU

Some less common locales fall back silently to `en` data in Workers:

```
┌────────────────────────────┬──────────────────────────────────┐
│ Locale                     │ Workers behavior (as of 2026)    │
├────────────────────────────┼──────────────────────────────────┤
│ az, ka, hy, mn             │ May use root/en data             │
│ Regional variants          │ Fully supported parent used      │
│ (e.g. es-419, zh-Hant-HK)  │                                  │
│ Script subtags (sr-Latn)   │ Supported                        │
│ Private-use subtags        │ Stripped to nearest public tag   │
└────────────────────────────┴──────────────────────────────────┘
```

Probe at startup:

```js
function auditLocaleSupport(locales) {
  const nf = Intl.NumberFormat.supportedLocalesOf(locales, {
    localeMatcher: 'best fit',
  });
  const dtf = Intl.DateTimeFormat.supportedLocalesOf(locales, {
    localeMatcher: 'best fit',
  });
  return { numberFormat: nf, dateTimeFormat: dtf };
}
```

## Anti-patterns

- Instantiating `new Intl.NumberFormat(locale)` inside a hot loop —
  construction is expensive.  Cache formatters in a module-level
  `Map<string, Intl.NumberFormat>`.
- Trusting `toLocaleString()` for locale-aware formatting — it
  delegates to Intl internally but does not let you cache the
  formatter or handle fallbacks explicitly.
- Using `Intl.Collator` for security-sensitive string comparisons
  (e.g. username deduplication) — locale-aware collation is not
  the same as byte equality; use `===` for identity checks.
- Formatting currency without specifying `currency` — throws
  `RangeError: currency code is required`; always validate user
  input before passing to the formatter.

## Gotchas

- `Intl.NumberFormat.supportedLocalesOf` returning an empty array
  does not mean the constructor will throw; it means the runtime will
  silently use a fallback locale.  Checking support before formatting
  is advisory, not a guard against exceptions.
- `Intl.DateTimeFormat` with `{ dateStyle, timeStyle }` and also
  individual fields (e.g. `{ month: 'long' }`) throws a `TypeError`
  in some runtimes; use one style or the other, not both.
- Workers isolates are reused across requests.  Module-level cached
  formatters persist across requests in the same isolate — this is
  beneficial for performance but means locale choice must not leak
  between user requests.  Key the cache by locale string, not by
  request context.
- `Intl.RelativeTimeFormat` requires an explicit `unit` parameter;
  it does not auto-select between "days" and "hours" — write your own
  unit selection logic before calling `.format()`.

## Verification

```js
// In a test Worker or via wrangler dev --remote
const tests = [
  [new Intl.NumberFormat('de').format(1234567.89), '1.234.567,89'],
  [new Intl.NumberFormat('ar').format(1234),       '١٬٢٣٤'],
  [new Intl.DateTimeFormat('ja', {
      dateStyle: 'medium', timeZone: 'Asia/Tokyo'
    }).format(new Date('2026-08-22T00:00:00Z')),    '2026年8月22日'],
];
for (const [got, expected] of tests) {
  console.assert(got === expected, `Expected ${expected}, got ${got}`);
}
```

```bash
wrangler dev --remote
curl http://localhost:8787/format?locale=de&value=1234567
# Expected: {"formatted":"1.234.567"}
```

## Related

- `documentation/categories/i18n/number-currency-formatting-2026.md`
- `documentation/categories/i18n/date-formatting-intl.md`
- `documentation/categories/i18n/cloudflare-workers-geolocation-locale-routing.md`
- `documentation/categories/i18n/compact-number-notation-locales-2026.md`
- `documentation/categories/i18n/Intl-PluralRules-2026.md`

## Source URLs

- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://tc39.es/ecma402/  (ECMA-402 Intl spec)
- https://unicode-org.github.io/icu/  (ICU project)
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
