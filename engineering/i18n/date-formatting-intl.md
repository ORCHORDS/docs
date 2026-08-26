# date-formatting-intl

**Issue:** Formatting dates with Intl.DateTimeFormat to respect locale conventions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hard-coded `MM/DD/YYYY` is wrong for most locales. `Intl.DateTimeFormat` produces locale-correct output without a library.

## Pattern / Solution
```js
const date = new Date('2026-08-11');

new Intl.DateTimeFormat('de-DE', { dateStyle: 'long' }).format(date);
// -> '11. August 2026'

new Intl.DateTimeFormat('ja-JP', { dateStyle: 'full' }).format(date);
// -> '2026年8月11日火曜日'

new Intl.DateTimeFormat('en-US', {
  weekday: 'long', year: 'numeric', month: 'short', day: 'numeric'
}).format(date);
// -> 'Tuesday, Aug 11, 2026'

// Reuse formatter for performance
const fmt = new Intl.DateTimeFormat(navigator.language, { dateStyle: 'medium' });
items.forEach(item => fmt.format(item.createdAt));
```

## Gotchas
- `dateStyle`/`timeStyle` are mutually exclusive with individual field options
- `calendar` option (e.g. `'buddhist'`, `'persian'`) changes the calendar system
- Node.js before v13 ships limited ICU data; use `full-icu` npm package

## Related
- `number-formatting-intl.md`
- `timezone-handling-intl.md`
- `relative-time-formatting.md`
