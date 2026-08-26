# plural-rules-cldr

**Issue:** Understanding CLDR plural categories and applying correct rules per locale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
English has two plural forms (one/other) but Russian has four (one/few/many/other). Using only `one`/`other` produces ungrammatical strings for many languages.

## Pattern / Solution
CLDR defines six categories: `zero`, `one`, `two`, `few`, `many`, `other`.

| Locale | Categories used |
|--------|----------------|
| en     | one, other |
| ar     | zero, one, two, few, many, other |
| ru     | one, few, many, other |
| zh, ja | other (only) |

ICU syntax:
```
{count, plural,
  =0    {No items}
  one   {# item}
  few   {# items}
  many  {# items}
  other {# items}
}
```
JavaScript:
```js
const pr = new Intl.PluralRules('ru');
pr.select(1);  // 'one'
pr.select(11); // 'many'
pr.select(21); // 'one'
```

## Gotchas
- `=0` and `=1` are exact-match overrides that take priority over category rules
- Arabic `few` applies to 3-10; `many` applies to 11-99
- CLDR data updates each release; outdated libraries may have wrong rules

## Related
- `icu-message-format.md`
- `flutter-intl-arb.md`
- `ios-localizable-strings.md`
