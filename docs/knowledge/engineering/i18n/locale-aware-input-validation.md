# locale-aware-input-validation

**Issue:** Validating user input that varies in format by locale (dates, phone numbers, postal codes)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A date field validated as `MM/DD/YYYY` rejects valid dates entered in `DD.MM.YYYY` format. Phone number and postal code patterns differ radically between countries.

## Pattern / Solution
Date input -- use `<input type="date">` and let the browser handle locale formatting:
```html
<input type="date" value="2026-08-11" />  <!-- ISO 8601 value; browser shows locale format -->
```
Parse user-entered date strings with `Temporal` or a locale-aware library:
```js
import { parse } from '@internationalized/date';
const date = parse(userInput, 'de-DE'); // handles DD.MM.YYYY
```
Phone number validation with `libphonenumber-js`:
```js
import { parsePhoneNumber, isValidPhoneNumber } from 'libphonenumber-js';
isValidPhoneNumber('+1 (800) 555-1234', 'US'); // true
isValidPhoneNumber('06 12 34 56 78', 'FR');     // true
const parsed = parsePhoneNumber('08001234567', 'DE');
parsed.formatInternational(); // '+49 800 1234567'
```
Postal code patterns:
```js
const postalPatterns = {
  US: /^\d{5}(-\d{4})?$/,
  CA: /^[A-Z]\d[A-Z] \d[A-Z]\d$/,
  GB: /^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$/,
  DE: /^\d{5}$/,
};
function validatePostal(code, country) {
  return postalPatterns[country]?.test(code.trim().toUpperCase()) ?? true;
}
```

## Gotchas
- `<input type="number">` uses `.` as decimal; European users expect `,` -- use `type="text"` with `Intl.NumberFormat` parsing
- Never validate phone numbers with a simple regex; use `libphonenumber-js` or equivalent
- Address field order (street/city/state/zip) varies by country; avoid hard-coded form layouts

## Related
- `date-formatting-intl.md`
- `number-formatting-intl.md`
- `international-address-2026.md`
