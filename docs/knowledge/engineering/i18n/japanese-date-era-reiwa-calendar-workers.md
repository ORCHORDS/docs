# Japanese Date Era Reiwa Calendar Workers
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker serving a Japanese audience must display dates in the
Japanese imperial-era system (令和, Reiwa for 2019–present; 平成, Heisei for
1989–2019) using `Intl.DateTimeFormat` with the `japanese` calendar, handle
era transitions correctly, and gracefully fall back when future undeclared eras
are encountered.

## Context

Japan uses both the Gregorian calendar and a regnal-era calendar where year 1
resets at the start of each emperor's reign. ICU/CLDR ships era data up to the
current known era (Reiwa, started 2019-05-01). Cloudflare Workers v8 ICU
includes this data. The danger areas are:

- Era-boundary dates (the last day of Heisei / first day of Reiwa)
- Dates before 1868 (Meiji) which use extended historical eras
- A future era declaration that has not yet landed in the deployed ICU version

## Japanese Calendar Era Formatting

```typescript
// src/lib/ja-date.ts

/** Full Japanese era date: 令和8年8月23日（日曜日） */
export const jaEraFull = new Intl.DateTimeFormat('ja-JP-u-ca-japanese', {
  era: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
});

/** Narrow era abbreviation: R8.08.23 */
export const jaEraNarrow = new Intl.DateTimeFormat('ja-JP-u-ca-japanese', {
  era: 'narrow',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** Gregorian fallback for contexts that must be unambiguous */
export const jaGregorian = new Intl.DateTimeFormat('ja-JP', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export function formatJapaneseDate(date: Date): string {
  try {
    return jaEraFull.format(date);
  } catch {
    // Unknown future era — fall back to Gregorian
    return jaGregorian.format(date);
  }
}

// formatJapaneseDate(new Date('2026-08-23'))
// → "令和8年8月23日日曜日"
```

## Era Boundary Handling

The Heisei–Reiwa transition occurred on 2019-05-01. Dates on either side of
this boundary must be formatted with the correct era.

```typescript
// src/lib/ja-era-boundary.ts

const ERA_REIWA_START = new Date('2019-05-01T00:00:00+09:00');
const ERA_HEISEI_START = new Date('1989-01-08T00:00:00+09:00');

export type JapaneseEraName = '令和' | '平成' | '昭和' | '大正' | '明治' | '不明';

export function resolveEraName(date: Date): JapaneseEraName {
  const ts = date.getTime();
  if (ts >= ERA_REIWA_START.getTime()) return '令和';
  if (ts >= ERA_HEISEI_START.getTime()) return '平成';
  if (ts >= new Date('1926-12-25T00:00:00+09:00').getTime()) return '昭和';
  if (ts >= new Date('1912-07-30T00:00:00+09:00').getTime()) return '大正';
  if (ts >= new Date('1868-01-25T00:00:00+09:00').getTime()) return '明治';
  return '不明';
}

export function eraYear(date: Date): number {
  const era = resolveEraName(date);
  const eraStarts: Record<JapaneseEraName, number> = {
    '令和': 2019,
    '平成': 1989,
    '昭和': 1926,
    '大正': 1912,
    '明治': 1868,
    '不明': 0,
  };
  return date.getFullYear() - eraStarts[era] + 1;
}

export function formatEraDate(date: Date): string {
  const era = resolveEraName(date);
  const year = eraYear(date);
  // Month/day via Intl to get Japanese month name
  const md = new Intl.DateTimeFormat('ja-JP', {
    month: 'long',
    day: 'numeric',
  }).format(date);
  return `${era}${year}年${md}`;
}

// formatEraDate(new Date('2019-04-30')) → "平成31年4月30日"
// formatEraDate(new Date('2019-05-01')) → "令和1年5月1日"
// formatEraDate(new Date('2026-01-01')) → "令和8年1月1日"
```

## Workers Edge Handler: Japanese Date Response

```typescript
// src/index.ts
import { formatJapaneseDate, formatEraDate, resolveEraName } from './lib/ja-era-boundary';

interface DateResponse {
  gregorian: string;
  japaneseEra: string;
  eraName: string;
  eraYear: number;
}

const jaDateISO = new Intl.DateTimeFormat('ja-JP', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  timeZone: 'Asia/Tokyo',
});

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const raw = url.searchParams.get('date');

    const date = raw ? new Date(raw) : new Date();
    if (isNaN(date.getTime())) {
      return new Response('Invalid date', { status: 400 });
    }

    const response: DateResponse = {
      gregorian: jaDateISO.format(date),
      japaneseEra: formatJapaneseDate(date),
      eraName: resolveEraName(date),
      eraYear: eraYear(date),
    };

    return new Response(JSON.stringify(response, null, 2), {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Language': 'ja-JP',
        'Cache-Control': 'public, max-age=86400',
      },
    });
  },
};

// Import eraYear directly (re-exported for convenience)
function eraYear(date: Date): number {
  const starts: Record<string, number> = {
    '令和': 2019, '平成': 1989, '昭和': 1926, '大正': 1912, '明治': 1868,
  };
  const era = resolveEraName(date);
  return era === '不明' ? 0 : date.getFullYear() - starts[era] + 1;
}
```

## KV Caching Era-Formatted Strings

Formatting Japanese era dates is CPU-cheap, but if you serve thousands of
distinct date strings (e.g. in a product catalogue), cache them in KV.

```typescript
// src/lib/kv-era-cache.ts

export async function getOrFormatEraDate(
  kv: KVNamespace,
  date: Date,
): Promise<string> {
  const key = `era-date:${date.toISOString().slice(0, 10)}`;
  const cached = await kv.get(key);
  if (cached) return cached;

  const formatted = formatJapaneseDate(date);
  // Era dates don't change; cache indefinitely (30 days TTL as safety)
  await kv.put(key, formatted, { expirationTtl: 86400 * 30 });
  return formatted;
}
```

## Anti-patterns

- **Using `new Date().toLocaleDateString('ja-JP-u-ca-japanese')`** — the
  `toLocaleDateString` method is not always available in all Workers runtimes;
  use `Intl.DateTimeFormat` explicitly.
- **Hardcoding "令和" as the only possible era** — future era names are unknown
  until officially announced; always fall back to Gregorian.
- **Ignoring the JST (+09:00) offset** — a date stored in UTC that crosses
  midnight JST will render as the wrong day. Always pass `timeZone: 'Asia/Tokyo'`
  or normalise to JST before formatting.
- **Formatting era years as Gregorian** — "2026年" is Gregorian; "令和8年" is
  imperial. Mixing them confuses users. Choose one system per surface.
- **Parsing user-input era dates without validation** — "令和99年" is not a valid
  date; validate era-year combinations before constructing a `Date`.

## Gotchas

- `Intl.DateTimeFormat('ja-JP-u-ca-japanese', { era: 'long' }).format(d)` on V8
  renders "令和8年" as `"令和8年"` but the exact string depends on ICU version;
  always test output format in `wrangler dev`.
- The first year of an era is sometimes written "元年" (first year) rather than
  "1年" in formal Japanese. ICU uses "1年" by default; implement "元年" manually
  if required by your style guide.
- `Intl.DateTimeFormat` with `ca-japanese` throws a `RangeError` for dates
  before Meiji (pre-1868) on some ICU configurations — wrap in try/catch.
- Era-transition minutes matter: the Heisei era ended at midnight JST on
  2019-04-30; a UTC timestamp of `2019-04-30T15:00:00Z` is `2019-05-01T00:00:00+09:00`,
  which is already Reiwa.
- KV keys containing Japanese characters are valid but prefer ASCII keys (`era-date:2026-08-23`) for debuggability.

## Verification

```typescript
// test/ja-era.spec.ts

import { resolveEraName, formatEraDate } from '../src/lib/ja-era-boundary';

const cases: [string, string, string][] = [
  ['2026-08-23', '令和', '令和8年8月23日'],
  ['2019-05-01', '令和', '令和1年5月1日'],
  ['2019-04-30', '平成', '平成31年4月30日'],
  ['1989-01-07', '昭和', '昭和64年1月7日'],
  ['1989-01-08', '平成', '平成1年1月8日'],
];

for (const [iso, expectedEra, expectedFmt] of cases) {
  const d = new Date(iso + 'T12:00:00+09:00');
  const era = resolveEraName(d);
  if (era !== expectedEra) {
    throw new Error(`${iso}: expected era ${expectedEra}, got ${era}`);
  }
  const fmt = formatEraDate(d);
  if (fmt !== expectedFmt) {
    throw new Error(`${iso}: expected "${expectedFmt}", got "${fmt}"`);
  }
}
console.log('All era boundary tests passed');
```

## Related

- `datetime-formatting-temporal-api-intl.md`
- `date-time-timezone-workers-edge-formatting.md`
- `edge-timezone-detection-cf-object.md`
- `non-gregorian-calendars-eras-2026.md`
- `translation-kv-caching-ttl-strategy.md`

## Sources

- CLDR Japanese calendar era data — https://github.com/unicode-org/cldr/blob/main/common/supplemental/supplementalData.xml
- MDN `Intl.DateTimeFormat` `era` option — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat
- Unicode BCP 47 `ca-japanese` extension — https://www.unicode.org/reports/tr35/#u_Extension
- Japanese era (gengo) Wikipedia reference — https://en.wikipedia.org/wiki/Japanese_era_name
- Cloudflare Workers runtime standards — https://developers.cloudflare.com/workers/runtime-apis/web-standards/
