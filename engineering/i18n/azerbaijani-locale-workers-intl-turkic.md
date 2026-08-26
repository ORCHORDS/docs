# Azerbaijani Locale: Cloudflare Workers Intl for Turkic Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) is gaining users in Azerbaijan and the Azerbaijani diaspora in Russia and Iran. Anonymous post timestamps showing `Aug 23, 2026` and currency amounts in plain integers alienate users who expect Azerbaijani month names and the Azerbaijani Manat symbol. Formatting these values at the Workers edge — using `Intl` APIs — avoids shipping locale data to the client and keeps the anonymity model intact.

## Context

Azerbaijani (Azərbaycan dili) is a Turkic language written in the Latin script in Azerbaijan (`az-AZ`, also written as `az-Latn-AZ`). A Cyrillic variant (`az-Cyrl`) exists in some post-Soviet communities but is very rare; this article covers the standard Latin-script variant. Azerbaijani uses a comma as the decimal separator, a period (or non-breaking space) as the thousands separator, and the Azerbaijani Manat (AZN, symbol `₼`) as its currency. The ICU data for `az` is well-supported in Cloudflare Workers' V8 runtime.

## Locale Configuration in Workers

The recommended tag is `az-AZ` (or `az-Latn-AZ` with explicit script). For most example project use cases, `az-AZ` is sufficient. Detect from `cf.country` or a locale cookie; fall back to `az-AZ`.

```typescript
// src/lib/locale-az.ts
export type AzerbaijaniScript = 'Latn' | 'Cyrl';

export interface AzerbaijaniLocaleConfig {
  tag: string;
  script: AzerbaijaniScript;
  currency: 'AZN';
  timeZone: string;
}

export function resolveAzerbaijaniLocale(
  request: Request,
  cookieLocale?: string
): AzerbaijaniLocaleConfig {
  // Honour an explicit cookie locale
  if (cookieLocale === 'az-Cyrl-AZ') {
    return { tag: 'az-Cyrl-AZ', script: 'Cyrl', currency: 'AZN', timeZone: 'Asia/Baku' };
  }
  // Default to Latin-script Azerbaijani
  return { tag: 'az-AZ', script: 'Latn', currency: 'AZN', timeZone: 'Asia/Baku' };
}

export function assertAzerbaijaniTag(tag: string): string {
  const valid = ['az-AZ', 'az-Latn-AZ', 'az-Cyrl-AZ', 'az'];
  if (valid.includes(tag)) return tag;
  throw new RangeError(`Unsupported Azerbaijani locale tag: ${tag}`);
}

// Check that the runtime supports az-AZ formatting
export function azerbaijaniLocaleSupported(): boolean {
  try {
    const s = new Intl.DateTimeFormat('az-AZ').format(new Date());
    return s.length > 0;
  } catch {
    return false;
  }
}
```

## Date and Time Formatting

Azerbaijani month names in Latin script are distinct from Turkish (e.g., *avqust* for August, *oktyabr* for October). Date order is `d MMMM yyyy` for long style and `dd.MM.yyyy` for short style — the period-delimited DMY short format is shared with most post-Soviet Turkic locales.

```typescript
// src/lib/date-az.ts
export function formatAzerbaijaniDate(
  date: Date,
  config: AzerbaijaniLocaleConfig,
  style: 'full' | 'long' | 'medium' | 'short' = 'long'
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: style,
    timeZone: config.timeZone,
  }).format(date);
}

export function formatAzerbaijaniDateTime(
  date: Date,
  config: AzerbaijaniLocaleConfig
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: 'long',
    timeStyle: 'short',
    // Azerbaijan Time: UTC+4 (UTC+5 in summer — AZST observed)
    timeZone: config.timeZone,
  }).format(date);
}

export function formatAzerbaijaniRelativeTime(
  diffSeconds: number,
  config: AzerbaijaniLocaleConfig
): string {
  const rtf = new Intl.RelativeTimeFormat(config.tag, { numeric: 'auto' });
  const abs = Math.abs(diffSeconds);
  if (abs < 60)    return rtf.format(Math.round(diffSeconds), 'second');
  if (abs < 3600)  return rtf.format(Math.round(diffSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
  return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

// formatAzerbaijaniDate(new Date('2026-08-23'), config, 'long')
//   => "23 avqust 2026"
// formatAzerbaijaniDate(new Date('2026-08-23'), config, 'short')
//   => "23.08.26"
// formatAzerbaijaniRelativeTime(-120, config)
//   => "2 dəqiqə əvvəl"
```

## Number and Currency Formatting

The Azerbaijani Manat (AZN) uses `₼` as its symbol (U+20BC). `Intl.NumberFormat` places the symbol after the amount in Azerbaijani convention. Use 2 decimal places (qəpik = 1/100 AZN).

```typescript
// src/lib/currency-az.ts
export function formatAzerbaijaniCurrency(
  amount: number,
  config: AzerbaijaniLocaleConfig,
  display: 'narrowSymbol' | 'symbol' | 'code' = 'narrowSymbol'
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'currency',
    currency: config.currency,   // 'AZN'
    currencyDisplay: display,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatAzerbaijaniDecimal(
  value: number,
  config: AzerbaijaniLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'decimal',
    useGrouping: true,
  }).format(value);
}

export function formatAzerbaijaniPercent(
  ratio: number,
  config: AzerbaijaniLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(ratio);
}

// formatAzerbaijaniCurrency(1234.5, config)
//   => "1.234,50 ₼"  (symbol after amount, period thousands, comma decimal)
// formatAzerbaijaniDecimal(9876543, config)
//   => "9.876.543"
// formatAzerbaijaniPercent(0.123, config)
//   => "12,3%"
```

## Text Handling and Plural Rules

Azerbaijani, like most Turkic languages, has only two CLDR plural categories: `one` (n = 1) and `other` (everything else). This is the same simple binary split as English and makes ICU plural message formatting straightforward. However, Azerbaijani has vowel harmony that affects suffix forms — these are handled in translation strings, not in the `Intl` API.

```typescript
// src/lib/plural-az.ts
export function azerbaijaniPluralCategory(
  n: number,
  config: AzerbaijaniLocaleConfig
): Intl.LDMLPluralRule {
  return new Intl.PluralRules(config.tag).select(n);
}

export function formatAzerbaijaniPostCount(
  count: number,
  config: AzerbaijaniLocaleConfig
): string {
  const category = azerbaijaniPluralCategory(count, config);
  const formatted = formatAzerbaijaniDecimal(count, config);
  // Azerbaijani: "1 yazı" (post), "N yazı" (posts — no plural inflection on noun)
  return `${formatted} yazı`;
}

export function formatAzerbaijaniList(
  items: string[],
  config: AzerbaijaniLocaleConfig,
  type: 'conjunction' | 'disjunction' = 'conjunction'
): string {
  return new Intl.ListFormat(config.tag, { type, style: 'long' }).format(items);
}

// Note: Azerbaijani nouns do not inflect for number; the plural marker
// ("-lar"/"-lər") is not produced by Intl.PluralRules — it must be in translation strings.
// Vowel harmony variant (-lar vs -lər) depends on the stem's last vowel and
// must be encoded per-noun in the message catalog.

export function formatAzerbaijaniDisplayName(
  code: string,
  type: 'language' | 'region' | 'currency',
  config: AzerbaijaniLocaleConfig
): string {
  const dn = new Intl.DisplayNames([config.tag], { type });
  return dn.of(code) ?? code;
}
```

## KV Caching for Azerbaijani Locale Data

Cache formatted output keyed by locale tag. Because Azerbaijani has DST transitions (AZST, UTC+5 in summer), relative timestamp caching TTL should be short to avoid showing the wrong UTC offset window in future posts.

```typescript
// src/lib/kv-az.ts
interface Env {
  LOCALE_CACHE: KVNamespace;
}

// AZN symbol and date format strings are stable — long TTL
const TTL_STATIC = 86_400;
// Relative times change every second by definition — very short TTL
const TTL_RELATIVE = 30;

export async function getCachedAzerbaijaniFormat(
  env: Env,
  logicalKey: string,
  config: AzerbaijaniLocaleConfig,
  compute: () => string,
  ttl = TTL_STATIC
): Promise<string> {
  const cacheKey = `i18n:${config.tag}:${logicalKey}`;
  const hit = await env.LOCALE_CACHE.get(cacheKey);
  if (hit !== null) return hit;

  const value = compute();
  // Non-blocking write
  env.LOCALE_CACHE.put(cacheKey, value, { expirationTtl: ttl });
  return value;
}

// Worker fetch handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cookie = request.headers.get('Cookie') ?? '';
    const localeMatch = cookie.match(/locale=([^;]+)/);
    const config = resolveAzerbaijaniLocale(request, localeMatch?.[1]);

    const now = Date.now();
    const postTs = now - 7200_000; // 2 hours ago
    const diffSec = (postTs - now) / 1000;

    const [dateStr, relStr, amountStr] = await Promise.all([
      getCachedAzerbaijaniFormat(env, `date:${Math.floor(postTs / 60000)}`, config,
        () => formatAzerbaijaniDateTime(new Date(postTs), config), TTL_STATIC),
      getCachedAzerbaijaniFormat(env, `rel:${Math.floor(diffSec / 60)}`, config,
        () => formatAzerbaijaniRelativeTime(diffSec, config), TTL_RELATIVE),
      getCachedAzerbaijaniFormat(env, 'azn:500', config,
        () => formatAzerbaijaniCurrency(500, config), TTL_STATIC),
    ]);

    return new Response(JSON.stringify({ date: dateStr, relative: relStr, amount: amountStr }), {
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  },
};
```

## Anti-patterns

- Do not use `tr-TR` (Turkish) as a fallback for Azerbaijani — month names, decimal formatting conventions, and inflection patterns differ.
- Do not strip the `₼` symbol (U+20BC) from formatted output — it was assigned to Manat specifically to replace the ambiguous `m` abbreviation; always preserve it.
- Do not ignore DST for Azerbaijani time display — AZT (UTC+4) shifts to AZST (UTC+5) in summer; always pass `timeZone: 'Asia/Baku'` and let `Intl` resolve the correct offset.
- Do not cache formatted Azerbaijani strings under a generic `az` key when the locale tag is `az-AZ` — keep the full tag in the cache key.
- Do not attempt to handle Azerbaijani vowel harmony in `Intl` code — it belongs in the translation catalog strings, not in the formatting layer.

## Gotchas

- `az-AZ` and `az-Latn-AZ` resolve to the same ICU locale data; either tag is acceptable, but `az-AZ` is shorter and more commonly used.
- Azerbaijani uses the Latin letter `ə` (U+0259, schwa) in its alphabet — do not confuse it with `e` when filtering or normalising locale output strings.
- The Manat symbol `₼` (U+20BC) was added to Unicode in version 6.2 (2012); confirm it renders in the target font stack before relying on it in the UI.
- `Intl.DisplayNames` for `az-AZ` returns Azerbaijani-language names for currencies, languages, and regions — useful for building locale-aware dropdown menus on example project's settings screen.
- `Intl.RelativeTimeFormat` with `numeric: 'auto'` in Azerbaijani produces *bu gün* (today), *dünən* (yesterday), *sabah* (tomorrow) — verify these strings against native speaker expectations before shipping.

## Verification

1. Assert `formatAzerbaijaniDate(new Date('2026-08-23'), config, 'long')` contains `avqust`.
2. Assert `formatAzerbaijaniCurrency(1500.75, config)` contains `₼` and a comma decimal separator.
3. Assert `formatAzerbaijaniRelativeTime(-7200, config)` contains `saat` (hour in Azerbaijani).
4. Assert `formatAzerbaijaniList(['Əli', 'Leyla', 'Orxan'], config)` produces the correct Azerbaijani conjunction.
5. Test DST by formatting a datetime known to fall in summer (AZST, UTC+5) and confirming the hour is one ahead of a winter datetime at the same UTC time.

## Related

- [bcp47-language-tag-syntax.md](bcp47-language-tag-syntax.md) — script subtags (`az-Latn-AZ` vs `az-Cyrl-AZ`)
- [locale-fallback-chain.md](locale-fallback-chain.md) — fallback from `az-AZ` → `az`
- [currency-formatting-cloudflare-workers-intl-numberformat.md](currency-formatting-cloudflare-workers-intl-numberformat.md) — general currency formatting patterns
- [translation-kv-caching-ttl-strategy.md](translation-kv-caching-ttl-strategy.md) — KV TTL design
- [locale-negotiation-accept-language.md](locale-negotiation-accept-language.md) — Accept-Language negotiation

## Sources

- CLDR Locale Data — Azerbaijani (az): https://github.com/unicode-org/cldr/tree/main/common/main
- Unicode CLDR Plural Rules (Azerbaijani): https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- MDN Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN Intl.RelativeTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat
- Cloudflare Workers Runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/
- IANA Language Subtag Registry (az): https://www.iana.org/assignments/language-subtag-registry
- Unicode Manat sign U+20BC: https://www.unicode.org/charts/PDF/U20A0.pdf
