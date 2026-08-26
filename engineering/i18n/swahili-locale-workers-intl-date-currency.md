# Swahili Locale: Cloudflare Workers Intl Date and Currency Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) serves a growing East African user base across Kenya, Tanzania, and Uganda where Swahili (Kiswahili) is the primary communication language. Anonymous posts, timestamps, and coin/tip amounts need to be displayed in locale-appropriate formats. Without correct locale configuration, dates appear in US English order and currency symbols render as raw ISO codes, breaking trust with regional users.

## Context

Swahili is written in Latin script and is the national language of both Kenya (`sw-KE`) and Tanzania (`sw-TZ`). The two sub-locales differ: Kenya uses the Kenyan Shilling (KES) with a period as the decimal separator, while Tanzania uses the Tanzanian Shilling (TZS) with a comma. The V8 engine embedded in Cloudflare Workers ships full ICU data, so `Intl` APIs work correctly for `sw-KE` and `sw-TZ` without any additional polyfill.

## Locale Configuration in Workers

The IANA BCP 47 tags for Swahili are `sw-KE` (Kenya) and `sw-TZ` (Tanzania). Both use the Gregorian calendar and the Latin numbering system, so no `-u-ca-` or `-u-nu-` extensions are required. Detect the sub-locale from Cloudflare's `cf.country` field on the incoming request.

```typescript
// src/lib/locale.ts
export type SwahiliLocale = 'sw-KE' | 'sw-TZ';

export function resolveSwahiliLocale(request: Request): SwahiliLocale {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country?.toUpperCase();
  if (country === 'TZ') return 'sw-TZ';
  // Default to Kenya for all other East African requests
  return 'sw-KE';
}

// Validate an inbound locale string before trusting it
export function assertSwahiliLocale(tag: string): SwahiliLocale {
  if (tag === 'sw-KE' || tag === 'sw-TZ') return tag;
  throw new RangeError(`Unsupported Swahili locale: ${tag}`);
}
```

## Date and Time Formatting

Swahili uses the Gregorian calendar, but day names and month names should be displayed in Kiswahili. The `Intl.DateTimeFormat` API with the correct locale tag produces full Swahili month names (e.g., *Januari*, *Februari*) and short day names (*Jum*, *Alo*). For social timestamps on example project, favour medium-length date formats to avoid ambiguity.

```typescript
// src/lib/date.ts
export function formatSwahiliDate(
  date: Date,
  locale: SwahiliLocale,
  style: 'full' | 'long' | 'medium' | 'short' = 'medium'
): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: style,
  }).format(date);
}

export function formatSwahiliDateTime(
  date: Date,
  locale: SwahiliLocale
): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'long',
    timeStyle: 'short',
    // East Africa Time: UTC+3 (no DST)
    timeZone: 'Africa/Nairobi',
  }).format(date);
}

export function formatSwahiliRelativeTime(
  diffSeconds: number,
  locale: SwahiliLocale
): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (Math.abs(diffSeconds) < 60) return rtf.format(Math.round(diffSeconds), 'second');
  if (Math.abs(diffSeconds) < 3600) return rtf.format(Math.round(diffSeconds / 60), 'minute');
  if (Math.abs(diffSeconds) < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
  return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

// Example output (sw-KE):
// formatSwahiliDate(new Date('2026-08-23'), 'sw-KE') => "23 Ago 2026"
// formatSwahiliRelativeTime(-120, 'sw-KE') => "dakika 2 zilizopita"
```

## Number and Currency Formatting

Kenya and Tanzania both use shilling-based currencies without subunits in everyday usage (TZS has no cents; KES coins are whole numbers for most transactions). Use `maximumFractionDigits: 0` for shilling amounts on example project's tip/coin UI to match local conventions.

```typescript
// src/lib/currency.ts
const CURRENCY_BY_LOCALE: Record<SwahiliLocale, string> = {
  'sw-KE': 'KES',
  'sw-TZ': 'TZS',
};

export function formatSwahiliCurrency(
  amount: number,
  locale: SwahiliLocale
): string {
  const currency = CURRENCY_BY_LOCALE[locale];
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
    currencyDisplay: 'narrowSymbol',
  }).format(amount);
}

export function formatSwahiliCompactNumber(
  value: number,
  locale: SwahiliLocale
): string {
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(value);
}

// Example output:
// formatSwahiliCurrency(1500, 'sw-KE') => "KSh 1,500"
// formatSwahiliCurrency(25000, 'sw-TZ') => "TSh 25,000"
// formatSwahiliCompactNumber(1_200_000, 'sw-KE') => "1.2M"
```

## Text Handling and Plural Rules

Swahili has a noun class system, but its plural forms for numeric contexts are relatively simple: CLDR assigns Swahili the `one` (singular) and `other` (plural) categories, matching English structure. This makes ICU message formatting straightforward.

```typescript
// src/lib/plural.ts
export function swahiliPluralCategory(
  n: number,
  locale: SwahiliLocale
): Intl.LDMLPluralRule {
  const pr = new Intl.PluralRules(locale);
  return pr.select(n);
}

export function formatSwahiliPostCount(
  count: number,
  locale: SwahiliLocale
): string {
  const category = swahiliPluralCategory(count, locale);
  const formatted = new Intl.NumberFormat(locale).format(count);
  // Swahili messages for example project post counts
  const templates: Record<Intl.LDMLPluralRule, string> = {
    one: `chapisho ${formatted}`,   // "1 post"
    other: `machapisho ${formatted}`, // "N posts"
    zero: '', two: '', few: '', many: '',
  };
  return templates[category] || `machapisho ${formatted}`;
}

// Swahili list formatting
export function formatSwahiliList(
  items: string[],
  locale: SwahiliLocale,
  type: 'conjunction' | 'disjunction' = 'conjunction'
): string {
  return new Intl.ListFormat(locale, { type, style: 'long' }).format(items);
}
```

## KV Caching for Swahili Locale Data

Cache formatted strings and locale metadata in Cloudflare KV with locale-scoped keys. Use a short TTL for relative timestamps (they change by definition) and a long TTL for static currency/date format strings.

```typescript
// src/lib/kv-cache.ts
interface Env {
  LOCALE_CACHE: KVNamespace;
}

const STATIC_TTL = 86_400;    // 24 h for date/currency format strings
const DYNAMIC_TTL = 60;       // 1 min for relative timestamps

export async function getCachedSwahiliFormat(
  env: Env,
  key: string,
  locale: SwahiliLocale,
  compute: () => string,
  ttl: number = STATIC_TTL
): Promise<string> {
  const cacheKey = `i18n:${locale}:${key}`;
  const cached = await env.LOCALE_CACHE.get(cacheKey);
  if (cached !== null) return cached;

  const value = compute();
  // Fire-and-forget write — don't block the response
  env.LOCALE_CACHE.put(cacheKey, value, { expirationTtl: ttl });
  return value;
}

// Usage in a Worker fetch handler
export async function handleSwahiliRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const locale = resolveSwahiliLocale(request);
  const amount = 4500;

  const formatted = await getCachedSwahiliFormat(
    env,
    `currency:${amount}`,
    locale,
    () => formatSwahiliCurrency(amount, locale),
    STATIC_TTL
  );

  return new Response(JSON.stringify({ amount: formatted }), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
```

## Anti-patterns

- Do not use `sw` (bare Swahili without region) — decimal separator and currency differ between `sw-KE` and `sw-TZ`; always include the region subtag.
- Do not hardcode `KSh` or `TSh` as string literals; let `Intl.NumberFormat` emit the symbol so future CLDR updates propagate automatically.
- Do not display fractional shillings (e.g., `KES 1,500.00`) — locals do not express shilling amounts with decimal places.
- Do not use `Africa/Dar_es_Salaam` for Tanzania display times; it is an alias for `Africa/Nairobi` but prefer the canonical zone to avoid confusion.
- Do not cache locale-keyed data without the sub-locale (`sw` only) — the KV key must include `sw-KE` or `sw-TZ` to prevent cross-region pollution.

## Gotchas

- `Intl.DateTimeFormat('sw-KE')` month abbreviations in Workers V8 may differ from browser outputs — always validate against the CLDR 44+ reference.
- TZS has no official minor unit; `Intl.NumberFormat` will default `minimumFractionDigits: 2` for currency style unless explicitly overridden to `0`.
- East Africa Time (EAT, UTC+3) has no daylight-saving transitions — `timeZone: 'Africa/Nairobi'` is safe year-round for both Kenya and Tanzania.
- The Swahili word for "yesterday" (*jana*) and "tomorrow" (*kesho*) are produced correctly by `Intl.RelativeTimeFormat` but only when `numeric: 'auto'` is set.
- `narrowSymbol` for KES renders `KSh` in most environments; `symbol` renders `KES` — test in the Workers preview to confirm the expected output.

## Verification

1. Deploy a test Worker that calls `formatSwahiliDate`, `formatSwahiliCurrency`, and `formatSwahiliRelativeTime` for both `sw-KE` and `sw-TZ`.
2. Assert that `sw-TZ` currency output contains `TSh` (not `KSh`).
3. Assert month names are in Kiswahili (e.g., *Agosti* for August, *Januari* for January).
4. Assert `formatSwahiliRelativeTime(-3600, 'sw-KE')` contains *saa* (hour in Swahili).
5. Run `wrangler dev --local` and exercise the KV cache path to confirm TTL writes do not block the response.

## Related

- [swahili-localization-workers-d1.md](swahili-localization-workers-d1.md) — D1 schema design and collation for Swahili content
- [currency-formatting-cloudflare-workers-intl-numberformat.md](currency-formatting-cloudflare-workers-intl-numberformat.md) — general currency formatting patterns
- [intl-segmenter-cloudflare-workers-text-processing.md](intl-segmenter-cloudflare-workers-text-processing.md) — text segmentation for Swahili word boundaries
- [translation-kv-caching-ttl-strategy.md](translation-kv-caching-ttl-strategy.md) — KV TTL design for i18n data
- [locale-negotiation-accept-language.md](locale-negotiation-accept-language.md) — Accept-Language negotiation in Workers

## Sources

- CLDR Locale Data — Swahili (sw): https://github.com/unicode-org/cldr/tree/main/common/main
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- MDN Intl.NumberFormat currency: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- Cloudflare Workers Runtime APIs — KV: https://developers.cloudflare.com/kv/
- IANA Language Subtag Registry (sw): https://www.iana.org/assignments/language-subtag-registry
- Unicode CLDR Plural Rules (Swahili): https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
