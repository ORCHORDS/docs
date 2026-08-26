# number-formatting-intl

**Issue:** Formatting numbers with Intl.NumberFormat for different locales
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Decimal separator, grouping separator, and digit shapes vary by locale. `1,234.56` (en-US) is `1.234,56` in German and uses Arabic-Indic digits in Arabic locales.

## Pattern / Solution
```js
const n = 1234567.89;

new Intl.NumberFormat('en-US').format(n); // '1,234,567.89'
new Intl.NumberFormat('de-DE').format(n); // '1.234.567,89'
new Intl.NumberFormat('ar-EG').format(n); // Arabic-Indic digits

// Force ASCII digits in Arabic
new Intl.NumberFormat('ar-EG', { numberingSystem: 'latn' }).format(n);

// Compact notation
new Intl.NumberFormat('en', { notation: 'compact', compactDisplay: 'short' }).format(n);
// -> '1.2M'
```

## Gotchas
- Swiss `de-CH` uses apostrophe as grouping separator
- Indian `en-IN` uses South Asian grouping: `12,34,567.89`
- `numberingSystem` requires feature detection; not universal

## Related
- `currency-formatting-patterns.md`
- `date-formatting-intl.md`
