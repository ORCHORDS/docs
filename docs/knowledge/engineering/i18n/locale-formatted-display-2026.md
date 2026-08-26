# locale-formatted-display-2026

**Issue:** A team localizes a checkout page. The team writes `'Total: $' + total.toFixed(2)`. The team ships to German users. German users see "Total: $1,234.56" instead of the expected "Gesamt: 1.234,56 $". The team learns that currency, numbers, dates, and lists are all locale-dependent, and concatenating them by hand is a bug in most of the world.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

`1,234.56` is `1.234,56` in German and `1 234 567,89` in French. `7/7/2026` is `7.7.2026` in German and `2026/7/7` in Japanese. Yen amounts have no decimal places. The same number renders differently in 5 real locales: en-US `1,234,567.89`, de-DE `1.234.567,89`, fr-FR `1 234 567,89`, de-CH `1'234'567.89`, en-IN `12,34,567.89`.

## Root cause

Locale-aware formatting is defined in the Unicode CLDR (Common Locale Data Repository) and shipped via the ECMAScript Internationalization API (`Intl`). Every modern browser and Node.js has CLDR data built in. Hand-rolled formatting ignores CLDR and produces locale-incorrect output.

## The 5 Intl APIs to use

1. **`Intl.NumberFormat(locale, options)`** - numbers, currency, percent, units, compact notation.
2. **`Intl.DateTimeFormat(locale, options)`** - dates, times, with IANA time zone support.
3. **`Intl.PluralRules(locale, options)`** - plural category selection (already covered in dedicated entry).
4. **`Intl.RelativeTimeFormat(locale, options)`** - "3 hours ago", "in 2 days".
5. **`Intl.ListFormat(locale, options)`** - "A, B, and C" vs "A, B und C" vs "A、B、C".

## The 6 currency rules

1. **Currency from transaction, formatting from user's locale.** A German user paying in USD sees "1.234,50 $".
2. **Never derive currency from UI language.**
3. **Use `style: 'currency'` always, not `'$' + price.toFixed(2)`.**
4. **`currencyDisplay: 'symbol' | 'code' | 'name' | 'narrowSymbol'`.** Default is symbol.
5. **`minimumFractionDigits` and `maximumFractionDigits`** for consistent decimal places.
6. **JPY, KRW have 0 decimals by CLDR default.** Don't force 2 decimals for these.

## The 5 date rules

1. **Store UTC in database.** Convert to user zone at display only.
2. **Use IANA time zone names** (`Europe/Warsaw`), not UTC offsets (`+01:00`).
3. **`Intl.DateTimeFormat().resolvedOptions().timeZone`** detects user zone on client.
4. **Pass locale AND time zone to `Intl.DateTimeFormat`.** Don't rely on host default for server-side.
5. **Test DST transitions** in your test matrix (US spring forward, EU fall back, southern hemisphere opposite).

## The 5 i18next integration patterns

i18next v21.3+ supports inline formatting in translation strings.

1. `{{val, number}}` for numbers.
2. `{{val, datetime}}` for dates.
3. `{{val, currency(USD)}}` for currency, with code in parentheses.
4. `{{val, relativetime}}` for "3 hours ago" style.
5. `{{val, list}}` for lists with locale-aware conjunction.

The library calls the matching `Intl` API with the active language, so output follows the locale automatically.

## The 5 anti-patterns

1. **Manual concatenation `'Total: $' + price`.** Breaks in any non-US locale.
2. **Storing locale-formatted strings in the database.** Always store canonical (number, date object), format at display.
3. **Hardcoding separator (`,` vs `.` or `,` vs ` `).** Use `Intl.NumberFormat` with the active locale.
4. **Using UTC offset instead of IANA name.** DST rules are zone-specific; offsets don't capture them.
5. **Formatting server-side without locale context.** If server formats dates/numbers, accept the user's locale as an explicit parameter.

## The 4-step adoption pattern

1. **Centralize in `utils/format.js`** with hooks for `useTranslation()`. Don't sprinkle `Intl.NumberFormat` calls everywhere.
2. **Use i18next format syntax** in translation strings: `{{val, currency(USD)}}`.
3. **Test matrix:** European locale with space separator, Eastern Arabic numerals locale (ar-EG), a date format-different locale (en-US vs pl-PL), a Japanese calendar locale if using Temporal.
4. **Currency code from transaction data**, not UI language. Pass it explicitly to `formatCurrency(value, currencyCode)`.

## Verification

The tell that locale formatting is right:

- Currency formatting uses `Intl.NumberFormat` with `style: 'currency'`
- Dates use `Intl.DateTimeFormat` with explicit IANA time zone
- Database stores UTC; conversion happens only at display
- Translation strings use `{{val, number}}` and `{{val, currency(USD)}}` syntax, not concatenation
- The team can name the 5 Intl APIs

The tell it isn't:

- `'Total: $' + price` anywhere in the codebase
- Stored date strings in the database
- Hardcoded `'en-US'` locale in `Intl.NumberFormat` calls
- Mixed currency logic and UI language

## Gotchas

- **Reduced-ICU Node.js builds** may fail for `Intl.DateTimeFormat` with full locale data. Use `full-icu` package or `--with-intl=full-icu`.
- **Yen formatting without decimals** is correct per CLDR; don't override.
- **Persian/Arabic locales** use Eastern Arabic numerals (٠١٢٣٤٥٦٧٨٩); the digit characters differ.
- **`Intl.NumberFormat` with `style: 'unit'`** for "5 kilometers" vs "3 miles" - locale decides singular/plural.
- **Server-side formatting for PDF/email**: pass locale and time zone as explicit parameters; never rely on server host defaults.

## Related

- `i18n/Intl-PluralRules-2026.md` - plural categories
- `i18n/number-currency-formatting-2026.md` - dedicated entry
- `i18n/timezone-iana-temporal-2026.md` - timezone handling
- `i18n/icu-messageformat2-2026.md` - i18next uses ICU MessageFormat

## Source URLs (verified 2026-08-10)

- https://www.locize.com/blog/i18n-formatting
- https://simplelocalize.io/blog/posts/handling-dates-times-numbers-localization/
- https://simplelocalize.io/blog/posts/number-formatting-in-javascript/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
- https://www.i18next.com/translation-function/formatting
