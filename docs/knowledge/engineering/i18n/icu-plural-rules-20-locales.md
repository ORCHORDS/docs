# icu-plural-rules-20-locales

**Issue:** ICU plural forms differ wildly across locales
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write `{count, plural, =0 {no items} one {1 item} other {# items}}`.
In English, this is correct. In Russian, native speakers say
"1 товар", "2 товара", "5 товаров" — three distinct forms. In
Arabic, six. In Japanese, one (no plural at all). Your translation
round-trip fails the QA pass.

## Root cause
ICU plural categories per CLDR:
- **one** (1): English, German, Spanish, French, Italian, etc.
- **few** (2-4): Russian, Polish, Ukrainian, Czech, etc.
- **many** (5+ or 0/decimal): Russian (0/decimal), Polish (5+), Arabic
- **other** (catch-all): Japanese, Chinese, Korean, Vietnamese

**Source:** Unicode CLDR plural rules:
https://unicode.org/reports/tr35/tr35-numbers.html#Language_Plural_Rules

> "Different languages have different numbers of plural forms.
> English has two (one, other); Arabic has six (zero, one, two,
> few, many, other)."

## Fix
Use the full ICU plural categories. For 20-locale coverage,
you need at minimum: `one`, `few`, `many`, `other`.

```json
{
  "post_count": "{count, plural, =0 {No posts yet} one {1 post} few {# posts} many {# posts} other {# posts}}"
}
```

In `next-intl`, the ICU message is processed by the runtime; you
just need the right category names in the JSON. For a 20-locale
app, generate the keys for all 4 categories even if some locales
won't use them. The runtime ignores unused categories.

### Per-locale plural behavior

| Locale | 0 | 1 | 2 | 5 | 11 |
|---|---|---|---|---|---|
| en | other | one | other | other | other |
| ru | many | one | few | many | many |
| ar | zero | one | two | few | many |
| ja | other | other | other | other | other |
| zh | other | other | other | other | other |
| pl | many | one | few | many | many |

The categories are NOT "plural = 2". They are CLDR-defined
classes. Use the locale's CLDR plural rules (CLDR provides them as
XML/JSON, freely downloadable).

## Verification
- **Test:** `test/i18n-plural.test.ts > ICU plural for 20 locales`
  — for each locale, test 0, 1, 2, 5, 11, 21 items
- **Visual QA:** Screenshot the same post-list page in 20 locales;
  confirm grammatical correctness with native speaker review
- **Linguist review:** For high-stakes locales (ru, ar, pl, ja),
  have a native speaker review the plural strings

## Gotchas
- **The `=0` and `=1` explicit categories override `one`/`other`**
  for those exact values. Use them when the message is very
  different (e.g. "No posts" vs "0 posts").
- **`#` is the placeholder for the count value.** It's
  auto-formatted per the locale's number rules.
- **CLDR updates yearly.** New plural rules can be added. Pin
  your CLDR version in `package.json` (or whatever lib you use).
- **A few locales have non-intuitive "few" ranges.** For example,
  Polish `few` is 2-4, 22-24, 32-34 (not just 2-4). Trust CLDR,
  don't hardcode the ranges.
- **The ICU message syntax uses `{}` for placeholders.** If your
  translation tool exports literal `{}` in the JSON, the runtime
  will error. Escape as `\\{}` or use the tool's escape mode.

## Related
- `flat-dotted-vs-nested-keys.md`
- `brand-literals-stay-english.md`
- `data-i18n-marker-pattern.md`
- Unicode CLDR: https://unicode.org/reports/tr35/tr35-numbers.html
- ICU MessageFormat: https://messageformat.icu/
