# number-currency-formatting-2026

**Issue:** A product displays $1,234.56 to a German customer. The format is wrong — in de-DE the number is `1.234,56 €`, the symbol goes after, and the decimal separator is a comma. The customer asks for a refund. The team hardcoded the US format.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Numbers and currencies look wrong in non-US locales. `1,234.56` is read as "one point two three four five six" in German, not "one thousand two hundred thirty-four point five six." A price of `€1,000.00` displayed to a US customer is the European convention; the same number is `$1.000,00` in de-DE.

## Root cause

Three different conventions differ across locales:

- **Decimal separator.** US/UK: `.` (period). Most of Europe, much of South America: `,` (comma).
- **Thousands separator.** US/UK: `,` (comma). Most of Europe: `.` (period) or space. India: lakh/crore grouping (`1,23,456.789`).
- **Symbol position.** US/UK: prefix ($1,234.56). Germany/France: suffix (1.234,56 €). Some currencies (Swiss) separate with space.

Currency rounding also differs. JPY has no subunit (¥1,235 from $1,234.56). KWD has 3 decimal places. USD has 2.

## The `Intl.NumberFormat` API

`Intl.NumberFormat` is the ECMA-402 standard for language-sensitive number and currency formatting. Built into every modern browser and Node.js. No library required.

```javascript
// US English
new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(1234.56)
// → "$1,234.56"

// German (symbol after, comma as decimal)
new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(1234.56)
// → "1.234,56 €"

// UK English
new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(1234.56)
// → "£1,234.56"

// Japanese yen (no subunit, rounds to integer)
new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY" }).format(1234.56)
// → "￥1,235"

// Indian English (lakh/crore grouping)
new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(1234.56)
// → "₹1,234.56"

// Arabic (Arabic-Indic digits)
new Intl.NumberFormat("ar-EG").format(123456.789)
// → "١٢٣٬٤٥٦٫٧٨٩"

// Chinese (Han decimal digits)
new Intl.NumberFormat("zh-Hans-CN-u-nu-hanidec").format(123456.789)
// → "一二三,四五六.七八九"
```

## The styles

`Intl.NumberFormat` supports four styles:

| Style | Use | Example |
|---|---|---|
| `decimal` | Plain numbers | `1,234.56` |
| `currency` | Money | `$1,234.56` |
| `percent` | Percentages | `12.5%` |
| `unit` | Units (length, mass, etc.) | `50 km/h` |

For currency, the required option is `currency` (ISO 4217 code: `USD`, `EUR`, `GBP`, `JPY`, etc.).

## The currency display options

| Option | Behavior |
|---|---|
| `currencyDisplay: "symbol"` (default) | Local symbol (`$`, `€`, `£`) |
| `currencyDisplay: "code"` | ISO code (`USD 1,234.56`) |
| `currencyDisplay: "narrowSymbol"` | Narrow symbol (`$100` instead of `US$100`) |
| `currencyDisplay: "name"` | Local name (`1,234.56 US dollars`) |
| `currencySign: "accounting"` | Negative in parentheses (accounting style) |

## The five rules

**Always use `Intl.NumberFormat`.** Manual string manipulation (`"$" + amount.toFixed(2)`) is wrong for any non-US locale. The library handles symbol placement, decimal and thousands separators, digit grouping, and rounding.

**Keep the raw number for calculations.** Store the price as a plain number (or integer in the smallest currency unit, e.g. cents) and only format at the display layer. Never use formatted strings in arithmetic.

```javascript
// Wrong: arithmetic on formatted strings
const total = "$1,234.56" + "$500.00"  // → "$1,234.56$500.00"

// Right: arithmetic on raw numbers, format at display
const total = 1234.56 + 500.00  // → 1734.56
new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(total)
// → "$1,734.56"
```

**Cache formatter instances.** Creating a new `Intl.NumberFormat` is not free; cache by locale + currency combination.

```javascript
const formatters = new Map();
function fmt(amount, currency, locale) {
  const key = `${locale}-${currency}`;
  if (!formatters.has(key)) {
    formatters.set(key, new Intl.NumberFormat(locale, { style: "currency", currency }));
  }
  return formatters.get(key).format(amount);
}
```

**Store monetary values in the smallest unit.** Cents for USD, yen for JPY (no subunit), fils for KWD (3 subunits). Avoids floating-point rounding bugs.

```javascript
// Wrong: floating-point dollars
const price = 0.1 + 0.2  // → 0.30000000000000004

// Right: integer cents
const priceCents = 10 + 20  // → 30
new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(priceCents / 100)
// → "$0.30"
```

**Test with multiple locales.** The US format hides bugs that the German format exposes (decimal separator, symbol position). Test with `de-DE`, `fr-FR`, `ja-JP`, `ar-EG` to catch locale-specific bugs.

## The currency rounding gotcha

`Intl.NumberFormat` rounds based on the currency's default fraction digits:

```javascript
new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY" }).format(1234.56)
// → "￥1,235" (rounds to integer; JPY has no subunit)
```

JPY has 0 fraction digits by default. KWD has 3. The number of fraction digits is part of the currency's CLDR data, not a constant.

For consistent rounding across all currencies, explicitly set `minimumFractionDigits` and `maximumFractionDigits`:

```javascript
new Intl.NumberFormat("ja-JP", {
  style: "currency", currency: "JPY",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0
}).format(1234.56)  // → "￥1,235"
```

## The RTL bidirectionality for currency

In an Arabic UI, the currency value and symbol are bidirectional:

```html
<p>المبلغ: <bdi>1,234.56 $</bdi></p>
```

The `<bdi>` element isolates the currency display so digits and symbols don't reorder with surrounding Arabic text. Without it, `$1,234.56` inside an RTL paragraph may display in unexpected order.

## The percentage style

For percentages, pass the value as a fraction (0.125 for 12.5%):

```javascript
new Intl.NumberFormat("en-US", { style: "percent" }).format(0.125)
// → "13%" (rounded)

new Intl.NumberFormat("de-DE", { style: "percent" }).format(0.125)
// → "13 %" (German has space before %)
```

The `maximumFractionDigits` option controls precision.

## The unit style

For measurements, use the `unit` style with a CLDR unit identifier:

```javascript
new Intl.NumberFormat("en-US", { style: "unit", unit: "kilometer-per-hour" }).format(50)
// → "50 km/h"

new Intl.NumberFormat("en-US", { style: "unit", unit: "liter", unitDisplay: "long" }).format(16)
// → "16 liters"
```

Common units: `kilometer-per-hour`, `meter`, `kilogram`, `liter`, `celsius`, `fahrenheit`, `byte`, `megabyte`, `gigabyte`. Locale-aware formatting handles the spacing and unit suffix per locale.

## Verification

The tell that number/currency formatting is working:

- All currency values use `Intl.NumberFormat` with `style: "currency"` and an explicit `currency` code
- Monetary values are stored in the smallest currency unit (cents, yen, fils)
- Formatter instances are cached, not recreated per render
- Test coverage includes `de-DE`, `ja-JP`, `ar-EG` — at least one non-US locale with non-Latin digits
- RTL display uses `<bdi>` for currency values in Arabic text

The tell it isn't:

- `("$" + amount.toFixed(2))` anywhere in the codebase
- The German customer sees `$1,234.56` instead of `1.234,56 €`
- A JPY price of `¥1,234.56` (with decimals) — JPY has no subunit
- Floating-point arithmetic on dollar values without integer cents

## Gotchas

- **Manual string concatenation is wrong for any non-US locale.** Always use `Intl.NumberFormat`.
- **Store money in the smallest unit.** Cents for USD, yen for JPY, fils for KWD. Avoids floating-point bugs.
- **Cache formatters.** `new Intl.NumberFormat()` is not free.
- **Test with non-US locales.** US format hides bugs; `de-DE` exposes them.
- **JPY has 0 fraction digits by default.** Override with `minimumFractionDigits` if needed.
- **RTL currency display needs `<bdi>`.** Without it, digits and symbols can reorder.
- **Formatted strings are not arithmetic-safe.** Never use them in calculations.

## Related

- `i18n/icu-message-format.md` — date/time formatting in user-facing strings
- `i18n/locale-negotiation.md` — choosing which locale to format for
- `i18n/timezone-iana-temporal-2026.md` — paired timezone handling

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- https://www.geeksforgeeks.org/javascript/javascript-intl-numberformat-constructor/
- https://coreui.io/answers/how-to-format-a-number-as-currency-in-javascript/
- https://developer.mozilla.org/de/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
- https://www.freecodecamp.org/news/how-to-format-number-as-currency-in-javascript-one-line-of-code/
