# Tagalog / Filipino Locale on Cloudflare Workers: Intl Plural Rules and Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A remittance app serving Filipino overseas workers (OFW) shows "1 items" instead of
"1 item" in English mode, and in Filipino mode always uses the plural form regardless of
count. A date formatted via `toLocaleDateString('fil')` returns an unexpected English-looking
string because the developer expected full Filipino month names. A UI showing `"may 0 na
mensahe"` vs `"may 1 na mensahe"` cannot agree on which plural form to use because the
team conflates the BCP 47 tags `fil`, `tl`, and `tgl`.

## Context

Filipino (BCP 47: `fil`, also `fil-PH`) is the standardised form of Tagalog and the
national language of the Philippines. Key `Intl` facts:

- **BCP 47 tag**: `fil` (Filipino) is the CLDR/BCP 47 preferred tag; `tl` (Tagalog) is a
  legacy ISO 639-1 code accepted by most runtimes but may have less complete CLDR data.
  Always use `fil` or `fil-PH` for new code.
- **Script**: Latin with diacritics (Filipino uses the Latin alphabet, no separate script
  subtag needed)
- **Plural rule (CLDR)**: Filipino has a **two-form** plural system but with an unusual rule:
  - **`one`**: applies to numbers whose integer part (and visible fraction digits) is 0 or 1
    — i.e. `0`, `1`, and decimal values like `0.5`, `1.4`
  - **`other`**: all other integers (`2`, `3`, …) and their decimal forms
  - This means Filipino treats `0` as grammatically singular (unlike English)
- **Currency**: Philippine Peso (PHP), symbol `₱`
- **Date format**: month/day/year in short (`8/23/2026`), long form uses English month names
  in everyday Filipino text (`Agosto 23, 2026`)
- **Week start**: Sunday
- **Number system**: Latin (`latn`)

Filipino is extensively code-switched with English; many UI strings mix Filipino and English
words. Translation memories must account for this.

## Plural Rules in Detail

```typescript
// workers/src/fil-plural.ts

// CLDR plural rule for 'fil':
// one: n = 0..1 or v != 0 @integer 0, 1 @decimal 0.0~1.5, 10.0, 100.0, 1000.0, …
// other: everything else

export type FilPluralCategory = 'one' | 'other';

export function getFilPluralCategory(n: number): FilPluralCategory {
  const intPart = Math.floor(Math.abs(n));
  const fracPart = n % 1; // non-zero if decimal

  if (intPart === 0 || intPart === 1 || fracPart !== 0) {
    return 'one';
  }
  return 'other';
}

// Verify against Intl.PluralRules
export function getFilPluralCategoryIntl(n: number): Intl.LDMLPluralRule {
  const pr = new Intl.PluralRules('fil');
  return pr.select(n);
}

// Quick smoke-test:
// getFilPluralCategoryIntl(0)   → "one"
// getFilPluralCategoryIntl(1)   → "one"
// getFilPluralCategoryIntl(2)   → "other"
// getFilPluralCategoryIntl(0.5) → "one"  ← note: 0 is "one" unlike English
// getFilPluralCategoryIntl(1.5) → "one"
// getFilPluralCategoryIntl(10)  → "other"
```

### Building a plural message helper

Filipino UI strings often follow the pattern `"may {count} na {noun}"` (there is/are N noun).

```typescript
interface FilMessages {
  one: string;   // template with {count}
  other: string; // template with {count}
}

export function formatFilMessage(count: number, messages: FilMessages): string {
  const category = getFilPluralCategoryIntl(count);
  const template = messages[category];
  const countDisplay = new Intl.NumberFormat('fil-PH').format(count);
  return template.replace('{count}', countDisplay);
}

// Usage:
// formatFilMessage(0, {
//   one:   'Walang mensahe',
//   other: 'May {count} na mensahe',
// })
// → "Walang mensahe"   (0 → category "one", but caller chose a special zero string)

// formatFilMessage(3, {
//   one:   'May {count} na mensahe',
//   other: 'May {count} na mensahe',
// })
// → "May 3 na mensahe"
```

### Ordinal plural rules

Filipino ordinals use the prefix `ika-` (shortened `ika`) and do not change by count:
`ika-1`, `ika-2`, `ika-10`. `Intl.PluralRules` ordinal categories for `fil` all resolve
to `other` — there is no distinct `one`/`two`/`few` ordinal form.

```typescript
const ordinalRules = new Intl.PluralRules('fil', { type: 'ordinal' });
console.log(ordinalRules.select(1));  // "other"
console.log(ordinalRules.select(2));  // "other"
console.log(ordinalRules.select(10)); // "other"

// Filipino ordinal display using ika- prefix:
export function formatFilOrdinal(n: number): string {
  return `ika-${n}`;
  // 1 → "ika-1", 23 → "ika-23"
}
```

## Number and Currency Formatting

```typescript
// workers/src/fil-formatting.ts

export function formatNumberFil(value: number): string {
  return new Intl.NumberFormat('fil-PH').format(value);
  // 1234567.89 → "1,234,567.89"  (en-style grouping — fil uses en separators)
}

export function formatCurrencyPHP(amount: number): string {
  return new Intl.NumberFormat('fil-PH', {
    style: 'currency',
    currency: 'PHP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "₱1,234.50"
}

export function formatCurrencyUSD(amount: number): string {
  // USD amounts common in OFW remittance context
  return new Intl.NumberFormat('fil-PH', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
  // 500 → "US$500.00"
}

export function formatPercentFil(ratio: number): string {
  return new Intl.NumberFormat('fil-PH', { style: 'percent' }).format(ratio);
  // 0.05 → "5%"
}
```

## Date and Time Formatting

Filipino CLDR date patterns default to English month names in most dateStyle modes —
this matches real-world Filipino usage where English month names are standard.

```typescript
export function formatDateFil(date: Date, style: 'full' | 'long' | 'medium' | 'short' = 'long'): string {
  return new Intl.DateTimeFormat('fil-PH', { dateStyle: style }).format(date);
  // full   → "Sabado, Agosto 23, 2026"
  // long   → "Agosto 23, 2026"
  // medium → "Ago 23, 2026"
  // short  → "8/23/26"   ← M/D/Y order (month first, like en-US)
}

export function formatTimeFil(date: Date): string {
  return new Intl.DateTimeFormat('fil-PH', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'Asia/Manila',
  }).format(date);
  // → "2:30 PM"  (12-hour with AM/PM — standard in Philippines)
}

export function formatRelativeFil(deltaSeconds: number): string {
  const rtf = new Intl.RelativeTimeFormat('fil', { numeric: 'auto' });
  const abs = Math.abs(deltaSeconds);
  if (abs < 60) return rtf.format(Math.round(deltaSeconds), 'second');
  if (abs < 3600) return rtf.format(Math.round(deltaSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(deltaSeconds / 3600), 'hour');
  return rtf.format(Math.round(deltaSeconds / 86400), 'day');
  // -60 → "isang minuto ang nakalipas"
  // 86400 → "bukas"
}
```

## Workers Handler: OFW Remittance Dashboard

```typescript
// workers/src/index.ts
import type { Env } from './env';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/api/transactions') {
      return handleTransactions(request, env);
    }
    return new Response('Not found', { status: 404 });
  },
};

interface Transaction {
  id: string;
  amount_php: number;
  sent_at: string; // ISO 8601
  status: 'pending' | 'completed' | 'failed';
}

async function handleTransactions(request: Request, env: Env): Promise<Response> {
  const lang = request.headers.get('Accept-Language') ?? 'fil-PH';
  const locale = lang.startsWith('fil') || lang.startsWith('tl') ? 'fil-PH' : 'en-PH';

  const { results } = await env.DB.prepare(
    'SELECT id, amount_php, sent_at, status FROM transactions ORDER BY sent_at DESC LIMIT 10',
  ).all<Transaction>();

  const currFmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'PHP',
    minimumFractionDigits: 2,
  });

  const dateFmt = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Manila',
  });

  const pluralRules = new Intl.PluralRules(locale);
  const totalCount = results.length;
  const pluralCat = pluralRules.select(totalCount);

  const summaryMessages: Record<Intl.LDMLPluralRule, string> = {
    one: `May ${totalCount} na transaksyon`,
    other: `May ${totalCount} na mga transaksyon`,
    zero: `Walang transaksyon`,
    two: `May ${totalCount} na transaksyon`,
    few: `May ${totalCount} na transaksyon`,
    many: `May ${totalCount} na transaksyon`,
  };

  return Response.json({
    locale,
    summary: summaryMessages[pluralCat],
    transactions: results.map((t) => ({
      id: t.id,
      amount: currFmt.format(t.amount_php),
      date: dateFmt.format(new Date(t.sent_at)),
      status: t.status,
    })),
  });
}
```

## ICU MessageFormat with Filipino Plurals

```typescript
// Using @messageformat/core or similar
import { MessageFormat } from '@messageformat/core';

const mf = new MessageFormat('fil');

const msg = mf.compile(
  '{count, plural, one {May # na mensahe} other {May # na mga mensahe}}',
);

console.log(msg({ count: 0 }));  // "May 0 na mensahe"   (0 = "one" in fil)
console.log(msg({ count: 1 }));  // "May 1 na mensahe"
console.log(msg({ count: 5 }));  // "May 5 na mga mensahe"
```

## Anti-patterns

- **Using `tl` instead of `fil`**: `tl` (Tagalog) and `fil` (Filipino) are separate CLDR
  locales with slightly different data coverage. `fil` has more complete CLDR support
  and is the correct tag for general Filipino UI. Do not mix them in the same app.
- **Treating Filipino `0` like English**: In `fil`, count `0` belongs to the `one` plural
  category. A message system that treats `0` as `other` (like English) will output
  `"May 0 na mga mensahe"` where grammar expects `"May 0 na mensahe"`.
- **Hard-coding month names in Filipino**: Filipino month names in everyday use are English
  loanwords (`Enero`, `Pebrero`, `Marso`…). Do not use Tagalog neologisms
  (`Enero`=`Enero`; some older sources list `Hunyo` for June but `Hunyo` is also now
  standard). Use `Intl.DateTimeFormat` to get CLDR-authoritative names.
- **Prefixing ₱ manually**: `Intl.NumberFormat('fil-PH', { style: 'currency', currency: 'PHP' })`
  prepends the `₱` symbol without space. Manual concatenation risks double-prefixing or
  wrong spacing.
- **12-hour vs 24-hour confusion**: The Philippines uses 12-hour time with AM/PM in everyday
  contexts. `hour12: true` is the appropriate default; 24-hour is used in formal/military
  contexts only.

## Gotchas

- `Intl.PluralRules('fil').select(0)` returns `"one"` — verify this in your test suite
  since it surprises developers from English-speaking backgrounds.
- The BCP 47 tag `fil` is not a 2-letter ISO 639-1 code; some older libraries only accept
  2-letter tags and silently fall back to a default locale. Test with those libraries
  explicitly.
- `Intl.DateTimeFormat('fil-PH', { month: 'long' })` returns English month names
  (`August`, `September`). The Filipino CLDR data for months in standalone `long` format
  is the Hispanised form (`Agosto`, `Setyembre`) — you get these via `dateStyle: 'long'`.
- `Intl.ListFormat('fil-PH', { style: 'long', type: 'conjunction' })` produces
  `"A, B, at C"` — the Filipino conjunction `at` replaces the English `and`.
- The timezone for the Philippines is a single zone: `Asia/Manila` (UTC+8, no DST).

## Verification

```typescript
import { describe, it, expect } from 'vitest';

describe('fil-PH plural rules', () => {
  const pr = new Intl.PluralRules('fil');

  it('treats 0 as "one"', () => {
    expect(pr.select(0)).toBe('one');
  });

  it('treats 1 as "one"', () => {
    expect(pr.select(1)).toBe('one');
  });

  it('treats 2 as "other"', () => {
    expect(pr.select(2)).toBe('other');
  });

  it('treats 0.5 as "one" (decimal)', () => {
    expect(pr.select(0.5)).toBe('one');
  });

  it('formats PHP currency with peso sign', () => {
    const fmt = new Intl.NumberFormat('fil-PH', { style: 'currency', currency: 'PHP' });
    expect(fmt.format(1234.5)).toContain('₱');
  });

  it('formats date with English month name', () => {
    const fmt = new Intl.DateTimeFormat('fil-PH', { dateStyle: 'long', timeZone: 'Asia/Manila' });
    expect(fmt.format(new Date('2026-08-23T00:00:00Z'))).toContain('Agosto');
  });
});
```

## Related

- `Intl-PluralRules-2026.md`
- `icu-plural-rules-20-locales.md`
- `welsh-maltese-pluralization-workers.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `date-time-timezone-workers-edge-formatting.md`
- `icu-messageformat-pluralization-complex-languages.md`

## Sources

- CLDR plural rules for `fil`: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- CLDR locale data for `fil`: https://github.com/unicode-org/cldr/tree/main/common/main
- BCP 47 subtag registry — `fil` (Filipino)
- MDN `Intl.PluralRules`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- Cloudflare Workers Intl API support: https://developers.cloudflare.com/workers/runtime-apis/
- Bangsamoro Autonomous Region — Philippine Standard Time (PST) is UTC+8 year-round
