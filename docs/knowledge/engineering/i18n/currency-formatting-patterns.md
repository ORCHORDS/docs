# currency-formatting-patterns

**Issue:** Displaying monetary amounts correctly across locales and currencies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Currency symbol position, decimal places, and spacing rules differ per locale. `$100.00` is correct for en-US but `100,00 EUR` for fr-FR.

## Pattern / Solution
```js
const amount = 1234.5;

new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
// -> '$1,234.50'

new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(amount);
// -> '1 234,50 EUR'

new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(1235);
// -> 'JPY1,235'  (no decimal places)

// Accounting style (negatives in parens)
new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', currencySign: 'accounting'
}).format(-amount);
// -> '($1,234.50)'
```

## Gotchas
- Never store display-formatted strings in DB; store raw numeric + currency code
- KWD and BHD have 3 decimal places; do not assume 2
- JPY, KRW, VND have 0 decimal places; Intl handles automatically

## Related
- `number-formatting-intl.md`
- `locale-specific-images.md`
