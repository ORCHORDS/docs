# feature-cookbook-localization

**Issue:** Localization — content, dates, currency, addresses
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app is in English. You add French. A user enters
their address: "123 Main St". The form expects "Numéro et
rue". The data is wrong. You add Japanese. The user's
name is in the wrong order (family name first). You
have to redesign the form for each locale.

## Root cause
**Localization is more than translation.** It's a
re-design of the UI for each locale's conventions.

**Source:** Various i18n guides.

## The "user input" pattern

For user input that's locale-specific:
- **Names:** Different orders (English: given + family;
  Japanese: family + given; Spanish: given + paternal +
  maternal)
- **Addresses:** Different formats (US: street, city,
  state, zip; Japan: postal code, prefecture, city, area)
- **Phone numbers:** Different formats
- **Dates:** Different formats (US: MM/DD/YYYY; EU:
  DD/MM/YYYY; ISO: YYYY-MM-DD)
- **Numbers:** Different separators (US: 1,234.56; EU:
  1.234,56)

For most apps, use a single format per locale.

## The "name" pattern

For names, store them in a single field:
```ts
interface User {
  fullName: string;  // Single field
  honorific?: string;  // Optional
}
```

Or use a structured field:
```ts
interface User {
  givenName: string;
  familyName: string;
  honorific?: string;
}
```

For some cultures (Japanese, Korean, Hungarian), the
family name is first.

## The "address" pattern

For addresses, use a single field or structured:
```ts
interface Address {
  street1: string;
  street2?: string;
  city: string;
  state?: string;  // For US
  postalCode: string;
  country: string;  // ISO 3166-1 alpha-2
}
```

Use the ISO country code; it's standard.

## The "phone number" pattern

For phone numbers, use libphonenumber:
```ts
import { parsePhoneNumber, isValidPhoneNumber } from 'libphonenumber-js';

const phone = parsePhoneNumber('+1 555 123 4567', 'US');
console.log(phone.formatInternational());  // "+1 555-123-4567"
console.log(phone.formatNational());  // "(555) 123-4567"
console.log(isValidPhoneNumber('+1 555 123 4567'));  // true
```

The library handles all the locale-specific formats.

## The "date" pattern

For dates, use `Intl.DateTimeFormat`:
```ts
const date = new Date('2026-08-09T14:30:00Z');
const formatted = new Intl.DateTimeFormat('en-US', { dateStyle: 'long' }).format(date);
// "August 9, 2026"

const formattedEs = new Intl.DateTimeFormat('es-ES', { dateStyle: 'long' }).format(date);
// "9 de agosto de 2026"
```

The date is formatted per the locale.

## The "time" pattern

For time, use `Intl.DateTimeFormat`:
```ts
const time = new Intl.DateTimeFormat('en-US', { timeStyle: 'short' }).format(date);
// "9:30 AM"

const time24 = new Intl.DateTimeFormat('en-GB', { timeStyle: 'short', hour12: false }).format(date);
// "09:30"
```

The time format depends on the locale (12h vs 24h).

## The "number" pattern

For numbers, use `Intl.NumberFormat`:
```ts
const number = 1234.56;

new Intl.NumberFormat('en-US').format(number);  // "1,234.56"
new Intl.NumberFormat('de-DE').format(number);  // "1.234,56"
new Intl.NumberFormat('fr-FR').format(number);  // "1 234,56"
new Intl.NumberFormat('ar-EG').format(number);  // "١٬٢٣٤٫٥٦"
```

The number format depends on the locale.

## The "currency" pattern

For currency, use `Intl.NumberFormat`:
```ts
const amount = 99.99;

new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
// "$99.99"

new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);
// "99,99 €"

new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(amount);
// "¥100"  (no decimals for JPY)
```

The currency is formatted per the locale.

## The "timezone" pattern

For timezones, use `Intl.DateTimeFormat` with `timeZone`:
```ts
const date = new Date('2026-08-09T14:30:00Z');
new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', timeStyle: 'short' }).format(date);
// "10:30 AM" (UTC-4 in summer)
new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Tokyo', timeStyle: 'short' }).format(date);
// "11:30 PM" (UTC+9)
```

The time is in the user's timezone.

## The "address format" pattern

For address display, format per locale:
```ts
function formatAddress(address: Address, locale: string): string {
  const country = getCountryFormat(address.country);
  return country.format(address);
}

function getCountryFormat(country: string): AddressFormatter {
  switch (country) {
    case 'US': return usFormat;
    case 'JP': return japanFormat;
    case 'DE': return germanyFormat;
    // ...
  }
}

function usFormat(a: Address): string {
  return `${a.street1}${a.street2 ? `, ${a.street2}` : ''}\n${a.city}, ${a.state} ${a.postalCode}\n${a.country}`;
}

function japanFormat(a: Address): string {
  return `〒${a.postalCode} ${a.state}${a.city}${a.street1}${a.street2 ? `, ${a.street2}` : ''}\n${a.country}`;
}
```

The address is formatted per the country.

## The "name order" pattern

For names, format per locale:
```ts
function formatName(name: Name, locale: string): string {
  switch (locale) {
    case 'ja-JP':
    case 'ko-KR':
    case 'hu-HU':
      return `${name.familyName} ${name.givenName}`;
    default:
      return `${name.givenName} ${name.familyName}`;
  }
}
```

The name is formatted per the locale.

## The "postal code" pattern

For postal codes, validate per country:
```ts
const POSTAL_CODE_PATTERNS: Record<string, RegExp> = {
  US: /^\d{5}(-\d{4})?$/,
  UK: /^[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}$/i,
  JP: /^\d{3}-?\d{4}$/,
  DE: /^\d{5}$/,
  // ...
};

function isValidPostalCode(code: string, country: string): boolean {
  return POSTAL_CODE_PATTERNS[country]?.test(code) ?? false;
}
```

The postal code is validated per country.

## The "VAT/tax" pattern

For VAT/tax IDs, validate per country:
```ts
function isValidVAT(vat: string, country: string): boolean {
  // Use a library (e.g. vat-validate)
  return validateVAT(vat, country);
}
```

The VAT is validated per country.

## The "language detection" pattern

For language detection:
```ts
function detectLocale(request: Request): string {
  // 1. User preference
  const cookie = parseCookie(request.headers.get('Cookie') ?? '');
  if (cookie.locale) return cookie.locale;

  // 2. Accept-Language
  const acceptLanguage = request.headers.get('Accept-Language') ?? 'en';
  const preferred = acceptLanguage.split(',')[0].split(';')[0].toLowerCase();
  const supported = ['en', 'es', 'fr', 'de', 'ja', 'ar', 'ru', 'zh-CN'];
  if (supported.includes(preferred)) return preferred;

  // 3. Default
  return 'en';
}
```

The locale is detected.

## The "locale fallback" pattern

For unsupported locales, fall back:
```ts
function getLocaleFamily(locale: string): string {
  // 'en-US' -> 'en'
  return locale.split('-')[0];
}

function getTranslation(locale: string, key: string): string {
  // Try 'en-US', then 'en', then 'en-XX'
  const family = getLocaleFamily(locale);
  return locales[locale]?.[key] ?? locales[family]?.[key] ?? locales.en[key] ?? key;
}
```

The fallback chain handles partial translations.

## Verification
- **Test:** Each locale has the right format
- **Test:** Names are formatted correctly
- **Test:** Dates are in the right timezone
- **Live:** User sees the right locale
- **Audit:** Annual review of localization

## Gotchas
- **The "no locale-specific design" anti-pattern.** Some
  locales need different layouts (RTL, longer text).
- **The "translation is enough" anti-pattern.** Translation
  is 10% of localization; date/number/currency is 90%.
- **The "single name field" anti-pattern.** For some
  cultures, given + family are separate.
- **The "no timezone" anti-pattern.** A date without
  timezone is ambiguous.
- **The "hard-coded format" anti-pattern.** A "MM/DD/YYYY"
  is wrong for most of the world.

## Related
- `feature-cookbook-i18n.md`
- `i18n/date-and-number-formatting.md`
- `i18n/icu-plural-rules-20-locales.md`
- `i18n/rtl-safe-component-patterns.md`
- `time-handling.md`
- `currency-handling.md` (later)
- libphonenumber: https://www.npmjs.com/package/libphonenumber-js
- Intl: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
