# Intl-PluralRules-2026

**Issue:** A team has English strings "1 item" and "2 items". They add Arabic, but Arabic needs 6 plural forms. Hand-coding if-else chains is brittle. A native API exists.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A team that hardcodes plural forms (or uses English-only rules) breaks in non-English locales. Russian needs three forms. Polish needs four. Arabic needs six. Hand-coding the rules is error-prone and misses languages.

## Root cause

`Intl.PluralRules` is the ECMA-402 native API for selecting the CLDR plural category (zero, one, two, few, many, other) for any number and locale. It has been Baseline Widely Available since 2022-03-19 and is supported in every modern browser and Node.js. No library required.

## The 5-line pattern

```javascript
const prEn = new Intl.PluralRules('en-US');
console.log(prEn.select(0));   // "other" — "0 items"
console.log(prEn.select(1));   // "one"   — "1 item"
console.log(prEn.select(2));   // "other" — "2 items"

const prAr = new Intl.PluralRules('ar-EG');
console.log(prAr.select(0));   // "zero"
console.log(prAr.select(1));   // "one"
console.log(prAr.select(2));   // "two"
console.log(prAr.select(10));  // "few"
console.log(prAr.select(100)); // "many"
```

`select(n)` returns the CLDR plural category. The team picks the right translation key by suffix or by ICU MessageFormat.

## The two implementation styles (with Intl.PluralRules)

**Style 1 — Suffixed keys (i18next default):**

```json
{
  "item": "item",
  "item_one": "1 item",
  "item_other": "# items"
}
```

```javascript
function t(key, count, locale) {
  const pr = new Intl.PluralRules(locale);
  const category = pr.select(count);
  return translations[locale][`${key}_${category}`].replace('#', count);
}
```

**Style 2 — ICU MessageFormat (intl-messageformat, FormatJS):**

```json
{ "item": "{count, plural, one {# item} other {# items}}" }
```

Both styles resolve to the same CLDR categories. i18next v4 is built directly on `Intl.PluralRules`. The choice is style preference; the underlying rules are identical.

## The 6 CLDR categories

| Category | Used by |
|---|---|
| `zero` | Arabic, Latvian, Welsh (exact 0) |
| `one` | English, French, German (singular) |
| `two` | Arabic, Hebrew, Slovenian (dual) |
| `few` | Russian, Polish, Czech (paucal) |
| `many` | Russian, Polish, Arabic (large quantity) |
| `other` | All languages (required fallback) |

Not every language uses every category. English uses only `one` and `other`. Polish uses `one`, `few`, `many`, `other`. Arabic uses all six. The browser knows.

## The selectRange pattern

For ranges (1-5 items), `selectRange` returns the right category for the locale's convention:

```javascript
const pr = new Intl.PluralRules('en');
pr.selectRange(1, 5);  // "other" — "1-5 items" in English
```

Some languages have specific range rules; CLDR documents them.

## The ordinal pattern

For ordinal numbers (1st, 2nd, 3rd, 11th, 21st, 101st, etc.):

```javascript
const pr = new Intl.PluralRules('en', { type: 'ordinal' });
console.log(pr.select(1));   // "one"   — "1st"
console.log(pr.select(2));   // "two"   — "2nd"
console.log(pr.select(3));   // "few"   — "3rd"
console.log(pr.select(11));  // "other" — "11th"
console.log(pr.select(21));  // "one"   — "21st"
```

English ordinals use `one` for 1, 21, 31; `two` for 2, 22, 32; `few` for 3, 23, 33; `other` for everything else.

## The Intl.PluralRules vs manual rules

```javascript
// ❌ Manual rules
function plural(n, locale) {
  if (locale === 'en') return n === 1 ? 'one' : 'other';
  if (locale === 'pl') return n === 1 ? 'one' : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'few' : 'many');
  // ... 50+ more lines for other languages
}

// ✅ Native API
const pr = new Intl.PluralRules(locale);
return pr.select(n);
```

The manual approach is wrong on edge cases (Russian 11, 12-14, 21, 22-24; Arabic 0, 1, 2, 3-10, 11-99, 100+). The native API uses CLDR data, which is updated regularly.

## The 5 best practices

1. **Always use the native API.** Don't hand-code CLDR rules.
2. **Cache PluralRules instances.** Creating them is not free; cache by locale.
3. **Test with edge cases.** 0, 1, 2, 5, 11, 21, 100, 101, 111.
4. **Use `selectRange` for ranges.** Some languages have specific range rules.
5. **Use the ordinal type for ordering.** "1st place" is not the same as "1 item."

## The runtime fallback

If the locale is not supported, the native API falls back to the runtime's default. A team that supports a non-default locale should check `supportedLocalesOf`:

```javascript
const supported = Intl.PluralRules.supportedLocalesOf(['ar-EG', 'xx']);
if (supported.length === 0) {
  // Locale not supported; fall back to default or English
}
```

## The verification

The tell that PluralRules is working:

- Every translation uses the native API; no hand-coded rules
- Edge cases (0, 1, 11, 21, 100) are tested in CI
- PluralRules instances are cached
- The translation for every locale includes the right plural forms
- A native speaker of Arabic or Polish can confirm the forms are correct

The tell it isn't:

- English-only plural rules
- Hardcoded "if (n === 1)" everywhere
- Russian 21 shows the "one" form (should be "many")
- Arabic 0 uses the "other" form (should be "zero")

## Gotchas

- **Don't hardcode the rules.** CLDR updates regularly; the API picks up the updates.
- **Cache the PluralRules object.** Per-locale instances are reusable.
- **Test with edge cases.** 0, 1, 2, 11, 21, 100, 101, 111 are the language-specific edge cases.
- **Use `selectRange` for ranges.** Some languages have range-specific rules.
- **Use the `ordinal` type for ordering.** "1st" is not "1."
- **Cache the translation lookup.** The lookup is more expensive than the API call.

## Related

- `i18n/icu-message-format.md` — the message format with plural support
- `i18n/pseudo-localization.md` — testing plurals in pseudo-locales
- `i18n/number-currency-formatting-2026.md` — number formatting pairs with plural selection

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- https://www.locize.com/blog/i18n-pluralization
- https://web-platform-dx.github.io/web-features-explorer/features/intl-plural-rules/
- https://www.smashingmagazine.com/2025/08/power-intl-api-guide-browser-native-internationalization/
- https://cldr.unicode.org/index/cldr-spec/plural-rules
