# Devanagari Hindi Locale Workers Intl Formatting
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker serving an Indian audience must render numbers, currency,
dates, and units in the `hi-IN` locale with correct Devanagari numerals, INR
currency symbol placement, and Hindi-language month/weekday names — without
bundling a large polyfill.

## Context

Cloudflare Workers v8 runtime ships full ICU data, so `Intl.NumberFormat`,
`Intl.DateTimeFormat`, and `Intl.PluralRules` work natively for `hi-IN`.
However, the locale can produce either **Devanagari** (०, १, २…) or **Latin**
(0, 1, 2…) digits depending on the `-u-nu-` Unicode extension. Mixing digit
systems in the same page confuses Hindi readers. Explicit number-system
selection via BCP 47 `u` extensions is the correct approach.

## Number System Selection: Devanagari vs Latin

By default `hi-IN` resolves to the `deva` (Devanagari) numeral system on V8
ICU. Verify explicitly rather than relying on defaults.

```typescript
// src/lib/hi-formatters.ts

/** Devanagari digits: ०१२३४५६७८९ */
export const hiDevaNum = new Intl.NumberFormat('hi-IN-u-nu-deva', {
  useGrouping: true,
});

/** Latin digits (for contexts like code, IDs, API values) */
export const hiLatnNum = new Intl.NumberFormat('hi-IN-u-nu-latn', {
  useGrouping: true,
});

/** Currency — INR with Devanagari digits */
export const hiCurrency = new Intl.NumberFormat('hi-IN-u-nu-deva', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Compact notation: १.२ करोड़ style */
export const hiCompact = new Intl.NumberFormat('hi-IN-u-nu-deva', {
  notation: 'compact',
  compactDisplay: 'short',
});

console.log(hiDevaNum.format(1234567));  // → "१२,३४,५६७"
console.log(hiCurrency.format(49999));   // → "₹४९,९९९.००"
console.log(hiCompact.format(12000000)); // → "१.२ क॰"
```

Note the **Indian grouping system** (lakh/crore: 2-2-3 groups from right) is
automatically applied when `hi-IN` is the locale — no manual configuration.

## Date and Era Formatting

`hi-IN` uses the Gregorian calendar (`gregory`) by default. Month and weekday
names are rendered in Hindi.

```typescript
// src/lib/hi-date.ts

/** Full Hindi date: रविवार, 23 अगस्त 2026 */
export const hiDateLong = new Intl.DateTimeFormat('hi-IN', {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  numberingSystem: 'deva', // explicit — same as -u-nu-deva
});

/** Short date with Devanagari digits: २३/०८/२०२६ */
export const hiDateShort = new Intl.DateTimeFormat('hi-IN-u-nu-deva', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

/** Relative time */
export const hiRelTime = new Intl.RelativeTimeFormat('hi-IN', {
  numeric: 'auto',
  style: 'long',
});

export function formatRelative(diffMs: number): string {
  const days = Math.round(diffMs / 86_400_000);
  if (Math.abs(days) < 1) {
    const hours = Math.round(diffMs / 3_600_000);
    return hiRelTime.format(hours, 'hour');
  }
  return hiRelTime.format(days, 'day');
}

// hiDateLong.format(new Date('2026-08-23')) → "रविवार, 23 अगस्त 2026"
// hiDateShort.format(new Date('2026-08-23')) → "२३/०८/२०२६"
// formatRelative(-172800000) → "२ दिन पहले"
```

## Locale Detection and Number-System Header Injection

At the edge, detect the user's preferred locale from `Accept-Language` and
inject a `nu` extension when the primary language is Hindi.

```typescript
// src/middleware/hi-locale.ts

export interface LocaleContext {
  locale: string;
  numberSystem: 'deva' | 'latn';
  rtl: boolean;
}

export function detectHindiContext(request: Request): LocaleContext {
  const accept = request.headers.get('Accept-Language') ?? '';
  const tags = accept
    .split(',')
    .map(t => t.trim().split(';')[0].trim().toLowerCase());

  const isHindi = tags.some(t => t === 'hi' || t.startsWith('hi-'));

  if (!isHindi) {
    return { locale: 'en-IN', numberSystem: 'latn', rtl: false };
  }

  // Honour explicit nu extension from the browser if present
  const raw = tags.find(t => t.startsWith('hi')) ?? 'hi-in';
  const hasDevaExt = raw.includes('nu-deva');
  const hasLatnExt = raw.includes('nu-latn');
  const numberSystem = hasLatnExt ? 'latn' : 'deva';

  const locale = hasDevaExt || hasLatnExt
    ? `hi-IN-u-nu-${numberSystem}`
    : 'hi-IN-u-nu-deva'; // default to Devanagari

  return { locale, numberSystem, rtl: false };
}

export default {
  async fetch(request: Request): Promise<Response> {
    const ctx = detectHindiContext(request);

    const num = new Intl.NumberFormat(ctx.locale, {
      style: 'currency',
      currency: 'INR',
    });

    const body = JSON.stringify({
      locale: ctx.locale,
      sample: num.format(1500),
    });

    return new Response(body, {
      headers: {
        'Content-Type': 'application/json',
        'Content-Language': 'hi-IN',
        'Vary': 'Accept-Language',
      },
    });
  },
};
```

## Plural Rules for Hindi

Hindi has only two ICU plural categories: `one` (1) and `other` (everything
else). Unlike English, the `one` form applies only to exactly 1.

```typescript
// src/lib/hi-plural.ts

const hiPlural = new Intl.PluralRules('hi-IN');

const messages: Record<string, string> = {
  one: '१ वस्तु',
  other: '{n} वस्तुएँ',
};

export function formatItemCount(n: number): string {
  const devaNum = new Intl.NumberFormat('hi-IN-u-nu-deva').format(n);
  const category = hiPlural.select(n); // 'one' | 'other'
  return messages[category].replace('{n}', devaNum);
}

// formatItemCount(1)  → "१ वस्तु"
// formatItemCount(5)  → "५ वस्तुएँ"
// formatItemCount(0)  → "० वस्तुएँ"
```

## Anti-patterns

- **Hardcoding `₹` and formatting manually** — use `Intl.NumberFormat` with
  `currency: 'INR'`; the symbol position (prefix vs suffix) is locale-governed.
- **Assuming Latin digits for `hi-IN`** — V8 ICU defaults vary by ICU version;
  always pin the number system with `-u-nu-deva` or `-u-nu-latn`.
- **Using `.toLocaleString('hi-IN')` in Workers without testing** — the Worker
  runtime's ICU version may differ from local Node; test in `wrangler dev` with
  `--experimental-local` or deploy to a staging zone.
- **Mixing grouping separators** — Hindi uses a comma but with 2-2-3 grouping
  (`12,34,567`). Do not apply `en-US` grouping manually.
- **Forgetting `Vary: Accept-Language`** — cached responses served to an `en-US`
  user will otherwise show Devanagari digits.

## Gotchas

- `Intl.NumberFormat('hi-IN').resolvedOptions().numberingSystem` returns `'deva'`
  on Workers v8 runtime but `'latn'` on some older Deno/Node versions.
- Compact notation (`notation: 'compact'`) for `hi-IN` generates "करोड़" (crore)
  and "लाख" (lakh) labels that do not appear in English compact notation.
- Hindi month names from `Intl.DateTimeFormat` do not include genitive forms
  (unlike Slavic locales); they are invariant.
- The locale tag `hi` without a region subtag defaults to `hi-IN` in ICU;
  specifying `hi-IN` explicitly is clearer.
- `Intl.RelativeTimeFormat` for `hi-IN` requires `numeric: 'auto'` to produce
  "कल" (yesterday/tomorrow) instead of "-1 दिन".

## Verification

```typescript
// test/hi-in.spec.ts
import { hiCurrency, hiDevaNum, formatItemCount } from '../src/lib/hi-formatters';

Deno.test('INR currency prefix and Devanagari digits', () => {
  const result = hiCurrency.format(49999.5);
  // Must start with ₹, contain Devanagari digits, use lakh grouping
  if (!result.startsWith('₹')) throw new Error(`Bad prefix: ${result}`);
  if (!/[०-९]/.test(result)) throw new Error(`No Devanagari digits: ${result}`);
  if (!result.includes('४९')) throw new Error(`Bad grouping: ${result}`);
});

Deno.test('lakh grouping 12,34,567', () => {
  const r = hiDevaNum.format(1234567);
  if (r !== '१२,३४,५६७') throw new Error(`Got: ${r}`);
});

Deno.test('plural one vs other', () => {
  if (formatItemCount(1) !== '१ वस्तु') throw new Error('one failed');
  if (!formatItemCount(2).includes('वस्तुएँ')) throw new Error('other failed');
});
```

Run with `wrangler dev --test-scheduled` or Vitest targeting the Workers runtime.

## Related

- `intl-api-workers-edge-formatting.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `number-system-locale-workers-d1.md`
- `locale-negotiation-accept-language.md`
- `indic-script-rendering.md`

## Sources

- MDN `Intl.NumberFormat` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- Unicode CLDR `hi` plural rules — https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
- BCP 47 Unicode extension `-u-nu-` — https://www.unicode.org/reports/tr35/#u_Extension
- CLDR Indian numbering system data — https://github.com/unicode-org/cldr/blob/main/common/main/hi.xml
- Cloudflare Workers Intl support — https://developers.cloudflare.com/workers/runtime-apis/web-standards/
