# icu-message-format

**Issue:** A UI string built with concatenation (`"You have " + count + " new messages"`) breaks in Russian (3 plural forms), Arabic (6 plural forms), and any language with gender inflection. Translator hands back three variants per screen; engineer hardcodes one.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The English text reads "You have 3 new messages." In Russian, that becomes three different noun forms depending on whether the count ends in 1, 2-4, or 5+. In Arabic there are six. Concatenation does not work for any language that inflects nouns, verbs, or adjectives based on quantity, gender, or grammatical role.

## Root cause

English has only two plural forms: singular and plural. Most other languages have more. CLDR (Common Locale Data Repository) defines six plural categories used across world languages:

| Category | Used by | English example |
|---|---|---|
| `zero` | Arabic, Latvian, Welsh | "0 items" (Arabic distinguishes) |
| `one` | English, French, German | "1 item" |
| `two` | Arabic, Hebrew, Slovenian | "2 items" |
| `few` | Russian, Polish, Czech | "2-4 items" |
| `many` | Russian, Polish, Arabic | "5-20 items" |
| `other` | All languages (required fallback) | "21+ items" |

Concatenation gives the translator one form. ICU MessageFormat gives them one form per plural category, with the runtime picking the right one.

## The MessageFormat syntax

ICU MessageFormat is the industry-standard translatable string syntax that adapts to language-specific grammar using CLDR rules.

The basic placeholders:

- **Variable** — `{name}` inserts the value of `name` directly. For user names, simple labels.
- **Plural** — `{count, plural, one {# item} other {# items}}` selects based on the count's CLDR plural category.
- **Select** — `{gender, select, female {She} male {He} other {They}}` chooses text based on a string value. Used for gender pronouns, role, status.
- **Selectordinal** — `{rank, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}` for ordinals.

The `other` branch is required in every `plural` and `select` expression. The ICU standard requires it; strict parsers reject strings without it.

The `#` token in a plural expression is replaced by the formatted count number. Exact-match overrides (`=0`, `=1`) take precedence over category matching and are useful for zero-state copy.

The `offset:N` modifier subtracts N from the count before CLDR rules apply. Use it for patterns like "You and N others liked this" without application-level arithmetic.

## The nesting pattern

For combined gender and plural, nest `select` outside `plural`:

```
{gender, select,
  female {{count, plural,
    one {She added # photo}
    other {She added # photos}
  }}
  male {{count, plural,
    one {He added # photo}
    other {He added # photos}
  }}
  other {{count, plural,
    one {They added # photo}
    other {They added # photos}
  }}
}
```

The evaluation order is outer-first: `gender` (select) then `count` (plural) then any inner format. Keep nesting to 2 levels where possible; deeper nesting is hard for translators to read.

## The two implementation styles

**Suffixed keys (i18next default).** One JSON key per plural category:

```json
{
  "item": "item",
  "item_one": "1 item",
  "item_other": "# items"
}
```

Simpler diffs; one string per form; native browser `Intl.PluralRules` picks the right key.

**ICU inline.** Single string with full syntax:

```json
{ "item": "{count, plural, one {# item} other {# items}}" }
```

Denser; familiar to teams coming from FormatJS / react-intl; one string to translate per concept.

Both styles resolve to the same CLDR categories. Pick one and stay consistent. Mixing both in the same project is a translation-quality disaster.

## The MessageFormat 2 (MF2) migration

The Unicode CLDR/ICU working group is replacing ICU MessageFormat with MessageFormat 2 (MF2), finalized as Final Candidate in 2025. MF2 expresses plurals through explicit `.match` selectors and handles gender-plus-plural more cleanly.

Adoption is still very early in 2026. Do not adopt MF2 as the default yet. Wait for library support (icu4x, intl-messageformat, FormatJS) to reach GA. Track the i18next-ICU MF2 migration notes for the state of the migration.

## The five best practices

1. **Always include the `other` fallback.** Strict parsers reject strings without it. Run time errors with cryptic stack traces are the result.
2. **Use `#` for the formatted number in plurals.** It picks up the locale's number formatting (commas, decimals) automatically.
3. **Test with multiple locales.** 0, 1, 2, 5, 11, 21 hit different plural rules. English only tests `one` and `other`; Arabic tests all six.
4. **Keep messages translatable.** Give translators the full sentence, not a string they have to recombine. Concatenation is the enemy.
5. **Don't hardcode number/date formats.** Let the locale's number formatting apply through `#` or explicit `Intl.NumberFormat` calls.

## Verification

The tell that ICU MessageFormat is working:

- All UI strings with dynamic values use MessageFormat, not concatenation
- Translators are given full sentences with plural/select structure
- The CI test suite runs the eval set against Arabic (6 plural categories) and Polish (4) — both pass
- The team can name the plural category of any number in any supported language

The tell it isn't:

- One engineer hardcoded "1 message" / "X messages" in English; the Russian translator filed a bug
- A string concatenation has more than two parts in the codebase
- Plural forms exist in only one language

## Gotchas

- **Don't nest more than 2-3 levels deep.** Translators cannot read deeper nesting reliably. Use suffixed keys if you have more.
- **`other` is required, not optional.** Strict parsers reject strings without it. Some lenient parsers fall back to `other` automatically; don't rely on that.
- **The `=` exact match takes precedence over category.** `{count, plural, =0 {No items} one {1 item} other {# items}}` correctly says "No items" for 0 even though 0 has the `other` category in English.
- **Concatenation is wrong for any inflecting language.** Build a MessageFormat string with the full sentence, not a Python f-string with conditional logic.
- **MF2 adoption is not yet mainstream.** Stick with ICU MessageFormat 1.0 in 2026. Reassess in 2027.

## Related

- `i18n/pseudo-localization.md` — testing i18n without real translations
- `i18n/rtl-bidi-handling.md` — direction-aware messages
- `i18n/locale-negotiation.md` — choosing which locale to format for

## Source URLs (verified 2026-08-10)

- https://crowdin.com/blog/icu-guide
- https://intlpull.com/icu-message-format
- https://better-i18n.com/en/blog/icu-message-format/
- https://icusyntax.com/guides/icu-messageformat-guide
- https://www.locize.com/blog/i18n-pluralization
