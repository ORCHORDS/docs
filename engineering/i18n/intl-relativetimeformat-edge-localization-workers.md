# Using `Intl.RelativeTimeFormat` in Cloudflare Workers for Edge-Side Relative Timestamps

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A JSON API response returns a raw Unix timestamp and the client renders "2 hours ago" in JavaScript, causing a flash of un-localized content and an extra round-trip. Moving this formatting to the Cloudflare Worker edge eliminates client-side JavaScript overhead, ensures consistent locale handling, and allows KV caching of the formatted string. The challenge is selecting the right relative-time unit (seconds vs. minutes vs. days) and picking the correct locale per request.

## Context

`Intl.RelativeTimeFormat` is part of the ECMAScript Internationalization API and is fully supported in the V8 engine that powers Cloudflare Workers. It accepts a numeric value and a unit (`"second"`, `"minute"`, `"hour"`, `"day"`, `"week"`, `"month"`, `"year"`) plus `numeric: 'auto'` to emit natural-language forms like "yesterday" and "tomorrow" instead of "-1 day". The locale should be detected from the `Accept-Language` request header, or from `request.cf.country` as a fallback when the header is absent. Formatted strings are deterministic for a given (value, unit, locale) triple, making them ideal for short-TTL KV caching to avoid re-computing on every request.

## Detecting the Best Relative-Time Unit

```typescript
// utils/relativeTime.ts

export type RTFUnit =
  | 'second' | 'minute' | 'hour' | 'day' | 'week' | 'month' | 'year';

interface RelativeTimeParts {
  value: number;  // negative = past, positive = future
  unit: RTFUnit;
}

/**
 * Given a duration in milliseconds (positive = future, negative = past),
 * returns the most human-readable (value, unit) pair.
 */
export function getBestUnit(deltaMs: number): RelativeTimeParts {
  const abs = Math.abs(deltaMs);
  const sign = deltaMs < 0 ? -1 : 1;

  const MINUTE = 60_000;
  const HOUR   = 60 * MINUTE;
  const DAY    = 24 * HOUR;
  const WEEK   = 7  * DAY;
  const MONTH  = 30 * DAY;
  const YEAR   = 365 * DAY;

  if (abs < MINUTE)  return { value: sign * Math.round(abs / 1_000), unit: 'second' };
  if (abs < HOUR)    return { value: sign * Math.round(abs / MINUTE), unit: 'minute' };
  if (abs < DAY)     return { value: sign * Math.round(abs / HOUR),   unit: 'hour' };
  if (abs < WEEK)    return { value: sign * Math.round(abs / DAY),    unit: 'day' };
  if (abs < MONTH)   return { value: sign * Math.round(abs / WEEK),   unit: 'week' };
  if (abs < YEAR)    return { value: sign * Math.round(abs / MONTH),  unit: 'month' };
  return              { value: sign * Math.round(abs / YEAR),           unit: 'year' };
}

/**
 * Formats a past/future timestamp as a locale-relative string.
 *
 * @param timestamp  Unix epoch in seconds
 * @param locale     BCP 47 locale tag, e.g. "fr-FR"
 * @param numeric    'auto' => "yesterday"; 'always' => "-1 day"
 */
export function formatRelativeTime(
  timestamp: number,
  locale: string,
  numeric: 'auto' | 'always' = 'auto'
): string {
  const deltaMs = timestamp * 1_000 - Date.now();
  const { value, unit } = getBestUnit(deltaMs);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric, style: 'long' });
  return rtf.format(value, unit);
}
```

## Locale Detection from `cf.country` and `Accept-Language`

```typescript
// utils/detectLocale.ts

const COUNTRY_TO_LOCALE: Record<string, string> = {
  DE: 'de-DE', FR: 'fr-FR', JP: 'ja-JP', CN: 'zh-CN',
  BR: 'pt-BR', SA: 'ar-SA', IL: 'he-IL', IN: 'hi-IN',
  US: 'en-US', GB: 'en-GB', CA: 'en-CA', AU: 'en-AU',
};

export function detectLocale(request: Request): string {
  // 1. Prefer explicit Accept-Language header
  const acceptLang = request.headers.get('Accept-Language');
  if (acceptLang) {
    const primary = acceptLang.split(',')[0].trim().split(';')[0].trim();
    if (primary && primary !== '*') return primary;
  }

  // 2. Fall back to cf.country -> locale mapping
  const cf = (request as any).cf as { country?: string } | undefined;
  if (cf?.country && COUNTRY_TO_LOCALE[cf.country]) {
    return COUNTRY_TO_LOCALE[cf.country];
  }

  // 3. Default
  return 'en-US';
}
```

## KV Caching of Formatted Strings

```typescript
// worker.ts
import { detectLocale } from './utils/detectLocale';
import { formatRelativeTime } from './utils/relativeTime';

const KV_TTL = 60; // seconds — short TTL so "2 minutes ago" stays accurate

export interface Env {
  RTF_CACHE: KVNamespace;
}

async function getCachedRelativeTime(
  kv: KVNamespace,
  timestamp: number,
  locale: string
): Promise<string> {
  // Bucket timestamp to nearest minute to maximise cache hits
  const bucket = Math.floor(timestamp / 60);
  const key = `rtf:${locale}:${bucket}`;

  const cached = await kv.get(key);
  if (cached) return cached;

  const formatted = formatRelativeTime(timestamp, locale);
  await kv.put(key, formatted, { expirationTtl: KV_TTL });
  return formatted;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const tsParam = url.searchParams.get('ts');
    if (!tsParam || isNaN(Number(tsParam))) {
      return Response.json({ error: 'Missing or invalid ts query param' }, { status: 400 });
    }

    const timestamp = Number(tsParam);
    const locale = detectLocale(request);
    const relative = await getCachedRelativeTime(env.RTF_CACHE, timestamp, locale);

    return Response.json({
      timestamp,
      locale,
      relative,  // e.g. "il y a 2 heures" for fr-FR
    }, {
      headers: {
        'Cache-Control': `public, max-age=${KV_TTL}`,
        'Content-Language': locale,
      },
    });
  },
};
```

## `numeric: 'auto'` for Natural Language Output

Use `numeric: 'auto'` (the default in most UIs) to get "yesterday", "tomorrow", and "last week" instead of "-1 day", "in 1 day", "last 1 week". Switch to `numeric: 'always'` in contexts where exact counts matter (e.g., audit logs):

```typescript
// "yesterday" in en-US, "gestern" in de-DE
const yesterday = formatRelativeTime(Math.floor(Date.now() / 1000) - 86400, 'en-US', 'auto');
console.log(yesterday); // => "yesterday"

// Always numeric: "-1 day"
const alwaysNumeric = formatRelativeTime(Math.floor(Date.now() / 1000) - 86400, 'en-US', 'always');
console.log(alwaysNumeric); // => "1 day ago"
```

## Anti-patterns

- **Hardcoding unit thresholds in the client** — different products agree on different breakpoints (e.g., "just now" under 30s vs. under 60s); centralise the logic at the edge so all clients behave identically.
- **Using a full locale string as the raw KV key without bucketing** — `rtf:en-US:1753379823` changes every second, producing zero cache hits; bucket to the minute.
- **Ignoring `numeric: 'auto'` availability** — some locales do not have special forms for "yesterday"; the API falls back to numeric gracefully, but test before shipping.
- **Parsing `Accept-Language` with a simple split on `-`** — a tag like `zh-Hant-TW` has three subtags; use `split(',')[0]` then `split(';')[0]` to extract just the primary tag.

## Gotchas

- `Intl.RelativeTimeFormat` rounds toward zero, not toward the nearest unit — if you want "2 minutes ago" at 89 seconds, you must round yourself before calling `format()`.
- `request.cf.country` is only available in deployed Workers, not in `wrangler dev` local mode — guard with an optional-chain or the locale detection will throw.
- KV `get()` in a Worker counts against your read budget; a 60-second TTL with minute-bucketing means at most one write and a handful of reads per locale per minute globally.
- The `style` option (`'long'`, `'short'`, `'narrow'`) affects output length but not correctness — use `'short'` for mobile UIs where space is constrained.

## Verification

```bash
# Deploy
npx wrangler deploy

# Past timestamp (~2 hours ago)
TS=$(( $(date +%s) - 7200 ))
curl "https://my-worker.example.workers.dev/?ts=${TS}" \
  -H 'Accept-Language: fr-FR'
# Expected: {"relative":"il y a 2 heures", ...}

# Yesterday (auto numeric)
TS=$(( $(date +%s) - 86400 ))
curl "https://my-worker.example.workers.dev/?ts=${TS}" \
  -H 'Accept-Language: en-US'
# Expected: {"relative":"yesterday", ...}

# Check KV cache was populated
npx wrangler kv key list --binding RTF_CACHE | head -5
```

## Related

- `locale-aware-number-parsing-validation-workers.md`
- `bidi-text-rendering-rtl-mixed-content-workers.md`
- `translation-memory-d1-fuzzy-match-workers.md`

## Sources

- MDN Intl.RelativeTimeFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare Workers `request.cf` properties — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
