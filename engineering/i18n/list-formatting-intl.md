# list-formatting-intl

**Issue:** Joining arrays of strings into locale-correct lists
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manually joining with commas and "and" is wrong for many locales. Chinese uses different separators; Arabic positions conjunctions differently.

## Pattern / Solution
```js
const items = ['apples', 'bananas', 'oranges'];

new Intl.ListFormat('en').format(items);
// -> 'apples, bananas, and oranges'

new Intl.ListFormat('zh-CN').format(items);
// -> 'apples、bananas和oranges'

new Intl.ListFormat('de').format(items);
// -> 'apples, bananas und oranges'

// Disjunction
new Intl.ListFormat('en', { type: 'disjunction' }).format(items);
// -> 'apples, bananas, or oranges'

// Short style
new Intl.ListFormat('en', { style: 'short' }).format(items);
// -> 'apples, bananas, & oranges'
```

## Gotchas
- `type: 'unit'` is for quantity lists; use `'conjunction'` for normal lists
- Polyfill `@formatjs/intl-listformat` for legacy targets (landed 2020)
- The separator logic is locale-specific even for already-translated items

## Related
- `relative-time-formatting.md`
- `number-formatting-intl.md`
