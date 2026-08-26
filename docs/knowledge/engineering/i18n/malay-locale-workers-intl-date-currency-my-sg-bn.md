# Malay Locale on Cloudflare Workers: Intl Date and Currency for Malaysia, Singapore, and Brunei

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Southeast Asian fintech platform serving users in Malaysia (MY), Singapore (SG), and
Brunei (BN) renders currency amounts in inconsistent formats: Malaysian Ringgit displays
as `"MYR1,234.56"` instead of `"RM1,234.56"`, Brunei Dollar appears without the correct
`"B$"` symbol, and Singapore Dollar amounts show the wrong number of decimal places in one
locale but not another. Date formatting in Malay (`ms`) uses English month names in some
environments and Malay ones in others depending on whether `ms-MY`, `ms-SG`, or `ms-BN`
is used.

## Context

Malay (Bahasa Melayu, BCP 47: `ms`) is the official language of Malaysia, Brunei, and one
of four official languages of Singapore. Key `Intl` facts for the three main regional variants:

| Feature           | `ms-MY` (Malaysia)          | `ms-SG` (Singapore)         | `ms-BN` (Brunei)            |
|-------------------|-----------------------------|-----------------------------|-----------------------------|
| Currency          | MYR (Ringgit, `RM`)         | SGD (Dollar, `S$`)          | BND (Brunei Dollar, `B$`)   |
| Decimal sep       | `.` (period)                | `.` (period)                | `.` (period)                |
| Thousands sep     | `,` (comma)                 | `,` (comma)                 | `,` (comma)                 |
| Date order        | d/M/yyyy (`23/8/2026`)      | d/M/yyyy                    | d/M/yyyy                    |
| Long date         | `23 Ogos 2026`              | `23 Ogos 2026`              | `23 Ogos 2026`              |
| Week start        | Monday (MY), Sunday (SG/BN) | Sunday                      | Monday                      |
| Time              | 12-hour (AM/PM common)      | 12-hour                     | 12-hour                     |
| Number system     | `latn`                      | `latn`                      | `latn`                      |

Malay month names (from CLDR):

| English   | Malay (Bahasa Melayu) |
|-----------|-----------------------|
| January   | Januari               |
| February  | Februari              |
| March     | Mac                   |
| April     | April                 |
| May       | Mei                   |
| June      | Jun                   |
| July      | Julai                 |
| August    | Ogos                  |
| September | September             |
| October   | Oktober               |
| November  | November              |
| December  | Disember              |

Cloudflare Workers V8 runtime supports `ms`, `ms-MY`, `ms-SG`, and `ms-BN` with CLDR 45+
data.

## Currency Formatting

### Malaysia (MYR)

```typescript
// workers/src/ms-formatting.ts

export function formatMYR(amount: number): string {
  return new Intl.NumberFormat('ms-MY', {
    style: 'currency',
    currency: 'MYR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "RM1,234.50"  (symbol prefix, no space in ms-MY CLDR)
}

export function formatMYRCompact(amount: number): string {
  return new Intl.NumberFormat('ms-MY', {
    style: 'currency',
    currency: 'MYR',
    notation: 'compact',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(amount);
  // 5000000 → "RM5 juta"
}
```

### Singapore (SGD)

```typescript
export function formatSGD(amount: number): string {
  return new Intl.NumberFormat('ms-SG', {
    style: 'currency',
    currency: 'SGD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "S$1,234.50"
}

// Singapore also displays amounts in English context; for English-Singapore use 'en-SG'
export function formatSGDEnglish(amount: number): string {
  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency: 'SGD',
  }).format(amount);
  // 1234.5 → "$1,234.50"  (en-SG uses $ without S prefix)
}
```

### Brunei (BND)

```typescript
export function formatBND(amount: number): string {
  return new Intl.NumberFormat('ms-BN', {
    style: 'currency',
    currency: 'BND',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  // 1234.5 → "B$1,234.50"  (verify symbol in your V8/ICU version — some show "$")
}

// BND is at parity with SGD historically; display both when relevant
export function formatBNDWithParity(amount: number): string {
  const bnd = new Intl.NumberFormat('ms-BN', {
    style: 'currency',
    currency: 'BND',
    minimumFractionDigits: 2,
  }).format(amount);
  const sgd = new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency: 'SGD',
    minimumFractionDigits: 2,
  }).format(amount);
  return `${bnd} / ${sgd}`;
}
```

### Generic locale-routing helper

```typescript
type MalayRegion = 'MY' | 'SG' | 'BN';

const REGION_CONFIG: Record<MalayRegion, { locale: string; currency: string }> = {
  MY: { locale: 'ms-MY', currency: 'MYR' },
  SG: { locale: 'ms-SG', currency: 'SGD' },
  BN: { locale: 'ms-BN', currency: 'BND' },
};

export function formatRegionalCurrency(amount: number, region: MalayRegion): string {
  const { locale, currency } = REGION_CONFIG[region];
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
```

## Date and Time Formatting

```typescript
export function formatDateMs(
  date: Date,
  region: MalayRegion = 'MY',
  style: 'full' | 'long' | 'medium' | 'short' = 'long',
): string {
  const { locale } = REGION_CONFIG[region];
  return new Intl.DateTimeFormat(locale, { dateStyle: style }).format(date);
  // full   → "Sabtu, 23 Ogos 2026"
  // long   → "23 Ogos 2026"
  // medium → "23 Ogo 2026"
  // short  → "23/8/2026"
}

export function formatTimeMs(date: Date, region: MalayRegion = 'MY'): string {
  const { locale } = REGION_CONFIG[region];
  const tz: Record<MalayRegion, string> = {
    MY: 'Asia/Kuala_Lumpur',
    SG: 'Asia/Singapore',
    BN: 'Asia/Brunei',
  };
  return new Intl.DateTimeFormat(locale, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: tz[region],
  }).format(date);
  // → "2:30 PTG"  (PTG = petang = afternoon, ms-MY)
  // → "2:30 PM"   (ms-SG may use EN AM/PM)
}

export function formatRelativeMs(deltaSeconds: number, region: MalayRegion = 'MY'): string {
  const { locale } = REGION_CONFIG[region];
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const abs = Math.abs(deltaSeconds);
  if (abs < 60)    return rtf.format(Math.round(deltaSeconds), 'second');
  if (abs < 3600)  return rtf.format(Math.round(deltaSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(deltaSeconds / 3600), 'hour');
  return rtf.format(Math.round(deltaSeconds / 86400), 'day');
  // -3600 → "1 jam yang lalu"
  // 86400 → "esok"
}
```

## Workers Handler: Multi-Region Malay Financial Dashboard

```typescript
import type { Env } from './env';
import { formatRegionalCurrency, formatDateMs } from './ms-formatting';

type MalayRegion = 'MY' | 'SG' | 'BN';

function detectRegion(request: Request): MalayRegion {
  // Cloudflare provides country code
  const country = (request.cf as { country?: string } | undefined)?.country ?? 'MY';
  if (country === 'SG') return 'SG';
  if (country === 'BN') return 'BN';
  return 'MY';
}

interface Transaction {
  id: string;
  amount: number;
  currency: string;
  created_at: string;
  description_ms: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/transaksi') {
      const region = detectRegion(request);
      const { locale } = { MY: { locale: 'ms-MY' }, SG: { locale: 'ms-SG' }, BN: { locale: 'ms-BN' } }[region];

      const { results } = await env.DB.prepare(
        'SELECT id, amount, currency, created_at, description_ms FROM transactions ORDER BY created_at DESC LIMIT 20',
      ).all<Transaction>();

      const dateFmt = new Intl.DateTimeFormat(locale, {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: region === 'SG' ? 'Asia/Singapore' : region === 'BN' ? 'Asia/Brunei' : 'Asia/Kuala_Lumpur',
      });

      return Response.json({
        region,
        locale,
        transactions: results.map((t) => ({
          id: t.id,
          amount: formatRegionalCurrency(t.amount, region),
          date: dateFmt.format(new Date(t.created_at)),
          description: t.description_ms,
        })),
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## KV Caching for Multi-Region Price Lists

```typescript
interface CachedPriceEntry {
  raw: number;
  displays: Record<MalayRegion, string>;
  cachedAt: number;
}

type MalayRegion = 'MY' | 'SG' | 'BN';

async function getCachedPriceDisplays(
  kv: KVNamespace,
  productId: string,
  rawPrice: number,
): Promise<Record<MalayRegion, string>> {
  const key = `price:ms:${productId}`;
  const cached = await kv.get<CachedPriceEntry>(key, 'json');

  if (cached && cached.raw === rawPrice) {
    return cached.displays;
  }

  const displays: Record<MalayRegion, string> = {
    MY: new Intl.NumberFormat('ms-MY', { style: 'currency', currency: 'MYR', minimumFractionDigits: 2 }).format(rawPrice),
    SG: new Intl.NumberFormat('ms-SG', { style: 'currency', currency: 'SGD', minimumFractionDigits: 2 }).format(rawPrice),
    BN: new Intl.NumberFormat('ms-BN', { style: 'currency', currency: 'BND', minimumFractionDigits: 2 }).format(rawPrice),
  };

  await kv.put(key, JSON.stringify({ raw: rawPrice, displays, cachedAt: Date.now() }), {
    expirationTtl: 3600,
  });

  return displays;
}
```

## Islamic Calendar for Malaysian Religious Contexts

Malaysia uses the Gregorian calendar officially but the Hijri calendar for religious dates
(Ramadan, Hari Raya). ICU extension `-u-ca-islamic-umalqura` is available in V8.

```typescript
export function formatHijriDate(date: Date): string {
  return new Intl.DateTimeFormat('ms-MY-u-ca-islamic-umalqura', {
    dateStyle: 'long',
  }).format(date);
  // "29 Muharram 1448 H"  (approximate — depends on exact date)
}

export function formatDualCalendarDate(date: Date): string {
  const gregorian = new Intl.DateTimeFormat('ms-MY', { dateStyle: 'long' }).format(date);
  const hijri = new Intl.DateTimeFormat('ms-MY-u-ca-islamic-umalqura', { dateStyle: 'long' }).format(date);
  return `${gregorian} / ${hijri}`;
}
```

## Anti-patterns

- **Using `MYR` symbol manually as `RM`**: while `RM` is correct, prepending it manually
  bypasses `Intl` and risks wrong spacing/position. `Intl.NumberFormat('ms-MY', { style: 'currency', currency: 'MYR' })`
  produces `RM` correctly.
- **Treating `ms`, `ms-MY`, `ms-SG`, `ms-BN` as interchangeable**: Region variants differ
  in week start, timezone default, and the currency expected by users. Always use the
  region-specific tag for financial applications.
- **Assuming SGD and BND are the same**: They trade at 1:1 parity but are distinct
  currencies with different symbols and different legal contexts. Never substitute one for
  the other in a database.
- **Hard-coding English month names**: Malay month names differ from English: `Mac` (March),
  `Mei` (May), `Jun` (June), `Julai` (July), `Ogos` (August), `Disember` (December). Use
  `Intl.DateTimeFormat` to get CLDR-correct names.
- **Using 24-hour time by default for MS consumers**: Malaysia, Singapore, and Brunei all
  commonly use 12-hour time with AM/PM (`PG` = pagi = morning, `PTG` = petang = afternoon
  in ms-MY). Use `hour12: true`.

## Gotchas

- Malay plural rules (CLDR) have only one form: `other` for all counts. There is no
  grammatical plural distinction in Malay (reduplication is a different construct, not
  handled by `Intl.PluralRules`). `new Intl.PluralRules('ms').select(n)` always returns
  `"other"`.
- `Intl.DateTimeFormat('ms-MY', { hour12: true })` may produce `"PTG"` (afternoon) or
  `"PG"` (morning) as day-period strings depending on the CLDR version in V8. Test your
  ICU build if you need to parse these strings.
- Singapore uses `Asia/Singapore` (UTC+8, no DST); Brunei uses `Asia/Brunei` (UTC+8, no
  DST); Malaysia uses `Asia/Kuala_Lumpur` (UTC+8, no DST). All three are UTC+8 but keep
  separate IANA IDs.
- `ms-SG` in some older ICU builds falls back to `ms` data; test that currency symbol and
  date patterns are correct for your deployment V8 version.
- The BND currency symbol varies by ICU version: some show `BND`, some `B$`, some `$`.
  Pin `minimumFractionDigits` and verify the symbol at test time.

## Verification

```typescript
import { describe, it, expect } from 'vitest';

describe('Malay locale formatting', () => {
  it('formats MYR with RM symbol', () => {
    const fmt = new Intl.NumberFormat('ms-MY', { style: 'currency', currency: 'MYR', minimumFractionDigits: 2 });
    expect(fmt.format(1234.5)).toContain('RM');
    expect(fmt.format(1234.5)).toContain('1,234.50');
  });

  it('formats long date with Malay month name', () => {
    const d = new Date('2026-08-23T00:00:00Z');
    const fmt = new Intl.DateTimeFormat('ms-MY', { dateStyle: 'long', timeZone: 'Asia/Kuala_Lumpur' });
    expect(fmt.format(d)).toContain('Ogos');
  });

  it('short date is d/M/yyyy order', () => {
    const d = new Date('2026-08-23T00:00:00Z');
    const fmt = new Intl.DateTimeFormat('ms-MY', { dateStyle: 'short', timeZone: 'Asia/Kuala_Lumpur' });
    expect(fmt.format(d)).toBe('23/8/2026');
  });

  it('plural rule always returns other', () => {
    const pr = new Intl.PluralRules('ms');
    expect(pr.select(0)).toBe('other');
    expect(pr.select(1)).toBe('other');
    expect(pr.select(100)).toBe('other');
  });
});
```

```bash
# Manual verification via wrangler
wrangler dev --local
curl "http://localhost:8787/api/transaksi" \
  -H "CF-IPCountry: MY" | jq '.transactions[0].amount'
# Expected: "RM1,234.50"
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `date-time-timezone-workers-edge-formatting.md`
- `indonesian-bahasa-locale-workers-intl-formatting.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `kv-locale-key-sharding-high-traffic.md`
- `non-gregorian-calendars-eras-2026.md`

## Sources

- CLDR locale data for `ms`: https://github.com/unicode-org/cldr/tree/main/common/main
- BCP 47 subtag registry — `ms` (Malay), `MY`, `SG`, `BN`
- MDN `Intl.NumberFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN `Intl.DateTimeFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- Bank Negara Malaysia currency information: https://www.bnm.gov.my
- Monetary Authority of Singapore: https://www.mas.gov.sg
- Brunei Currency and Monetary Board: https://www.bdcb.gov.bn
- IANA TZDB: `Asia/Kuala_Lumpur`, `Asia/Singapore`, `Asia/Brunei`
