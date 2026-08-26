# Polish Locale on Cloudflare Workers: Genitive Month Names, Declension, and Intl Calendar

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Polish e-commerce site renders dates as "23 sierpień 2026" (nominative) in product
listings, but Polish grammar requires the genitive "23 sierpnia 2026". A logistics dashboard
sorts Polish city names incorrectly because `Ł`, `Ś`, `Ź` are placed after Z instead of
being interleaved with their base Latin letters. A checkout page shows "1 produkty" (wrong
plural) instead of "1 produkt" (correct) because the developer applied a two-form plural
rule instead of Polish's complex three-form system.

## Context

Polish (BCP 47: `pl`, region `pl-PL`) is a West Slavic language with:

- **Script**: Latin with diacritical extensions: `Ą Ć Ę Ł Ń Ó Ś Ź Ż`
- **Plural categories (CLDR)**: four-form system —
  - `one`: exactly `1`
  - `few`: 2–4, 22–24, 32–34, … (integers ending in 2–4, except 12–14)
  - `many`: 0, 5–19, 20–21, 25–31, … (integers ending in 0, 5–9, or 11–14)
  - `other`: fractional numbers (1.5, 2.3 …)
- **Month names**: nominative (`styczeń`, `sierpień`) vs. genitive (`stycznia`, `sierpnia`) —
  date contexts in Polish require the genitive; `Intl.DateTimeFormat` handles this
  correctly when `dateStyle` is used
- **Currency**: Polish Złoty (PLN), symbol `zł` (follows amount with space: `123,00 zł`)
- **Decimal separator**: comma (`,`)
- **Thousands separator**: space (` `, narrow no-break in CLDR)
- **Date order**: day.month.year (`23.08.2026`)
- **Week start**: Monday

## Plural Rules: the Four-Form System

Polish has one of the most complex plural systems in common European languages.

```typescript
// workers/src/pl-plural.ts

export type PlPluralCategory = 'one' | 'few' | 'many' | 'other';

export function getPlPluralCategory(n: number): PlPluralCategory {
  // CLDR rule for pl (cardinal):
  // one:   n = 1                           @integer 1
  // few:   v = 0 and n % 10 = 2..4        @integer 2~4, 22~24, 32~34, …
  //        and n % 100 != 12..14
  // many:  v = 0 and                      @integer 0, 5~19, 100, 1000, …
  //        (n != 1 and n % 10 = 0..1)
  //        or n % 10 = 5..9
  //        or n % 100 = 12..14
  // other: (everything else — fractions)  @decimal 0.0~1.5, 10.0, …

  if (n % 1 !== 0) return 'other'; // fractional

  const mod10 = n % 10;
  const mod100 = n % 100;

  if (n === 1) return 'one';
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return 'few';
  if (
    mod10 === 0 ||
    mod10 === 1 ||
    (mod10 >= 5 && mod10 <= 9) ||
    (mod100 >= 12 && mod100 <= 14)
  ) return 'many';

  return 'other'; // shouldn't reach for integers, but satisfies TypeScript
}

// Verification against Intl.PluralRules:
const pr = new Intl.PluralRules('pl');
// pr.select(1)   → "one"
// pr.select(2)   → "few"
// pr.select(4)   → "few"
// pr.select(5)   → "many"
// pr.select(11)  → "many"
// pr.select(12)  → "many"
// pr.select(14)  → "many"
// pr.select(22)  → "few"
// pr.select(1.5) → "other"
```

### Pluralisation helper for Polish UI strings

```typescript
interface PlMessages {
  one:   string; // "1 produkt"
  few:   string; // "2–4 produkty"
  many:  string; // "5+ produktów"
  other: string; // "1.5 produktu" (fractions, rare in UI)
}

export function formatPlMessage(count: number, messages: PlMessages): string {
  const pr = new Intl.PluralRules('pl');
  const category = pr.select(count) as PlPluralCategory;
  const countDisplay = new Intl.NumberFormat('pl-PL').format(count);
  return messages[category].replace('{count}', countDisplay);
}

// Example:
// formatPlMessage(1,   { one: '{count} produkt', few: '{count} produkty', many: '{count} produktów', other: '{count} produktu' })
// → "1 produkt"
// formatPlMessage(3,   { … }) → "3 produkty"
// formatPlMessage(5,   { … }) → "5 produktów"
// formatPlMessage(22,  { … }) → "22 produkty"
// formatPlMessage(100, { … }) → "100 produktów"
```

## Genitive Month Names and Date Formatting

Polish dates in running text require the genitive case of month names:

| Nominative | Genitive   |
|------------|------------|
| styczeń    | stycznia   |
| luty       | lutego     |
| marzec     | marca      |
| kwiecień   | kwietnia   |
| maj        | maja       |
| czerwiec   | czerwca    |
| lipiec     | lipca      |
| sierpień   | sierpnia   |
| wrzesień   | września   |
| październik | października |
| listopad   | listopada  |
| grudzień   | grudnia    |

`Intl.DateTimeFormat` with `dateStyle: 'long'` or `dateStyle: 'full'` produces the correct
genitive form automatically via CLDR data:

```typescript
// workers/src/pl-dates.ts

export function formatDatePl(date: Date, style: 'full' | 'long' | 'medium' | 'short' = 'long'): string {
  return new Intl.DateTimeFormat('pl-PL', { dateStyle: style }).format(date);
  // full   → "sobota, 23 sierpnia 2026"   ← genitive "sierpnia" ✓
  // long   → "23 sierpnia 2026"           ← genitive ✓
  // medium → "23 sie 2026"
  // short  → "23.08.2026"
}

export function formatTimePl(date: Date): string {
  return new Intl.DateTimeFormat('pl-PL', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Europe/Warsaw',
  }).format(date);
  // → "14:30"
}

// WRONG — returns nominative, grammatically incorrect in date contexts:
function formatMonthNominativeWrong(date: Date): string {
  // Produces "sierpień" — nominative — NOT suitable for full date strings
  return new Intl.DateTimeFormat('pl-PL', { month: 'long' }).format(date);
}

// For standalone month display (picker headers), nominative is acceptable:
export function formatMonthStandaloneOk(date: Date): string {
  return new Intl.DateTimeFormat('pl-PL', { month: 'long' }).format(date);
  // "sierpień" — correct for a calendar header label
}
```

## Number and Currency Formatting

```typescript
// workers/src/pl-formatting.ts

export function formatNumberPl(value: number): string {
  // pl-PL: narrow no-break space thousands, comma decimal
  return new Intl.NumberFormat('pl-PL').format(value);
  // 1234567.89 → "1 234 567,89"
}

export function formatCurrencyPLN(amount: number): string {
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "1 234,50 zł"   (symbol after amount with space)
}

export function formatCurrencyEUR(amount: number): string {
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
  // 100 → "100,00 €"
}

export function formatPercentPl(ratio: number): string {
  return new Intl.NumberFormat('pl-PL', { style: 'percent' }).format(ratio);
  // 0.15 → "15%"
}
```

## Collation: Polish Diacritics Sort Order

Polish alphabet order: A Ą B C Ć D E Ę F G H I J K L Ł M N Ń O Ó P R S Ś T U W Y Z Ź Ż

Letters with diacritics sort immediately after their base letter, not after Z.

```typescript
// workers/src/pl-collation.ts

export function sortPolish(strings: string[]): string[] {
  const collator = new Intl.Collator('pl-PL', {
    usage: 'sort',
    sensitivity: 'variant', // distinguish Ą from A, Ó from O
  });
  return [...strings].sort(collator.compare);
}

// Example:
const cities = ['Łódź', 'Kraków', 'Warszawa', 'Ząbki', 'Śląsk', 'Częstochowa', 'Białystok'];
console.log(sortPolish(cities));
// ["Białystok", "Częstochowa", "Kraków", "Łódź", "Śląsk", "Warszawa", "Ząbki"]
// Ł after L, Ś after S, Ź/Ż after Z
```

### D1 sort key strategy

SQLite does not do Polish collation natively. Store a normalised sort key:

```sql
ALTER TABLE cities ADD COLUMN sort_key TEXT;
CREATE INDEX idx_cities_sort ON cities(sort_key);
```

```typescript
import { Env } from './env';

function buildPolishSortKey(text: string): string {
  // NFD decomposition removes combining diacritics for basic Latin sort;
  // does NOT correctly place Ą after A in all ICU senses, but is a reasonable
  // ASCII-sortable approximation. Replace with ICU sort key generation in
  // a build pipeline for production-grade correctness.
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

export async function insertCityWithSortKey(env: Env, name: string): Promise<void> {
  await env.DB.prepare('INSERT INTO cities (name, sort_key) VALUES (?, ?)')
    .bind(name, buildPolishSortKey(name))
    .run();
}

export async function getCitiesSorted(env: Env): Promise<string[]> {
  const { results } = await env.DB.prepare(
    'SELECT name FROM cities ORDER BY sort_key',
  ).all<{ name: string }>();

  // Re-sort in Workers with full ICU collator for exact Polish diacritic order
  const collator = new Intl.Collator('pl-PL', { sensitivity: 'variant' });
  return results.map((r) => r.name).sort(collator.compare);
}
```

## Workers Handler: Product Catalogue with Polish Localisation

```typescript
import type { Env } from './env';
import { formatCurrencyPLN, formatDatePl } from './pl-formatting';
import { formatPlMessage } from './pl-plural';

interface Product {
  id: string;
  name_pl: string;
  price_pln: number;
  stock: number;
  created_at: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/katalog') {
      const { results } = await env.DB.prepare(
        'SELECT id, name_pl, price_pln, stock, created_at FROM products ORDER BY name_pl LIMIT 20',
      ).all<Product>();

      const collator = new Intl.Collator('pl-PL', { sensitivity: 'variant' });
      const sorted = [...results].sort((a, b) => collator.compare(a.name_pl, b.name_pl));

      const totalStock = sorted.reduce((sum, p) => sum + p.stock, 0);
      const stockSummary = formatPlMessage(totalStock, {
        one: '{count} sztuka w magazynie',
        few: '{count} sztuki w magazynie',
        many: '{count} sztuk w magazynie',
        other: '{count} sztuki w magazynie',
      });

      return Response.json({
        locale: 'pl-PL',
        stockSummary,
        products: sorted.map((p) => ({
          id: p.id,
          name: p.name_pl,
          price: formatCurrencyPLN(p.price_pln),
          stock: formatPlMessage(p.stock, {
            one: '{count} szt.',
            few: '{count} szt.',
            many: '{count} szt.',
            other: '{count} szt.',
          }),
          added: formatDatePl(new Date(p.created_at), 'medium'),
        })),
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Anti-patterns

- **Using two-form plural (one/other) for Polish**: Copy-pasting English pluralisation
  logic produces `"5 produkty"` instead of `"5 produktów"`. Always use `Intl.PluralRules('pl')`
  which returns `'one' | 'few' | 'many' | 'other'`.
- **Using `{ month: 'long' }` for full date strings**: This returns the nominative form
  (`sierpień`). Polish date grammar requires the genitive (`sierpnia`) in "23 sierpnia 2026".
  Use `dateStyle: 'long'` or `dateStyle: 'full'` instead.
- **Hard-coding `zł` prefix**: In Polish CLDR data the currency symbol `zł` follows the
  number. Prepending it produces wrong output `"zł123,00"`.
- **Sorting Polish strings with default `localeCompare`**: Without `'pl-PL'`, `Ł` sorts
  after `Z`, `Ą` after `Z`, etc. Always pass locale to `Intl.Collator`.
- **Assuming 14 is "few"**: The range 12–14 belongs to `many` in Polish (`12 produktów`,
  `13 produktów`, `14 produktów`). The "few" exception for 12–14 is the most commonly
  missed edge case.

## Gotchas

- Polish `many` category includes `0` (`0 produktów`, not `0 produkty`).
- Fractions map to `other` in Polish: `1.5 produktu` — rarely seen in UI but required
  for completeness in translation files.
- The thousands separator is narrow no-break space (U+202F). String comparisons on
  formatted numbers must handle this codepoint when stripping formatting.
- `Europe/Warsaw` is the correct IANA timezone (Poland observes CET/CEST).
- `Intl.Collator('pl-PL', { sensitivity: 'base' })` treats `A` = `Ą` — useful for
  search but not for sort. Use `sensitivity: 'variant'` for alphabetical ordering.
- Month abbreviations in `pl-PL` medium date use a period: `23 sie 2026` — strip dots
  before storing month abbreviations for display comparisons.

## Verification

```typescript
import { describe, it, expect } from 'vitest';

describe('pl-PL plural rules', () => {
  const pr = new Intl.PluralRules('pl');

  it.each([
    [1,   'one'],
    [2,   'few'],
    [4,   'few'],
    [5,   'many'],
    [11,  'many'],
    [12,  'many'],
    [14,  'many'],
    [22,  'few'],
    [100, 'many'],
    [1.5, 'other'],
  ])('select(%i) → %s', (n, expected) => {
    expect(pr.select(n)).toBe(expected);
  });
});

describe('pl-PL date formatting', () => {
  const aug23 = new Date('2026-08-23T12:00:00Z');

  it('uses genitive month name in long dateStyle', () => {
    const fmt = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'long', timeZone: 'Europe/Warsaw' });
    expect(fmt.format(aug23)).toContain('sierpnia'); // genitive
  });

  it('uses nominative in standalone month', () => {
    const fmt = new Intl.DateTimeFormat('pl-PL', { month: 'long', timeZone: 'Europe/Warsaw' });
    expect(fmt.format(aug23)).toBe('sierpień'); // nominative
  });
});

describe('pl-PL currency', () => {
  it('places zł after the amount', () => {
    const fmt = new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'PLN' });
    const result = fmt.format(1234.5);
    const zlIndex = result.indexOf('zł');
    const numIndex = result.indexOf('1');
    expect(numIndex).toBeLessThan(zlIndex);
  });
});
```

## Related

- `Intl-PluralRules-2026.md`
- `icu-plural-rules-20-locales.md`
- `pluralization-edge-cases-arabic-slavic.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `czech-slovak-locale-workers-intl-declension.md` (if exists)
- `ukrainian-locale-workers-intl-cyrillic-collation.md`

## Sources

- CLDR plural rules for `pl`: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- CLDR locale data for `pl`: https://github.com/unicode-org/cldr/tree/main/common/main
- BCP 47 subtag registry — `pl`
- MDN `Intl.PluralRules`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- MDN `Intl.Collator`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- MDN `Intl.DateTimeFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- National Bank of Poland — PLN currency conventions: https://www.nbp.pl
