# Catalan Locale: Cloudflare Workers Intl for Iberian Regional Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) serves communities in Catalonia, Valencia, the Balearic Islands, and Andorra where Catalan (`ca`) is the primary language. Spanish (`es-ES`) formatting is not a substitute: Catalan date order, currency symbols, and decimal separators differ from Spanish conventions and using Spanish output for a Catalan-speaking community is perceived as dismissive of regional identity. The platform must produce correctly formatted Catalan output at the Workers edge.

## Context

Catalan is a Romance language co-official in Catalonia (`ca-ES`), the Valencian Community (`ca-ES-valencia`), the Balearic Islands (`ca-ES`), and the sole official language of Andorra (`ca-AD`). It uses a comma as the decimal separator and a period (or non-breaking space) as the thousands separator — the same as French and Spanish, but with distinct date formats. The currency is EUR for Spain and Andorra. Catalan is always written LTR. The CLDR `ca` locale is mature and well-covered in V8's ICU data.

## Locale Configuration in Workers

The primary tag is `ca-ES` for Spain-region Catalan. Andorra uses `ca-AD`. The Valencian variety has the variant subtag `ca-ES-valencia` but CLDR formatting data is identical to `ca-ES` for numeric/date purposes — use `ca-ES` unless string translation differs.

```typescript
// src/lib/locale-ca.ts
export type CatalanRegion = 'ES' | 'AD' | 'FR'; // Roussillon (France)

export interface CatalanLocaleConfig {
  tag: string;
  region: CatalanRegion;
  currency: 'EUR';
  timeZone: string;
}

export function resolveCatalanLocale(request: Request): CatalanLocaleConfig {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country?.toUpperCase() ?? 'ES';

  switch (country) {
    case 'AD': return { tag: 'ca-AD', region: 'AD', currency: 'EUR', timeZone: 'Europe/Andorra' };
    case 'FR': return { tag: 'ca-FR', region: 'FR', currency: 'EUR', timeZone: 'Europe/Paris' };
    default:   return { tag: 'ca-ES', region: 'ES', currency: 'EUR', timeZone: 'Europe/Madrid' };
  }
}

// Validate inbound tag from cookies/URL params
export function assertCatalanTag(tag: string): string {
  if (/^ca(-[A-Z]{2}(-[a-z]+)?)?$/.test(tag)) return tag;
  throw new RangeError(`Invalid Catalan locale tag: ${tag}`);
}
```

## Date and Time Formatting

Catalan date formatting is `d de [month] de yyyy` for long style. Short style is `d/M/yy`. Month names and day names are capitalised differently from Spanish (Catalan month names are lowercase in running text but titlecase as standalone labels — CLDR handles this automatically).

```typescript
// src/lib/date-ca.ts
export function formatCatalanDate(
  date: Date,
  config: CatalanLocaleConfig,
  style: 'full' | 'long' | 'medium' | 'short' = 'long'
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: style,
    timeZone: config.timeZone,
  }).format(date);
}

export function formatCatalanDateTime(
  date: Date,
  config: CatalanLocaleConfig
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: config.timeZone,
  }).format(date);
}

export function formatCatalanRelativeTime(
  diffSeconds: number,
  config: CatalanLocaleConfig
): string {
  const rtf = new Intl.RelativeTimeFormat(config.tag, { numeric: 'auto' });
  const abs = Math.abs(diffSeconds);
  if (abs < 60)    return rtf.format(Math.round(diffSeconds), 'second');
  if (abs < 3600)  return rtf.format(Math.round(diffSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
  return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

// formatCatalanDate(new Date('2026-08-23'), { tag: 'ca-ES', ... }, 'long')
//   => "23 d'agost de 2026"
// formatCatalanDate(new Date('2026-08-23'), ..., 'short')
//   => "23/8/26"
// formatCatalanRelativeTime(-3600, config)
//   => "fa 1 hora"
```

## Number and Currency Formatting

Catalan uses a comma decimal separator and a period thousands separator (consistent with most continental European locales). The euro symbol (`€`) follows the amount in Catalan, unlike in many other EU locales where it precedes it.

```typescript
// src/lib/currency-ca.ts
export function formatCatalanCurrency(
  amount: number,
  config: CatalanLocaleConfig,
  display: 'narrowSymbol' | 'symbol' | 'code' = 'narrowSymbol'
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'currency',
    currency: config.currency,
    currencyDisplay: display,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatCatalanDecimal(
  value: number,
  config: CatalanLocaleConfig,
  fractionDigits = 2
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'decimal',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

export function formatCatalanCompact(
  value: number,
  config: CatalanLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(value);
}

// formatCatalanCurrency(1234.5, config)        => "1.234,50 €"
// formatCatalanDecimal(9876543.21, config)      => "9.876.543,21"
// formatCatalanCompact(1_500_000, config)       => "1,5 M"
```

## Text Handling and Plural Rules

Catalan has `one` and `other` plural categories, with the same boundary as Spanish (1 = one, everything else = other). Catalan list formatting uses the Oxford-comma equivalent: `i` before the last element in conjunctions, `o` in disjunctions.

```typescript
// src/lib/plural-ca.ts
export function catalanPluralCategory(
  n: number,
  config: CatalanLocaleConfig
): Intl.LDMLPluralRule {
  return new Intl.PluralRules(config.tag).select(n);
}

export function formatCatalanPostCount(
  count: number,
  config: CatalanLocaleConfig
): string {
  const category = catalanPluralCategory(count, config);
  const formatted = new Intl.NumberFormat(config.tag).format(count);
  return category === 'one'
    ? `${formatted} publicació`
    : `${formatted} publicacions`;
}

export function formatCatalanList(
  items: string[],
  config: CatalanLocaleConfig,
  type: 'conjunction' | 'disjunction' = 'conjunction'
): string {
  return new Intl.ListFormat(config.tag, { type, style: 'long' }).format(items);
}

// CLDR Catalan conjunction: "A, B i C"
// CLDR Catalan disjunction: "A, B o C"
// formatCatalanList(['Àlex', 'Berta', 'Carles'], config)
//   => "Àlex, Berta i Carles"

export function formatCatalanOrdinal(
  n: number,
  config: CatalanLocaleConfig
): string {
  const pr = new Intl.PluralRules(config.tag, { type: 'ordinal' });
  const category = pr.select(n);
  const formatted = new Intl.NumberFormat(config.tag).format(n);
  // Catalan ordinal: masculine 1r, 2n, 3r, 4t; feminine 1a, 2a, ...
  // CLDR uses gender-neutral numeric ordinal for APIs
  const suffixes: Record<Intl.LDMLPluralRule, string> = {
    one: 'r', other: 'è', zero: 'è', two: 'n', few: 'r', many: 'è',
  };
  return `${formatted}${suffixes[category]}`;
}
```

## KV Caching for Catalan Locale Data

Cache formatted values keyed by locale tag and the logical content identifier. Catalan is a minority language with a smaller user base than Spanish; avoid over-eager TTLs that stale out region-specific formatting (Andorra uses the same EUR but different time zone).

```typescript
// src/lib/kv-ca.ts
interface Env {
  LOCALE_CACHE: KVNamespace;
}

const TTL_CURRENCY = 3_600;   // 1 h — EUR exchange rates don't affect symbol
const TTL_DATE = 86_400;      // 24 h — date format strings are stable
const TTL_RELATIVE = 30;      // 30 s — relative timestamps age quickly

export async function getCachedCatalanFormat(
  env: Env,
  logicalKey: string,
  config: CatalanLocaleConfig,
  compute: () => string,
  ttl = TTL_DATE
): Promise<string> {
  const cacheKey = `i18n:${config.tag}:${logicalKey}`;
  const cached = await env.LOCALE_CACHE.get(cacheKey);
  if (cached !== null) return cached;

  const value = compute();
  env.LOCALE_CACHE.put(cacheKey, value, { expirationTtl: ttl });
  return value;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config = resolveCatalanLocale(request);
    const postDate = new Date('2026-07-15T09:30:00Z');

    const [dateStr, currencyStr] = await Promise.all([
      getCachedCatalanFormat(env, `date:${postDate.getTime()}`, config,
        () => formatCatalanDate(postDate, config, 'long'), TTL_DATE),
      getCachedCatalanFormat(env, `eur:1500`, config,
        () => formatCatalanCurrency(1500, config), TTL_CURRENCY),
    ]);

    return new Response(JSON.stringify({ date: dateStr, amount: currencyStr }), {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Vary': 'Accept-Language',
      },
    });
  },
};
```

## Anti-patterns

- Do not use `es-ES` (Spanish) as a fallback for Catalan users — date and currency formats differ and the choice is culturally significant.
- Do not use `ca` without a region tag in production — `ca-ES` vs `ca-AD` affects the time zone for date formatting.
- Do not hardcode `€` after the amount — in some CLDR versions the placement or spacing for `ca` may be `€` before the amount depending on the `currencyDisplay` setting; let `Intl.NumberFormat` determine placement.
- Do not conflate Valencian (`ca-ES-valencia`) with standard Catalan for translation keys; keep translation catalogs separate but share the same `Intl` formatting config.
- Do not cache Catalan output under a Spanish cache key even if output looks similar — a future CLDR update could change Catalan formatting independently.

## Gotchas

- The apostrophe in `23 d'agost` uses a RIGHT SINGLE QUOTATION MARK (U+2019), not an ASCII apostrophe (U+0027) — do not replace it in post-processing.
- `Europe/Madrid` observes CET/CEST; Andorra (`Europe/Andorra`) follows the same DST schedule but is a separate zone entry — use the correct zone for each region.
- `Intl.RelativeTimeFormat` for Catalan may output `fa 1 hora` (past) but `d'aquí a 1 hora` (future) — the contracted form `d'aquí a` contains the apostrophe and must not be HTML-escaped to `&#39;`.
- In compact notation (`1,5 M`), Catalan uses the non-breaking space between the number and the suffix in some CLDR versions — always trim with Unicode-aware trimming before comparing in tests.
- Catalan ordinal suffixes are gender-inflected (masculine: 1r, 2n, 3r, 4t; feminine: 1a, 2a, 3a, 4a); `Intl.PluralRules` does not encode gender, so ordinal suffix selection from CLDR data requires a lookup table.

## Verification

1. Assert `formatCatalanDate(new Date('2026-08-23'), config, 'long')` returns a string containing `agost`.
2. Assert `formatCatalanCurrency(1234.5, config)` places `€` after the number and uses a comma decimal separator.
3. Assert `formatCatalanRelativeTime(-3600, config)` contains `hora`.
4. Assert `formatCatalanList(['gat', 'gos', 'ocell'], config)` contains ` i ` before the last item.
5. Confirm `ca-AD` config uses `Europe/Andorra` time zone by comparing DST offset output against a reference datetime.

## Related

- [locale-negotiation-accept-language.md](locale-negotiation-accept-language.md) — detecting Catalan preference from Accept-Language
- [currency-formatting-cloudflare-workers-intl-numberformat.md](currency-formatting-cloudflare-workers-intl-numberformat.md) — general EUR formatting
- [bcp47-language-tag-syntax.md](bcp47-language-tag-syntax.md) — understanding region and variant subtags
- [locale-fallback-chain.md](locale-fallback-chain.md) — fallback from `ca-ES-valencia` → `ca-ES` → `ca`
- [translation-kv-caching-ttl-strategy.md](translation-kv-caching-ttl-strategy.md) — KV TTL patterns

## Sources

- CLDR Locale Data — Catalan (ca): https://github.com/unicode-org/cldr/tree/main/common/main
- Unicode CLDR Plural Rules (Catalan): https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- MDN Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN Intl.ListFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/ListFormat
- Cloudflare Workers Runtime: https://developers.cloudflare.com/workers/runtime-apis/
- IANA Language Subtag Registry (ca): https://www.iana.org/assignments/language-subtag-registry
