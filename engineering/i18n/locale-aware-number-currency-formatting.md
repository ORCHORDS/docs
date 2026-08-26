# Locale-Aware Number and Currency Formatting

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A price of `$1,234.56` is shown to a German user. The format
is wrong — in `de-DE` the correct rendering is `1.234,56 €`,
with a period as the thousands separator, a comma as the
decimal separator, and the symbol after the number. A Japanese
user sees `¥1,234.56` with two decimal places; JPY has no
subunit and the display should be `¥1,235`.

## Context

`Intl.NumberFormat` is the ECMA-402 standard for language-
sensitive number and currency formatting. It is built into
every modern browser and Node.js 12+. No third-party library
is required. Three independent conventions vary by locale:
decimal separator (period vs comma), grouping separator
(comma, period, space, or none), and currency symbol position
(prefix vs suffix, with or without a space). A fourth axis
is the digit script — Arabic-Indic digits in `ar-EG`, Han
decimal digits in `zh-Hans-CN-u-nu-hanidec`.

## 1. Basic usage

```javascript
// US English — symbol prefix, period decimal, comma group
new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD'
}).format(1234.56)
// → "$1,234.56"

// German — symbol suffix, comma decimal, period group
new Intl.NumberFormat('de-DE', {
  style: 'currency', currency: 'EUR'
}).format(1234.56)
// → "1.234,56 €"

// Japanese — symbol prefix, no subunit (rounds to integer)
new Intl.NumberFormat('ja-JP', {
  style: 'currency', currency: 'JPY'
}).format(1234.56)
// → "¥1,235"

// Arabic — Arabic-Indic digits
new Intl.NumberFormat('ar-EG').format(123456.789)
// → "١٢٣٬٤٥٦٫٧٨٩"
```

## 2. Currency display options

| `currencyDisplay` | Output (en-US / USD 1234)       |
|-------------------|---------------------------------|
| `"symbol"`        | `$1,234` (default)              |
| `"narrowSymbol"`  | `$1,234` (avoids `US$` prefix)  |
| `"code"`          | `USD 1,234`                     |
| `"name"`          | `1,234 US dollars`              |

`"narrowSymbol"` is preferred in product UIs — it drops
the country disambiguator (`CA$` → `$`) when the locale
already implies the currency. Use `"code"` in export
reports or contexts where multiple currencies appear on
the same page.

```javascript
new Intl.NumberFormat('en-CA', {
  style: 'currency', currency: 'CAD',
  currencyDisplay: 'narrowSymbol'
}).format(1234)
// → "$1,234" (not "CA$1,234")

new Intl.NumberFormat('en-CA', {
  style: 'currency', currency: 'CAD',
  currencyDisplay: 'code'
}).format(1234)
// → "CAD 1,234"
```

## 3. Compact notation

Use `notation: 'compact'` for dashboard metrics and labels
where space is constrained.

```javascript
new Intl.NumberFormat('en-US', {
  notation: 'compact',
  compactDisplay: 'short'
}).format(1_200_000)
// → "1.2M"

new Intl.NumberFormat('de-DE', {
  notation: 'compact',
  compactDisplay: 'short'
}).format(1_200_000)
// → "1,2 Mio."

new Intl.NumberFormat('ja-JP', {
  notation: 'compact',
  compactDisplay: 'short'
}).format(1_200_000)
// → "120万"
```

`compactDisplay: 'long'` gives `"1.2 million"` in en-US
and is appropriate for screen-reader-first contexts.

## 4. Significant digits vs fraction digits

Two independent controls govern decimal precision. Do not
mix them in the same formatter — pick one axis.

```javascript
// Fixed fraction digits (floor/ceil to 2 places)
new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2, maximumFractionDigits: 2
}).format(1.5)     // → "1.50"

// Significant digits (rounds to N meaningful digits)
new Intl.NumberFormat('en-US', {
  minimumSignificantDigits: 3, maximumSignificantDigits: 3
}).format(12345.6) // → "12,300"
```

## 5. Performance: caching formatter instances

`new Intl.NumberFormat()` constructs locale data; do not
call it on every render. Cache by a compound key.

```javascript
const _fmts = new Map();
function formatCurrency(amount, currency, locale) {
  const k = `${locale}|${currency}`;
  if (!_fmts.has(k)) {
    _fmts.set(k, new Intl.NumberFormat(locale, {
      style: 'currency', currency,
      currencyDisplay: 'narrowSymbol',
    }));
  }
  return _fmts.get(k).format(amount);
}
```

## Anti-patterns

- `"$" + amount.toFixed(2)` — hardcodes US symbol position,
  decimal separator, and grouping for every locale.
- Arithmetic on formatted strings. Store raw numbers or
  integer cents; format only at the display layer.
- Creating `new Intl.NumberFormat()` inside a render
  function or tight loop without caching.
- Storing monetary values as floating-point dollars
  (`0.1 + 0.2 !== 0.3`); use integer cents.

## Gotchas

- JPY has 0 default fraction digits; KWD has 3; USD has 2.
  The number of fraction digits is CLDR data, not a
  constant. Override with explicit `minimumFractionDigits`
  only when you need to deviate from the currency default.
- In `ar-EG`, `Intl.NumberFormat` outputs Arabic-Indic
  digits (٠١٢٣) by default. If you need ASCII digits in
  Arabic contexts, append `-u-nu-latn` to the locale tag:
  `new Intl.NumberFormat('ar-EG-u-nu-latn', …)`.
- `currencySign: 'accounting'` renders negative values as
  `(1,234.56)` instead of `-$1,234.56`. Required for
  financial UIs targeting accountants.
- `formatToParts()` returns an array of typed tokens
  (`currency`, `integer`, `decimal`, `fraction`) useful
  for applying custom styling to individual parts.

## Verification

- Format `1234.56` as `USD` in `en-US`, `de-DE`, `ja-JP`,
  and `ar-EG`. Confirm separator, symbol position, digit
  script, and fraction digits are all locale-correct.
- Search the codebase for `toFixed` and `$` concatenation
  patterns on monetary values.
- Add a unit test asserting `de-DE` formats `1000.5` as
  `"1.000,50 €"` (period group, comma decimal, suffix).
- Confirm formatter instances are created at module scope
  or memoized, not inside render.

## Related

- `i18n/number-formatting-intl.md`
- `i18n/currency-formatting-patterns.md`
- `i18n/compact-number-notation-locales-2026.md`
- `i18n/locale-negotiation.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- https://tc39.es/ecma402/#numberformat-objects
- https://www.unicode.org/cldr/charts/latest/supplemental/currency_data.html
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts
- https://caniuse.com/intl-numberformat
