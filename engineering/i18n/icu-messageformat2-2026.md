# icu-messageformat2-2026

**Issue:** A team localizes a product. They use ICU MessageFormat 1 (MF1) for plurals. They need a complex message combining gender + plural + number formatting. MF1 syntax is nested curly braces, error-prone, hard for translators. The team hears about MessageFormat 2 (MF2) but doesn't know when to migrate.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

MF1 is the de facto i18n message format. MF2 is the Unicode successor. As of May 2026, MF2 is spec-stable but adoption is early. Knowing when to stay on MF1 vs migrate to MF2 is a 2026 architectural decision.

## Root cause

MF2 was final-candidate in March 2025, refined in CLDR 47/48 (October 2025), spec-locked. TC39 `Intl.MessageFormat` proposal is at Stage 2 (blocked at 2.7; needs ~12 production users). FormatJS, Lingui, Tolgee, react-intl are still MF1. No major framework has defaulted to MF2 as of May 2026.

## The MF1 vs MF2 syntax difference

The clearest side-by-side is a plural message with interpolation.

```
# ICU MessageFormat 1
"items": "{count, plural, =0 {You have no items.} one {You have one item.} other {You have {count, number} items.}}"
```

The whole message is one curly-brace expression: variable, selector, and variants are all inline.

```
# MessageFormat 2
.input {$count :integer}
.match $count
0 {{You have no items.}}
one {{You have one item.}}
* {{You have {$count} items.}}
```

MF2 splits the message into three explicit parts: `.input` declarations, `.match` selector, and variants. `*` is the fallback (replaces MF1's `other`).

## When MF2 wins

MF2 is meaningfully cleaner for complex cases.

- **Multiple selectors per message** — gender + plural, plural + format
- **Message reuse** — `.local` declarations for inline sub-messages
- **Better error messages** — well-formed vs valid (syntax error vs data model error)
- **Bidi isolation built-in** — formatted messages are BiDi-isolated
- **Extension points** — users can supply new formatters and selectors

For a simple "You have N items" message, MF2 verbosity feels like overkill. For a "User X uploaded N photos to album Y" message with gender + plural + format, MF2 reads better.

## When to migrate (May 2026 guidance)

| Use case | Recommendation |
|---|---|
| New project, no MF1 debt | start with MF2, accept the rough edges |
| Existing project, simple messages (plural only) | stay on MF1; MF1 works |
| Existing project, complex messages (gender + plural + format) | consider MF2 migration; the verbosity pays off |
| Framework team (FormatJS, react-intl) | wait for the framework to default to MF2 |
| High-volume translation team | consider MF2; translator tooling is improving |

The locize blog (May 2026) consensus: "stay on MF1, watch the inflection signals, be ready to migrate when the ecosystem moves."

## The TC39 Intl.MessageFormat gate

The TC39 proposal is at Stage 2.7, blocked on adoption. To advance to Stage 3, ~12 organizations need to be using MF2 in production. As of May 2026, that bar hasn't been met.

- `i18next` removed legacy `interpolation.format` in v26 but kept MF1
- `FormatJS` / `react-intl` — still MF1
- `Lingui` — still MF1
- `Tolgee` — still MF1 in ICU docs
- `messageformat/messageformat` (npm package) — supports both MF1 and MF2 (technical preview)

## The MessageFormat 2 syntax elements

The MF2 working group designed 6 syntax elements that map to MF1 features.

| MF2 element | MF1 equivalent | Notes |
|---|---|---|
| `.input {$var :type}` | argument declaration | explicit type checking |
| `.local $var = {...}` | (no direct equivalent) | local bindings for sub-messages |
| `.match $var` | `{var, plural, ...}` / `{var, select, ...}` | explicit selector |
| variants (selector {pattern}) | inline variants | one per line, easier to read |
| `{$var}` placeholder | `{var}` | dollar prefix makes variables untranslatable |
| `{$var :function option=value}` | `{var, function, option}` | named options vs positional |

The dollar prefix and named options are the two biggest readability wins.

## The 5 anti-patterns (MF1 era)

1. **Nested curly braces 3+ levels deep.** MF1 syntax becomes unreadable beyond 2 levels. Consider MF2 or simplify the message.
2. **Position-based arguments.** Use named arguments in MF1 (`{name}` not `{0}`); MF2 forces this.
3. **String concatenation for plurals.** `"You have " + count + " items"` is the anti-pattern. Use MF1 or MF2 plural.
4. **Ignoring plural categories.** `if (count === 1)` only works for English. Use MF1 plural or `Intl.PluralRules`.
5. **Mixing MF1 and MF2 syntax.** They're not compatible. Pick one per message.

## The migration checklist (when you're ready)

1. Audit the message corpus. Identify the 20% of messages that are complex (gender + plural + format).
2. Pick a MF2 runtime. As of May 2026, options: `@messageformat/messageformat` (npm, MF1+MF2), `intl-messageformat` (planned MF2 support), custom ICU4J/ICU4C bindings.
3. Translate the complex messages first. MF2 syntax is easier for translators.
4. Keep MF1 for simple messages. The migration is gradual, not a big-bang.
5. Track the framework signals. When react-intl or FormatJS defaults to MF2, switch the default.

## Verification

The tell that MF1/MF2 is being used well:

- Plurals are in MF1 or MF2 syntax, not `if/else`
- Messages with gender + plural use MF2 or stay simple
- Translators can read the source syntax (named args, no nested braces 3+ deep)
- Plural categories are CLDR-backed (`Intl.PluralRules`), not English-only
- The runtime supports both MF1 and MF2 (for the migration period)

The tell it isn't:

- `if (count === 1) ... else ...` for plurals
- Position-based arguments (`{0}`, `{1}`) instead of named
- String concatenation for translatable messages
- Translators receive JSON with raw English

## Gotchas

- **MF2 is at Stage 2 in TC39**, not Stage 4. Native browser support is years away. Use a library.
- **MF2 syntax is stricter.** A well-formed MF2 message is also valid; a valid MF1 message may not be well-formed MF2. Use the validator.
- **The dollar prefix is mandatory in MF2.** `$count` not `count` inside placeholders.
- **Vertical bars are for literal strings with special chars.** `|2-digit|` is a literal "2-digit" string (with hyphen); vertical bars disambiguate.
- **Backslash escape is the same as MF1.** `\{` and `\}` escape literal braces.

## Related

- `i18n/icu-message-format.md` — MF1 deep dive
- `i18n/Intl-PluralRules-2026.md` — plural category API
- `i18n/cldr-data-2026.md` — CLDR data backing the plural rules
- `i18n/locale-negotiation.md` — locale fallback chain

## Source URLs (verified 2026-08-10)

- https://messageformat.unicode.org/
- https://unicode-org.github.io/icu/userguide/format_parse/messages/mf2.html
- https://github.com/unicode-org/message-format-wg/blob/main/spec/syntax.md
- https://github.com/messageformat/messageformat/releases — npm package releases
- https://www.locize.com/blog/messageformat-2-i18next — May 2026 state of migration
- https://blogs.igalia.com/compilers/2024/05/06/messageformat-2-0-a-new-standard-for-translatable-messages/
- https://github.com/tc39/proposal-intl-messageformat — TC39 proposal
- https://better-i18n.com/en/blog/icu-message-format/ — MF1 reference
