# Indonesian Bahasa Locale on Cloudflare Workers: Intl Date and Number Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An e-commerce platform serving Indonesia displays prices as "Rp1.234.567" on the server
but shows "Rp 1,234,567" from the edge, causing user confusion. Date strings rendered as
"23 Agustus 2026" on one service appear as "August 23, 2026" on another. Teams migrating
from a Java-based monolith to Cloudflare Workers encounter subtle `Intl` behaviour
differences for the `id` and `id-ID` locale tags.

## Context

Indonesian (Bahasa Indonesia, BCP 47: `id`, region variant `id-ID`) is the official language
of Indonesia with roughly 270 million speakers. The CLDR locale data for `id-ID` specifies:

- **Decimal separator**: comma (`,`) — `1.234,56`
- **Grouping separator**: period (`.`) — `1.234.567`
- **Currency**: Indonesian Rupiah (IDR), symbol `Rp`, no decimal fraction in everyday display
- **Date order**: day-month-year (`23 Agustus 2026`)
- **Week start**: Sunday (CLDR `weekData` for region `ID`)
- **Calendar**: Gregorian is dominant; Islamic calendar (`u-ca-islamic`) appears in religious
  contexts but is not the default
- **Number system**: Latin (`latn`), same digits as `en`

Cloudflare Workers expose the full V8 `Intl` stack. The runtime locale data follows
ICU / CLDR releases bundled with the V8 version in use. As of 2026, Workers V8 ships
CLDR 45+ data, which aligns with the examples in this article.

## Formatting Numbers and Currency

### Basic number formatting

```typescript
// workers/src/id-formatting.ts
export function formatNumberID(value: number): string {
  // id-ID uses period thousands separator, comma decimal separator
  return new Intl.NumberFormat('id-ID').format(value);
  // 1234567.89 → "1.234.567,89"
}

export function formatCurrencyIDR(amount: number): string {
  // IDR has no minor unit in everyday use — maximumFractionDigits: 0
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
  // 1234567 → "Rp 1.234.567"
}

export function formatCurrencyCompactIDR(amount: number): string {
  // Compact notation for large sums (jutaan = millions)
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    notation: 'compact',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(amount);
  // 5000000 → "Rp 5 jt"
}
```

### Percent formatting

```typescript
export function formatPercentID(ratio: number): string {
  return new Intl.NumberFormat('id-ID', { style: 'percent' }).format(ratio);
  // 0.253 → "25%"  (no space before % in id-ID CLDR data)
}
```

## Formatting Dates and Times

### Standard date patterns

```typescript
export function formatDateID(date: Date, style: 'full' | 'long' | 'medium' | 'short' = 'long'): string {
  return new Intl.DateTimeFormat('id-ID', { dateStyle: style }).format(date);
  // full   → "Sabtu, 23 Agustus 2026"
  // long   → "23 Agustus 2026"
  // medium → "23 Agu 2026"
  // short  → "23/08/26"
}

export function formatTimeID(date: Date): string {
  return new Intl.DateTimeFormat('id-ID', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
  // → "14.30.05"  (period as time separator in id-ID)
}

export function formatDateTimeID(date: Date): string {
  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(date);
  // → "23 Agustus 2026, 14.30"
}
```

### Relative time

```typescript
export function formatRelativeID(deltaSeconds: number): string {
  const rtf = new Intl.RelativeTimeFormat('id-ID', { numeric: 'auto' });
  if (Math.abs(deltaSeconds) < 60) return rtf.format(Math.round(deltaSeconds), 'second');
  if (Math.abs(deltaSeconds) < 3600) return rtf.format(Math.round(deltaSeconds / 60), 'minute');
  if (Math.abs(deltaSeconds) < 86400) return rtf.format(Math.round(deltaSeconds / 3600), 'hour');
  return rtf.format(Math.round(deltaSeconds / 86400), 'day');
  // -3600 → "1 jam yang lalu"
  // 86400 → "besok"
}
```

## Workers Handler: Locale-Aware API Response

```typescript
// workers/src/index.ts
import type { Env } from './env';

interface ProductPrice {
  id: string;
  name: string;
  priceIDR: number;
  stock: number;
  updatedAt: string; // ISO 8601
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/products' && request.method === 'GET') {
      return handleProducts(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handleProducts(request: Request, env: Env): Promise<Response> {
  // Determine locale: explicit query param > Accept-Language > fallback
  const url = new URL(request.url);
  const requestedLocale = url.searchParams.get('locale') ?? 'id-ID';
  const locale = Intl.getCanonicalLocales(requestedLocale)[0] ?? 'id-ID';

  // Fetch raw products from D1
  const stmt = env.DB.prepare('SELECT id, name, price_idr, stock, updated_at FROM products LIMIT 50');
  const { results } = await stmt.all<{
    id: string;
    name: string;
    price_idr: number;
    stock: number;
    updated_at: string;
  }>();

  const numberFmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });

  const dateFmt = new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Jakarta',
  });

  const formatted = results.map((row) => ({
    id: row.id,
    name: row.name,
    priceDisplay: numberFmt.format(row.price_idr),
    stock: row.stock,
    updatedDisplay: dateFmt.format(new Date(row.updated_at)),
  }));

  return Response.json({ locale, products: formatted });
}
```

## Timezone Handling for Indonesian Regions

Indonesia spans three time zones. Workers can pick the correct one based on a city/region
identifier stored per user.

```typescript
const INDONESIA_TIMEZONES: Record<string, string> = {
  WIB: 'Asia/Jakarta',    // Western Indonesian Time (Sumatra, Java, Kalimantan West/Central)
  WITA: 'Asia/Makassar',  // Central Indonesian Time (Bali, Sulawesi, Kalimantan South/East)
  WIT: 'Asia/Jayapura',   // Eastern Indonesian Time (Maluku, Papua)
};

export function formatIndonesianDateTime(
  isoDate: string,
  timezone: keyof typeof INDONESIA_TIMEZONES = 'WIB',
): string {
  const tz = INDONESIA_TIMEZONES[timezone];
  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'full',
    timeStyle: 'long',
    timeZone: tz,
  }).format(new Date(isoDate));
  // "Sabtu, 23 Agustus 2026 pukul 14.30.00 WIB"
}
```

## KV Caching Formatted Strings

Pre-formatting at write time and caching in KV avoids repeated `Intl` construction on hot
paths (product listing pages with thousands of SKUs).

```typescript
interface CachedPrice {
  raw: number;
  display: string;
  cachedAt: number;
}

const CACHE_TTL_SECONDS = 3600;

export async function getCachedPrice(
  kv: KVNamespace,
  productId: string,
  rawPrice: number,
): Promise<string> {
  const key = `price:id-ID:${productId}`;
  const cached = await kv.get<CachedPrice>(key, 'json');

  if (cached && cached.raw === rawPrice) {
    return cached.display;
  }

  const display = new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(rawPrice);

  await kv.put(key, JSON.stringify({ raw: rawPrice, display, cachedAt: Date.now() }), {
    expirationTtl: CACHE_TTL_SECONDS,
  });

  return display;
}
```

## Anti-patterns

- **Hard-coding `Rp` prefix manually**: `'Rp ' + amount.toLocaleString()` — this bypasses
  CLDR data and produces inconsistent spacing/grouping. Always use `Intl.NumberFormat`.
- **Using `en-US` grouping for Indonesian numbers**: The `.` (period) grouping separator in
  `id-ID` is opposite to `en-US`. Naive string replacement will corrupt values.
- **Assuming a single Indonesia timezone**: Jakarta (WIB) is UTC+7, Makassar (WITA) UTC+8,
  Jayapura (WIT) UTC+9. Using `Asia/Jakarta` for all users in Sulawesi or Papua is wrong.
- **Dropping IDR fraction digits globally**: Some payment systems require two decimal places
  for API interchange even though display conventionally shows none. Keep raw values as
  integers (Rupiah, no minor unit) in D1; format only at the presentation layer.
- **Neglecting the Islamic calendar**: For Ramadan or Eid-related features, users may expect
  Hijri dates. Use `id-ID-u-ca-islamic-umalqura` to show Hijri alongside Gregorian.

## Gotchas

- `new Intl.DateTimeFormat('id-ID').format(date)` returns `"23/8/2026"` (short, no leading
  zero) by default — not the long `"23 Agustus 2026"` form. Always specify `dateStyle`.
- The CLDR time separator for `id-ID` is `.` (period), so `"14.30"` is correct; do not
  replace it with `:` for display.
- `Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR' })` may produce `"Rp 14.30,00"`
  (with non-breaking space and fractional cents) in some ICU versions. Pin
  `minimumFractionDigits: 0, maximumFractionDigits: 0` explicitly for IDR.
- `id` (without region) and `id-ID` resolve to the same CLDR root in V8 but prefer `id-ID`
  for clarity and future-proofing with region-specific overrides.
- Month names in `id-ID` are localised (`Januari`, `Februari`, … `Desember`) — they must
  come from `Intl.DateTimeFormat`, not a hard-coded English array.

## Verification

```typescript
// Unit test (Vitest / Jest with --experimental-vm-modules)
import { describe, it, expect } from 'vitest';
import { formatCurrencyIDR, formatDateID, formatRelativeID } from './id-formatting';

describe('id-ID formatting', () => {
  it('formats IDR without fractional digits', () => {
    expect(formatCurrencyIDR(1_234_567)).toBe('Rp 1.234.567');
  });

  it('formats long date in Bahasa Indonesia', () => {
    const d = new Date('2026-08-23T00:00:00Z');
    expect(formatDateID(d, 'long')).toBe('23 Agustus 2026');
  });

  it('formats relative time correctly', () => {
    expect(formatRelativeID(-3600)).toBe('1 jam yang lalu');
  });
});
```

Run against Workers runtime:

```bash
wrangler dev --local
curl "http://localhost:8787/api/products?locale=id-ID" | jq '.products[0].priceDisplay'
# Expected: "Rp 1.234.567" (or with NBSP)
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `date-time-timezone-workers-edge-formatting.md`
- `kv-locale-key-sharding-high-traffic.md`
- `cldr-data-2026.md`
- `devanagari-hindi-locale-workers-intl-formatting.md`

## Sources

- CLDR locale data for `id`: https://github.com/unicode-org/cldr/tree/main/common/main
- BCP 47 language subtag registry — `id` (Indonesian)
- MDN `Intl.NumberFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN `Intl.DateTimeFormat`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- Cloudflare Workers Runtime API: https://developers.cloudflare.com/workers/runtime-apis/
- Bank Indonesia currency conventions: https://www.bi.go.id
