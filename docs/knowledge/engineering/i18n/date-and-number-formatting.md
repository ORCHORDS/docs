# date-and-number-formatting

**Issue:** `Intl.DateTimeFormat` + `Intl.NumberFormat` gotchas
**Date:** 2026-08-09
**Status:** documented

## Symptom
You render a date as `${new Date().toLocaleDateString()}`. The
output is the user's browser locale, not the page's locale. The
date format is inconsistent (some users see "8/9/2026", others
"2026-08-09", others "9/8/26" — different locales).

For numbers: `${count.toLocaleString()}` shows "1,000" in en-US
but "1.000" in de-DE. The decimal separator matters for
compliance (a bank balance of "1,000" in de-DE is 1, not 1000).

## Root cause
`Date.prototype.toLocaleDateString()` and
`Number.prototype.toLocaleString()` default to the **runtime
locale** (the JS engine's default, usually the OS locale), not
the **app locale** (the user's selected locale in your app).

**Source:** MDN — Intl:
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl

> "When no locale is specified, the default locale of the
> JavaScript runtime is used."

For SSR, this is the Node.js locale (usually `en-US`). For
client-side, it's the browser locale. For Workers (CF Workers),
it defaults to `en-US`. None of these match the app's locale
unless you explicitly pass it.

## Fix
Pass the app locale explicitly to `Intl.*`:

```ts
// Get the current user's locale from the i18n config
const locale = useLocale();  // 'en', 'zh-CN', 'ar-SA', etc.

// Date
const formattedDate = new Intl.DateTimeFormat(locale, {
  dateStyle: 'long',  // 'Aug 9, 2026' (en) / '9 août 2026' (fr) / '2026年8月9日' (ja)
  timeStyle: 'short',  // '8:00 PM' (en) / '20:00' (de)
  timeZone: user.timezone ?? 'UTC',  // user's local timezone, or UTC
}).format(new Date());

// Number
const formattedNumber = new Intl.NumberFormat(locale, {
  style: 'currency',
  currency: 'USD',  // or 'EUR', 'JPY', etc.
  currencyDisplay: 'symbol',  // '$100.00' vs '100.00 USD'
}).format(100);

// Percentage
const formattedPercent = new Intl.NumberFormat(locale, {
  style: 'percent',
  maximumFractionDigits: 2,
}).format(0.1234);  // '12.34%'
```

## Server-side (SSR) + client-side (CSR) parity

For Next.js with `next-intl`, use the `useFormatter` hook on
client + the formatter from `getRequestConfig` on server:

```ts
// Server component
import { getFormatter } from 'next-intl/server';
const format = await getFormatter();
return <p>{format.dateTime(date, { dateStyle: 'long' })}</p>;

// Client component
import { useFormatter } from 'next-intl';
const format = useFormatter();
return <p>{format.dateTime(date, { dateStyle: 'long' })}</p>;
```

The `format` object is locale-aware; both server and client
produce identical output for the same locale + options.

## Edge cases

### Calendar systems
Some locales use non-Gregorian calendars:
- `ar-SA`: Islamic (Hijri) calendar
- `th-TH`: Thai Buddhist calendar
- `fa-IR`: Persian (Solar Hijri) calendar

```ts
new Intl.DateTimeFormat('ar-SA', {
  calendar: 'islamic',
  year: 'numeric', month: 'long', day: 'numeric',
}).format(new Date());
// 'صفر 9, 1447 AH'
```

For 21+ social platforms, this is rarely needed (users expect
Gregorian), but financial/compliance apps may need it.

### Timezone
- `timeZone: 'UTC'` — display in UTC (default for servers)
- `timeZone: 'America/New_York'` — display in a specific zone
- `timeZone: user.timezone` — display in the user's zone (best UX)

For users across timezones, the date "August 9" can be different
in different zones. `new Date('2026-08-09T01:00:00Z')` is
"August 8" in America/Los_Angeles and "August 9" in Asia/Shanghai.
Passing `timeZone: 'Asia/Shanghai'` shows the Shanghai-local date.

### Currency display
- `currencyDisplay: 'symbol'` — `$100.00`
- `currencyDisplay: 'code'` — `USD 100.00`
- `currencyDisplay: 'name'` — `100.00 US dollars`

For multi-currency apps (e.g. crypto + fiat), use `code` to
disambiguate.

## Verification
- **Test:** `test/intl-format.test.ts > 20-locale formatting parity`
  — server and client produce identical output
- **Live:** 20-locale visual QA — date/number displays match
  user expectations
- **i18n lint:** No raw `toLocaleString()` or `toLocaleDateString()`
  calls (always use the i18n formatter)

## Gotchas
- **`Intl` polyfill is needed for legacy runtimes** (older
  Node.js, older browsers). Modern CF Workers + Next.js 14 have
  full Intl support out of the box.
- **The locale string is case-sensitive.** `'en-us'` ≠ `'en-US'`.
  Always use the canonical form from your i18n config.
- **The locale string is also dash-separated, not underscore.**
  `'en_US'` is POSIX; `'en-US'` is BCP 47. `Intl` accepts
  `'en_US'` in some browsers but not all. Use `'en-US'`.
- **For SSR, pass the locale from the request** (via middleware),
  not from `process.env`. The env doesn't know the user's
  preference.

## Related
- `locale-fallback-chain.md`
- `icu-plural-rules-20-locales.md`
- MDN Intl: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
