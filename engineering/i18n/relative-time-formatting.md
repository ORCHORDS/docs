# relative-time-formatting

**Issue:** Displaying relative time strings ("3 hours ago") in a locale-aware way
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hard-coded English "2 days ago" is not localizable. `Intl.RelativeTimeFormat` produces locale-correct output.

## Pattern / Solution
```js
const rtf = new Intl.RelativeTimeFormat('fr-FR', { numeric: 'auto' });

rtf.format(-1, 'day');   // -> 'hier'
rtf.format(-3, 'hour');  // -> 'il y a 3 heures'
rtf.format(2, 'week');   // -> 'dans 2 semaines'

function relativeTime(date, locale = navigator.language) {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const diffMs = date.getTime() - Date.now();
  const units = [
    ['year', 31_536_000_000], ['month', 2_592_000_000],
    ['week', 604_800_000], ['day', 86_400_000],
    ['hour', 3_600_000], ['minute', 60_000], ['second', 1_000],
  ];
  for (const [unit, ms] of units) {
    if (Math.abs(diffMs) >= ms) return rtf.format(Math.round(diffMs / ms), unit);
  }
  return rtf.format(0, 'second');
}
```

## Gotchas
- `numeric: 'always'` forces "1 day ago" instead of "yesterday"; use `'auto'` for natural language
- The API takes a numeric value + unit string, not a Date object directly
- Negative = past, positive = future

## Related
- `date-formatting-intl.md`
- `list-formatting-intl.md`
