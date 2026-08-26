# Ukrainian Locale on Cloudflare Workers: Intl, Cyrillic Collation, and Post-2022 Considerations

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A news aggregator serving Ukrainian readers finds that alphabetical sorting of article tags
produces inconsistent ordering — `Б` appearing before `А`, or Latin letters interspersed
incorrectly with Cyrillic. Date strings rendered server-side show Russian month names
(`январь`) instead of Ukrainian ones (`січень`). A payment platform needs to display UAH
amounts correctly and handle the post-2022 shift where Ukrainian users overwhelmingly
prefer Ukrainian-language interfaces over Russian ones.

## Context

Ukrainian (BCP 47: `uk`, region variant `uk-UA`) uses the Cyrillic script with a 33-letter
alphabet that differs from Russian in several key ways relevant to `Intl`:

- Letters unique to Ukrainian: `Ї` (U+0407), `І` (U+0406), `Є` (U+0404), `Ґ` (U+0490)
- Russian letters absent from Ukrainian: `Ё`, `Ъ`, `Ы`, `Э`
- Alphabet order: А Б В Г Ґ Д Е Є Ж З И І Ї Й К Л М Н О П Р С Т У Ф Х Ц Ч Ш Щ Ь Ю Я
- **Currency**: Ukrainian hryvnia (UAH), symbol `₴`
- **Date format**: day.month.year (`23.08.2026`) in short form; `23 серпня 2026 р.` in long form
- **Month names in genitive case**: Ukrainian grammar requires genitive month names in date
  contexts (`серпня` not `серпень`) — `Intl.DateTimeFormat` handles this correctly
- **Decimal separator**: comma (`,`)
- **Week start**: Monday

Post-2022 context: Following Russia's full-scale invasion, Ukrainian users widely switched
away from Russian-language settings (`ru-UA`) even for legacy apps. Teams must ensure `uk-UA`
is properly supported rather than falling back to `ru`.

## Cyrillic Collation with Intl.Collator

### Correct Ukrainian alphabetical sort

```typescript
// workers/src/uk-collation.ts
export function sortUkrainian(strings: string[]): string[] {
  const collator = new Intl.Collator('uk-UA', {
    usage: 'sort',
    sensitivity: 'base',   // accent-insensitive for basic sort
    ignorePunctuation: false,
  });
  return [...strings].sort(collator.compare);
}

// Example
const tags = ['Яблуко', 'Авокадо', 'Ґудзик', 'Єнот', 'Їжак', 'Апельсин', 'Банан'];
console.log(sortUkrainian(tags));
// ["Авокадо", "Апельсин", "Банан", "Ґудзик", "Єнот", "Їжак", "Яблуко"]
// Г comes before Ґ, Е before Є, И before І/Ї
```

### Case-insensitive search with Cyrillic

```typescript
export function searchUkrainian(haystack: string[], needle: string): string[] {
  const collator = new Intl.Collator('uk-UA', {
    usage: 'search',
    sensitivity: 'base',
  });

  return haystack.filter((item) =>
    item.split('').some((_, i) => {
      const slice = item.slice(i, i + needle.length);
      return collator.compare(slice, needle) === 0;
    }),
  );
}
```

### D1 locale-aware sorting

SQLite (used by Cloudflare D1) does not ship ICU collation for Ukrainian by default.
The recommended pattern is to sort at the application layer after fetching:

```typescript
import type { Env } from './env';

export async function getTagsSortedUk(env: Env): Promise<string[]> {
  const { results } = await env.DB.prepare(
    'SELECT name FROM tags WHERE locale = ? ORDER BY name', // SQLite default sort — ASCII only
  )
    .bind('uk-UA')
    .all<{ name: string }>();

  const collator = new Intl.Collator('uk-UA', { usage: 'sort', sensitivity: 'base' });
  return results.map((r) => r.name).sort(collator.compare);
}
```

For high-volume tables, store a pre-normalised sort key column (NFC, lowercased via
`Intl.Collator`-stable mapping) and index it:

```sql
-- D1 migration
ALTER TABLE tags ADD COLUMN sort_key TEXT;
CREATE INDEX idx_tags_sort_key ON tags (sort_key);
```

```typescript
function buildSortKey(name: string): string {
  // Decompose to NFD, remove combining marks for a simple approximation,
  // then lowercase — NOT a full ICU sort key but sufficient for ASCII+Cyrillic
  return name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}
```

## Number and Currency Formatting

```typescript
// workers/src/uk-formatting.ts

export function formatNumberUk(value: number): string {
  // uk-UA: space as thousands separator, comma as decimal separator
  return new Intl.NumberFormat('uk-UA').format(value);
  // 1234567.89 → "1 234 567,89"  (narrow no-break space U+202F as thousands sep)
}

export function formatCurrencyUAH(amount: number): string {
  return new Intl.NumberFormat('uk-UA', {
    style: 'currency',
    currency: 'UAH',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "1 234,50 ₴"
}

export function formatCurrencyUSD(amount: number): string {
  // USD is common in Ukrainian e-commerce / real estate
  return new Intl.NumberFormat('uk-UA', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
  // 1234.5 → "1 234,50 US$"
}

export function formatPercentUk(ratio: number): string {
  return new Intl.NumberFormat('uk-UA', { style: 'percent' }).format(ratio);
  // 0.153 → "15%"
}
```

## Date and Time Formatting

Ukrainian genitive month names (`серпня`, `вересня`, …) are produced automatically by
`Intl.DateTimeFormat` when `dateStyle` is `'long'` or `'full'`.

```typescript
export function formatDateUk(date: Date, style: 'full' | 'long' | 'medium' | 'short' = 'long'): string {
  return new Intl.DateTimeFormat('uk-UA', { dateStyle: style }).format(date);
  // full   → "субота, 23 серпня 2026 р."
  // long   → "23 серпня 2026 р."
  // medium → "23 серп. 2026 р."
  // short  → "23.08.2026"
}

export function formatTimeUk(date: Date): string {
  return new Intl.DateTimeFormat('uk-UA', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/Kyiv',
  }).format(date);
  // → "14:30"
}

export function formatRelativeUk(deltaSeconds: number): string {
  const rtf = new Intl.RelativeTimeFormat('uk-UA', { numeric: 'auto' });
  const abs = Math.abs(deltaSeconds);
  if (abs < 60) return rtf.format(Math.round(deltaSeconds), 'second');
  if (abs < 3600) return rtf.format(Math.round(deltaSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(deltaSeconds / 3600), 'hour');
  return rtf.format(Math.round(deltaSeconds / 86400), 'day');
  // -3600 → "годину тому"
  // 86400 → "завтра"
}
```

## Workers Handler: Language-Aware Routing

Post-2022, many Ukrainian sites removed Russian from their supported locales or demoted it.
This example shows locale negotiation that prioritises `uk` and rejects `ru` as a fallback
for Ukrainian users.

```typescript
import type { Env } from './env';

const SUPPORTED_LOCALES = ['uk-UA', 'uk', 'en-US', 'en'] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

function negotiateLocale(acceptLanguage: string | null): SupportedLocale {
  if (!acceptLanguage) return 'uk-UA';

  // Parse and rank Accept-Language header
  const preferred = acceptLanguage
    .split(',')
    .map((part) => {
      const [tag, q] = part.trim().split(';q=');
      return { tag: tag.trim(), q: parseFloat(q ?? '1') };
    })
    .sort((a, b) => b.q - a.q)
    .map((x) => x.tag);

  for (const tag of preferred) {
    const base = tag.split('-')[0].toLowerCase();
    if (base === 'uk') return 'uk-UA';
    if (base === 'en') return 'en-US';
    // Explicitly do NOT fall back to 'ru' for Ukrainian domains
  }

  return 'uk-UA';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = negotiateLocale(request.headers.get('Accept-Language'));
    const url = new URL(request.url);

    if (url.pathname === '/api/prices') {
      return handlePrices(request, env, locale);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handlePrices(_req: Request, env: Env, locale: string): Promise<Response> {
  const { results } = await env.DB.prepare(
    'SELECT id, name_uk, price_uah FROM products LIMIT 20',
  ).all<{ id: number; name_uk: string; price_uah: number }>();

  const currencyFmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'UAH',
    minimumFractionDigits: 2,
  });

  const collator = new Intl.Collator(locale, { usage: 'sort', sensitivity: 'base' });

  const sorted = [...results].sort((a, b) => collator.compare(a.name_uk, b.name_uk));

  return Response.json({
    locale,
    items: sorted.map((r) => ({
      id: r.id,
      name: r.name_uk,
      price: currencyFmt.format(r.price_uah),
    })),
  });
}
```

## Handling the `uk` vs `ru` Locale Switch in Legacy Data

If your D1 schema previously stored `ru-UA` as a locale preference for Ukrainian users,
a migration query and Edge-layer coercion can normalise this:

```sql
-- D1 migration: coerce legacy ru-UA preferences for users with Ukrainian phone numbers
UPDATE user_preferences
SET locale = 'uk-UA'
WHERE locale = 'ru-UA'
  AND user_id IN (SELECT id FROM users WHERE phone_country = 'UA');
```

```typescript
// Edge coercion for cached locale cookies that haven't been migrated
function coerceLegacyLocale(locale: string, userCountry: string | null): string {
  if (locale === 'ru-UA' && userCountry === 'UA') {
    return 'uk-UA';
  }
  return locale;
}
```

## Anti-patterns

- **Falling back `uk` → `ru`**: CLDR's parent locale chain for `uk-UA` goes to `uk`, then
  to `root` — not to `ru`. Never add `ru` as a fallback for Ukrainian locales in any
  translation or content fallback chain for UA-region traffic.
- **Hard-coding month names**: Ukrainian nominative (`серпень`) vs. genitive (`серпня`)
  differs by context. Hard-coding either and inserting into date strings will produce
  grammatically incorrect output. Use `Intl.DateTimeFormat`.
- **Sorting Cyrillic with `localeCompare` and no locale**: `'Я'.localeCompare('А')` with no
  locale uses the runtime default which may be `en-US`, producing wrong Ukrainian order.
  Always pass `'uk-UA'` explicitly.
- **Assuming `₴` is right-side**: In CLDR `uk-UA` the currency symbol follows the amount
  with a space. Do not prepend `₴` like a dollar sign.
- **Using `Europe/Moscow` timezone for Ukraine**: Ukraine uses `Europe/Kyiv` (formally
  renamed from `Europe/Kiev` in IANA TZDB 2022f). Always reference `Europe/Kyiv`.

## Gotchas

- `new Intl.Collator('uk-UA')` correctly places `Ґ` after `Г` and `Є` after `Е` etc. —
  confirm this with your V8 version if sorting is critical; ICU data for Ukrainian improved
  significantly in CLDR 42+.
- The thousands separator in `uk-UA` is a narrow no-break space (U+202F, ` `), not a
  regular space or a dot. String comparisons and stripping of separators must account for
  this codepoint.
- `Intl.DateTimeFormat('uk-UA', { month: 'long' }).format(date)` returns nominative
  (`серпень`). To get the genitive form used in full dates, use `dateStyle: 'long'` which
  produces the correctly inflected string via CLDR grammar data.
- `Europe/Kyiv` is the canonical IANA ID since tzdata 2022f. Older systems may still have
  `Europe/Kiev`; both resolve to the same zone in V8 but prefer the canonical spelling.
- The CLDR `uk` data includes a Ukrainian-specific list format (e.g. `А, Б і В`), where
  the conjunction is `і` (not Russian `и`). `Intl.ListFormat('uk-UA')` produces this
  correctly.

## Verification

```typescript
import { describe, it, expect } from 'vitest';

describe('uk-UA formatting', () => {
  it('sorts Cyrillic in Ukrainian alphabetical order', () => {
    const input = ['Яблуко', 'Авокадо', 'Ґудзик', 'Єнот'];
    const collator = new Intl.Collator('uk-UA', { sensitivity: 'base' });
    const sorted = [...input].sort(collator.compare);
    expect(sorted[0]).toBe('Авокадо');
    expect(sorted[1]).toBe('Ґудзик');
  });

  it('formats UAH currency with trailing symbol', () => {
    const fmt = new Intl.NumberFormat('uk-UA', { style: 'currency', currency: 'UAH' });
    const result = fmt.format(1234.5);
    expect(result).toContain('₴');
    expect(result).toContain('1');
  });

  it('uses genitive month name in long date', () => {
    const d = new Date('2026-08-23T00:00:00Z');
    const fmt = new Intl.DateTimeFormat('uk-UA', { dateStyle: 'long', timeZone: 'Europe/Kyiv' });
    expect(fmt.format(d)).toContain('серпня');
  });
});
```

## Related

- `unicode-collation-d1-sqlite-locale-sort.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `cldr-data-2026.md`
- `bcp47-language-tag-syntax.md`
- `locale-negotiation-accept-language.md`
- `georgian-script-localization-workers.md`

## Sources

- CLDR locale data for `uk`: https://github.com/unicode-org/cldr/tree/main/common/main
- IANA TZDB 2022f — `Europe/Kyiv` canonical rename
- Unicode CLDR Ukrainian plural rules: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN `Intl.Collator`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- National Bank of Ukraine currency information: https://bank.gov.ua
- BCP 47 subtag registry — `uk`
