# Unicode CLDR — Plural Rules, Locale Data, Number Formatting, and MessageFormat 2.0

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application displays "1 items in cart" because the translation
system only handles singular and plural forms. A Russian user sees
grammatically incorrect strings because Russian requires four plural
categories (one, few, many, other) based on last-digit rules, not
just two. Your number formatting shows "1,234.56" to German users
who expect "1.234,56". After upgrading ICU, Ukrainian locale strings
unexpectedly changed because the fallback chain from Ukrainian to
Russian was removed in CLDR 46.

## Context

Unicode CLDR (Common Locale Data Repository) is the standard source
for locale data used by ICU, Java's `java.text`, JavaScript's
`Intl` API, and most i18n libraries. CLDR defines six plural
categories (zero, one, two, few, many, other) — no language uses
all six except Arabic. CLDR 46 (October 2024) aligned with Unicode
16.0 and changed the Ukrainian locale fallback chain. CLDR 47
(March 2025) was a closed data cycle focused on stabilizing
MessageFormat 2.0, which advanced to Stable status with three
default functions (`:string`, `:number`, `:integer`). Implementations
ship in ICU4J, ICU4C, and ICU4X.

## Plural rule categories

```
CLDR defines six plural categories:

  Category    Used by                     Example (English)
  ──────────────────────────────────────────────────────────
  zero        Arabic, Latvian             0 items
  one         Most languages              1 item
  two         Arabic, Welsh, Slovenian    2 items
  few         Slavic, Arabic, Celtic      3 items (Russian: 2-4)
  many        Slavic, Arabic              5 items (Russian: 5-20)
  other       ALL languages (required)    25 items (fallback)

  Language examples:
    English:   one, other               (2 categories)
    Russian:   one, few, many, other    (4 categories)
    Arabic:    zero, one, two, few, many, other  (6 categories)
    Japanese:  other                    (1 category — no plural)
    Polish:    one, few, many, other    (4 categories)
```

```javascript
// Intl.PluralRules — native browser/Node.js API
new Intl.PluralRules('en').select(1);   // "one"
new Intl.PluralRules('en').select(5);   // "other"
new Intl.PluralRules('ar').select(3);   // "few"
new Intl.PluralRules('ru').select(21);  // "one" (last digit rule)
new Intl.PluralRules('ru').select(2);   // "few"
new Intl.PluralRules('ru').select(5);   // "many"

// ICU MessageFormat with plural rules
import IntlMessageFormat from 'intl-messageformat';

const msg = new IntlMessageFormat(
  '{count, plural, one {# file} other {# files}}',
  'en'
);
msg.format({ count: 1 });  // "1 file"
msg.format({ count: 5 });  // "5 files"

// Russian plural example
const ruMsg = new IntlMessageFormat(
  '{count, plural, one {# файл} few {# файла} many {# файлов} other {# файлов}}',
  'ru'
);
ruMsg.format({ count: 1 });   // "1 файл"
ruMsg.format({ count: 3 });   // "3 файла"
ruMsg.format({ count: 5 });   // "5 файлов"
ruMsg.format({ count: 21 });  // "21 файл"
```

## CLDR 46 and 47 changes

```
CLDR 46 (October 2024):
  → Aligned with Unicode 16.0
  → Ukrainian (uk) no longer falls back to Russian (ru)
  → New numbering systems
  → New iso8601 calendar type
  → Chinese collation updates
  → Hour-cycle preferences for en_HK, en_MY, en_IL
  → Nigerian Pidgin and Tigrinya promoted to Modern coverage

CLDR 47 (March 2025) — closed data cycle:
  → MessageFormat 2.0 → Stable status
  → Three stable default functions: :string, :number, :integer
  → Number-format elements require explicit numberSystem attribute
  → RBNF spellout improved for Gujarati, Bulgarian, Catalan, etc.
  → Date/time: new "Time Precision" option on semantic skeletons
  → Afrikaans now prefers English over Dutch as fallback
  → 11 new English regional variants
  → tzdata updated to 2025a
```

## Number formatting

```javascript
// CLDR-based number formatting via Intl.NumberFormat
new Intl.NumberFormat('en-US').format(1234.56);
// "1,234.56"

new Intl.NumberFormat('de-DE').format(1234.56);
// "1.234,56"

new Intl.NumberFormat('fr-FR').format(1234.56);
// "1 234,56" (narrow no-break space as grouping)

// Currency formatting
new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD'
}).format(1234.56);
// "$1,234.56"

new Intl.NumberFormat('ja-JP', {
  style: 'currency', currency: 'JPY'
}).format(1234);
// "￥1,234"
```

## MessageFormat 2.0

```
MessageFormat 2.0 (Stable in CLDR 47):

  Stable default functions:
    :string   — string formatting
    :number   — number formatting with options
    :integer  — integer formatting

  Syntax (simplified):
    .local $count = {$n :integer}
    .match $count
    one   {{You have {$count} notification}}
    *     {{You have {$count} notifications}}

  Implementations:
    ICU4J (Java), ICU4C (C/C++), ICU4X (Rust/JS)

  Key change from MF1:
    → Explicit function annotations (:number, :string)
    → Consistent formatting across all message parts
    → Better error handling and fallback behavior
```

## Anti-patterns

- **Assuming plural is just singular/plural** — English-centric
  thinking. Many languages need `few`, `many`, and `zero` branches.
  Missing categories produce grammatically incorrect strings.
- **Hardcoding locale fallback chains** — CLDR revises fallbacks
  (e.g., Ukrainian no longer falls back to Russian in CLDR 46).
  Pinned fallback tables go stale silently.
- **Number formatting with string concatenation** — `"$" + amount`
  ignores currency symbol placement (prefix in English, suffix in
  French), grouping separators, and decimal conventions. Use
  `Intl.NumberFormat` with currency options.
- **Testing only with English** — English has the simplest plural
  rules. Test with Arabic (6 categories), Russian (4 categories),
  and Japanese (no plural) to catch missing branches.

## Gotchas

- **CLDR version pinning** — MessageFormat 2.0 syntax and
  `numberSystem` attribute requirements changed between CLDR 46
  and 47. Code relying on implicit defaults can break on ICU
  upgrades. Pin and test CLDR/ICU version transitions.
- **`other` is always required** — every plural rule set must
  include an `other` category as the fallback. Omitting it
  causes runtime errors in strict implementations.
- **Ordinal vs cardinal plurals** — `Intl.PluralRules` supports
  both (`type: 'ordinal'` for 1st/2nd/3rd). Using cardinal rules
  for ordinal formatting produces wrong suffixes.
- **CLDR 47 was a closed cycle** — mostly tooling and MessageFormat
  changes, not new locale data. Upgrading from 46 to 47 should
  not cause locale data regressions, but test MF2-dependent code.

## Verification

- Plural rules cover all CLDR categories for each supported locale.
- `other` category present in every plural selection.
- Number formatting uses `Intl.NumberFormat`, not string concatenation.
- Locale fallback chain tested after CLDR version upgrades.
- ICU/CLDR version pinned and upgrade impact tested before rollout.
- Russian, Arabic, and Japanese tested for plural rule correctness.

## Related

- `documentation/docs/policies/i18n/icu4x-rust-unicode-processing.md`
- `documentation/docs/policies/i18n/temporal-api-date-time-formatting.md`
- `documentation/docs/policies/i18n/internationalized-routing-url-localization.md`

## Source URLs (verified 2026-08-16)

- CLDR 47 Release Note — https://cldr.unicode.org/downloads/cldr-47
- CLDR 46 Release Note — https://cldr.unicode.org/downloads/cldr-46
- Unicode LDML TR35 Part 3: Numbers — https://www.unicode.org/reports/tr35/47/tr35-numbers.html
- CLDR Plural Rules 2026 Guide — https://intlpull.com/blog/cldr-plural-rules-complete-guide-2026
