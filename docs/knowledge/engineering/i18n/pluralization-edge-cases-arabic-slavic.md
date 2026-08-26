# pluralization-edge-cases-arabic-slavic

**Issue:** Teams writing `{count, plural, one {# item} other {# items}}`
ship to Arabic, Polish, Russian, Ukrainian, and Welsh users who see
grammatically wrong strings — Arabic shows the "other" form for 11
items instead of "many", Polish shows "1 elementów" instead of
"1 element", Welsh never uses its dual form. The strings pass English
QA and automated tests because the test suite only checks `1` and
`5`. Runtime crashes in Workers edge formatting occur when ICU
MessageFormat 2 (MF2) receives a plural selector that has no matching
variant and the fallback is absent.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
[ar] count=3  renders: "3 عناصر"  ✓
[ar] count=11 renders: "11 عناصر" ✗  should be "11 عنصرًا" (many form)
[pl] count=1  renders: "1 elementów" ✗  should be "1 element" (one form)
[ru] count=21 renders: "21 предметов" ✗ should be "21 предмет" (one form)
[cy] count=2  renders: "2 eitemau" ✗  should be "2 eitem" (two form)

ICU MF2 runtime error in Cloudflare Worker:
  Error: No variant found for selector value 'few' — message had only
  {one} and {other} variants
```

## Context

CLDR defines plural categories as abstract classifiers, not literal
counts. The category `one` in Russian applies to 1, 21, 31, 41 …
(n mod 10 = 1 AND n mod 100 ≠ 11) — not just the literal `1`. Most
ICU implementations return the `other` fallback silently when a
category is missing; MF2's stricter runtime throws instead. Workers
running at the edge with no fallback message cause a 500 rather than
a graceful degraded string.

## CLDR plural category reference

| Language  | zero | one | two | few          | many           | other    |
|-----------|------|-----|-----|--------------|----------------|----------|
| Arabic ar |  0   |  1  |  2  | 3-10,103-110 | 11-26,111-126  | decimals |
| Polish pl |  —   |  1  | —   | 2-4,22-24… | 5-21,25-31…    | decimals |
| Russian ru|  —   |  1,21…| —  | 2-4,22-24… | 5-20,25-30…    | decimals |
| Ukrainian | —    | 1,21… | — | 2-4,22-24… | 5-20,25-30…    | decimals |
| Welsh cy  |  0   |  1  |  2  | 3            | 6              | other    |
| English en|  —   |  1  | —   | —            | —              | other    |

"—" means the category is not used in CLDR for that language.
The `few` and `many` rows are simplified — always use CLDR's formal
plural rules, not these summaries, when generating message catalogs.

## Arabic: 6 forms

Arabic has 6 mandatory plural categories. The `two` form uses a
grammatical dual suffix distinct from the numeric "2 things" form.

```json
// messages/ar.json  — ICU MessageFormat 1 syntax
{
  "item_count": "{count, plural,
    =0     {لا عناصر}
    one    {عنصر واحد}
    two    {عنصران}
    few    {{count} عناصر}
    many   {{count} عنصرًا}
    other  {{count} عنصر}
  }"
}
```

```json
// messages/ar.json  — ICU MessageFormat 2 syntax (MF2)
{
  "item_count": ".input {$count :integer}
    .match $count
    0   {{لا عناصر}}
    one {{عنصر واحد}}
    two {{عنصران}}
    few {{{$count} عناصر}}
    many {{{$count} عنصرًا}}
    *   {{{$count} عنصر}}"
}
```

In MF2, `*` is the required catch-all variant; it maps to the CLDR
`other` category. The `=0` explicit match from MF1 is replaced by a
`0` literal selector in MF2.

Critical Arabic numbers to test:

| n   | CLDR category | Expected suffix pattern |
|-----|---------------|-------------------------|
| 0   | zero          | لا عناصر                |
| 1   | one           | عنصر واحد               |
| 2   | two           | عنصران                  |
| 3   | few           | 3 عناصر                 |
| 11  | many          | 11 عنصرًا               |
| 100 | other         | 100 عنصر                |
| 103 | few           | 103 عناصر               |

## Polish, Russian, Ukrainian: 3 forms with counter-intuitive ranges

Polish, Russian, and Ukrainian share the same three-form structure
but their `few`/`many` boundary differs for numbers ending in 11-14.

```
Polish few:  n mod 10 ∈ {2,3,4} AND n mod 100 ∉ {12,13,14}
Polish many: n mod 10 ∈ {0,1,5,6,7,8,9} OR n mod 100 ∈ {11-14}
             also: decimals use 'many'

Russian one:  n mod 10 = 1  AND n mod 100 ≠ 11
Russian few:  n mod 10 ∈ {2,3,4} AND n mod 100 ∉ {12,13,14}
Russian many: everything else (includes 11-20, decimals, 0)
```

```json
// messages/pl.json
{
  "days_count": "{count, plural,
    one   {{count} dzień}
    few   {{count} dni}
    many  {{count} dni}
    other {{count} dnia}
  }"
}
```

Note that Polish `few` and `many` often use the same surface form
("dni") but must be listed separately because some nouns differ
between the categories. Never collapse them to avoid QA surprises
when translators provide distinct forms later.

Test matrix for Polish / Russian:

| n    | PL cat | RU cat | Example PL      | Example RU          |
|------|--------|--------|-----------------|---------------------|
| 1    | one    | one    | 1 dzień         | 1 предмет           |
| 2    | few    | few    | 2 dni           | 2 предмета          |
| 5    | many   | many   | 5 dni           | 5 предметов         |
| 11   | many   | many   | 11 dni          | 11 предметов        |
| 12   | many   | many   | 12 dni          | 12 предметов        |
| 21   | one    | one    | 21 dzień        | 21 предмет          |
| 22   | few    | few    | 22 dni          | 22 предмета         |
| 1.5  | other  | many   | 1,5 dnia        | 1,5 предмета        |

## Welsh: 6 forms with an unexpected `few=3`

Welsh is unusual in that `few` applies only to the literal number 3,
and `many` applies only to 6. This makes Welsh feel arbitrary unless
you know the CLDR rule:

```
cy zero:  n = 0
cy one:   n = 1
cy two:   n = 2
cy few:   n = 3
cy many:  n = 6
cy other: everything else
```

```json
// messages/cy.json
{
  "item_count": "{count, plural,
    =0  {Dim eitemau}
    one {1 eitem}
    two {2 eitem}
    few {3 eitem}
    many {6 eitem}
    other {{count} eitem}
  }"
}
```

Welsh `two` and `few` do not inflect the noun in the same way as
Slavic plurals — the number is repeated in the string to avoid
ambiguity. Check with a native Welsh speaker before using abbreviated
forms.

## Workers edge formatting with Intl.PluralRules

When formatting plurals at the Workers edge without ICU libraries,
`Intl.PluralRules` is available and agrees with CLDR:

```ts
// src/lib/plural.ts — runs in Cloudflare Workers
export function selectPlural(
  locale: string,
  count: number,
  forms: Record<string, string>,
): string {
  const pr = new Intl.PluralRules(locale, { type: "cardinal" });
  const category = pr.select(count);

  // MF2-style: check explicit value first, then category, then '*'
  const key = String(count);
  return forms[key] ?? forms[category] ?? forms["*"] ?? forms["other"] ?? "";
}

// Usage
const result = selectPlural("ar", 11, {
  "0": "لا عناصر",
  "one": "عنصر واحد",
  "two": "عنصران",
  "few": "{n} عناصر",
  "many": "{n} عنصرًا",
  "*": "{n} عنصر",
}).replace("{n}", String(11));
// → "11 عنصرًا"
```

`Intl.PluralRules` in the V8 runtime used by Workers matches CLDR
2025 data as of `compatibility_date = "2024-04-04"`. Older
compatibility dates may use V8 versions with CLDR 42 or earlier;
verify with `new Intl.PluralRules('ar').select(11)` === `"many"`.

## Mobile font rendering of pluralized strings

Arabic plural forms with dual suffix (`ان`) and genitive suffix
(`ًا`) require the font to support Arabic ligatures. On Android,
the default system font (Noto Naskh Arabic) renders these correctly.
On iOS, San Francisco does not include Arabic; the OS falls back to
Geeza Pro, which also renders correctly. Issues arise with:

- **Web fonts subset for Latin only** — if the project uses a custom
  web font subset that excludes Arabic Unicode ranges (U+0600–U+06FF),
  the harakat (short vowel marks) in plural suffixes fall back to a
  system font mid-word, causing visual inconsistency.
- **Variable fonts on Android <12** — Arabic variable fonts may
  render the grammatical `tatweel` (U+0640) incorrectly; use static
  weight variants for Arabic strings on mobile web.
- **Welsh `ll` and `ch` digraphs** — Welsh uses its own collation
  order but does not require special font support; no mobile font
  rendering issues are known.

## Anti-patterns

- **Writing `=1` instead of `one`** — `=1` is an exact value match;
  `one` is the CLDR category. For Russian and Polish, `one` matches
  1, 21, 31, …; `=1` only matches the literal integer 1.
- **Omitting the `other` / `*` fallback** — MF1 silently returns
  the key name; MF2 throws a runtime error. Always include `other`
  or `*` to guard against locales and CLDR updates you haven't
  anticipated.
- **Testing only `0`, `1`, `5`** — misses the 11-19 "teen exception"
  in all Slavic languages and the 103-110 range in Arabic.
- **Hardcoding plural logic** (`if count === 1`) — locale-specific
  plural math never belongs in application code; delegate to
  `Intl.PluralRules` or an ICU library.
- **Using the same string for `few` and `many` in Polish** — while
  the surface form is often identical today, collapsing the categories
  means translators cannot provide distinct forms in the TMS without a
  code change.

## Gotchas

- `Intl.PluralRules('uk')` (Ukrainian) is supported in Node 20+ and
  modern browsers, but the locale code must be `uk`, not `ua` — the
  latter is the country code, not the BCP 47 language tag.
- MF2 selectors match the string `"*"` as the catch-all; some TMS
  systems export `other` as the default key instead. Map `other` →
  `*` if the MF2 runtime you use requires `*`.
- CLDR updates the Welsh plural rule occasionally; the "few=3, many=6"
  pattern is documented in CLDR 45 (2024) but has changed in the past.
  Pin the CLDR version used by your ICU library and review Welsh on
  every CLDR major release.
- Decimal counts (`1.5`, `2.0`) use different CLDR categories than
  integers in several locales; for Arabic, `1.5` is `other`, not
  `one`. Always pass the count as a number, not a pre-formatted string,
  to `Intl.PluralRules`.

## Verification

```ts
// test/plural-rules.test.ts
import { describe, it, expect } from "vitest";

const cases: [string, number, string][] = [
  // [locale, n, expected CLDR category]
  ["ar", 0,   "zero"],
  ["ar", 1,   "one"],
  ["ar", 2,   "two"],
  ["ar", 3,   "few"],
  ["ar", 11,  "many"],
  ["ar", 100, "other"],
  ["ar", 103, "few"],
  ["pl", 1,   "one"],
  ["pl", 2,   "few"],
  ["pl", 5,   "many"],
  ["pl", 11,  "many"],
  ["pl", 21,  "one"],
  ["ru", 1,   "one"],
  ["ru", 11,  "many"],
  ["ru", 21,  "one"],
  ["uk", 2,   "few"],
  ["uk", 11,  "many"],
  ["cy", 2,   "two"],
  ["cy", 3,   "few"],
  ["cy", 6,   "many"],
];

describe("Intl.PluralRules CLDR categories", () => {
  it.each(cases)("%s n=%i → %s", (locale, n, expected) => {
    const pr = new Intl.PluralRules(locale, { type: "cardinal" });
    expect(pr.select(n)).toBe(expected);
  });
});
```

Run with native speaker review for Arabic (ar) and Welsh (cy) before
shipping; automated tests verify category selection, not translation
quality.

## Related

- `documentation/docs/policies/i18n/icu-plural-rules-20-locales.md`
- `documentation/docs/policies/i18n/icu-messageformat2-2026.md`
- `documentation/docs/policies/i18n/arabic-persian-text-rendering.md`
- `documentation/docs/policies/i18n/multilingual-font-loading-subsetting.md`
- `documentation/docs/policies/devtools/typescript-cloudflare-workers-strict.md`

## Sources

- https://unicode.org/reports/tr35/tr35-numbers.html#Language_Plural_Rules
- https://cldr.unicode.org/index/cldr-spec/plural-rules
- https://messageformat.dev/docs/
- https://tc39.es/ecma402/#pluralrules-objects
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/
