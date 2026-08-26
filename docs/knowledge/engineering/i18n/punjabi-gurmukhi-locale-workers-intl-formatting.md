# Punjabi Gurmukhi Locale: Cloudflare Workers Intl Formatting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) is onboarding users from Punjab (India) and the Punjabi diaspora who write in Gurmukhi script. Displaying post timestamps, reply counts, and community tip amounts in English-formatted numbers looks foreign to these users. Serving locale-aware Punjabi output from Cloudflare Workers — without a client-side polyfill — improves authenticity and reduces churn for a community that values script fidelity.

## Context

Punjabi written in Gurmukhi script uses the BCP 47 tag `pa-IN` (India) or `pa-Guru-IN` (explicit Gurmukhi script subtag). The Gurmukhi numeral system (`guru`) spans U+0A66–U+0A6F (੦–੯) and is commonly preferred in print; digital interfaces often default to Latin numerals but expose a numeral-system toggle. Punjabi in Pakistan is written in Shahmukhi (Perso-Arabic) script with the tag `pa-Arab-PK` — that variant is left-to-right in numeric context but requires RTL layout; this article covers the Gurmukhi/`pa-IN` variant only.

## Locale Configuration in Workers

Use `pa-Guru-IN` as the canonical tag for Gurmukhi Punjabi to avoid ambiguity with the Shahmukhi variant. The `-u-nu-guru` extension requests Gurmukhi digits; omit it for Latin digits.

```typescript
// src/lib/locale-pa.ts
export type PunjabiNumeralSystem = 'guru' | 'latn';

export interface PunjabiLocaleConfig {
  tag: string;
  script: 'Guru';
  numeralSystem: PunjabiNumeralSystem;
}

export function resolvePunjabiLocale(
  request: Request,
  preferredNu?: string
): PunjabiLocaleConfig {
  const nu: PunjabiNumeralSystem =
    preferredNu === 'guru' ? 'guru' : 'latn';
  const tag = nu === 'guru' ? 'pa-Guru-IN-u-nu-guru' : 'pa-Guru-IN';
  return { tag, script: 'Guru', numeralSystem: nu };
}

export function buildPunjabiTag(nu: PunjabiNumeralSystem): string {
  return nu === 'guru' ? 'pa-Guru-IN-u-nu-guru' : 'pa-Guru-IN';
}

// Feature-detect Gurmukhi numeral support at runtime
export function gurmukhiNumeralsSupported(): boolean {
  try {
    const sample = new Intl.NumberFormat('pa-Guru-IN-u-nu-guru').format(1);
    // Should contain a Gurmukhi digit U+0A67 (੧)
    return /[੦-੯]/.test(sample);
  } catch {
    return false;
  }
}
```

## Date and Time Formatting

Punjabi uses the Gregorian calendar for digital contexts. Month names and day names in Gurmukhi are provided by CLDR. The time zone for India is `Asia/Kolkata` (IST, UTC+5:30, no DST).

```typescript
// src/lib/date-pa.ts
export function formatPunjabiDate(
  date: Date,
  config: PunjabiLocaleConfig,
  style: 'full' | 'long' | 'medium' | 'short' = 'medium'
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: style,
    calendar: 'gregory',
  }).format(date);
}

export function formatPunjabiDateTime(
  date: Date,
  config: PunjabiLocaleConfig
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
    calendar: 'gregory',
  }).format(date);
}

export function formatPunjabiRelativeTime(
  diffSeconds: number,
  config: PunjabiLocaleConfig
): string {
  const rtf = new Intl.RelativeTimeFormat(config.tag, { numeric: 'auto' });
  const abs = Math.abs(diffSeconds);
  if (abs < 60)    return rtf.format(Math.round(diffSeconds), 'second');
  if (abs < 3600)  return rtf.format(Math.round(diffSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
  return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

// With Gurmukhi numerals (pa-Guru-IN-u-nu-guru):
//   formatPunjabiDate(new Date('2026-08-23'), config)
//   => "੨੩ ਅਗਸਤ ੨੦੨੬"
// With Latin numerals (pa-Guru-IN):
//   => "23 ਅਗਸਤ 2026"
```

## Number and Currency Formatting

India's currency is the Indian Rupee (INR). Punjabi locale uses the Indian grouping system: groups of two digits after the first group of three (e.g., 12,34,567). `Intl.NumberFormat` handles this automatically when the locale is `pa-Guru-IN` — no manual grouping logic is required.

```typescript
// src/lib/currency-pa.ts
export function formatPunjabiCurrency(
  amount: number,
  config: PunjabiLocaleConfig,
  display: 'narrowSymbol' | 'symbol' | 'code' = 'narrowSymbol'
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'currency',
    currency: 'INR',
    currencyDisplay: display,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatPunjabiDecimal(
  value: number,
  config: PunjabiLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'decimal',
  }).format(value);
}

export function formatPunjabiPercent(
  ratio: number,
  config: PunjabiLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(ratio);
}

// formatPunjabiCurrency(1234567, { tag: 'pa-Guru-IN', numeralSystem: 'latn', script: 'Guru' })
//   => "₹12,34,567"  (Indian grouping)
// formatPunjabiCurrency(1234567, { tag: 'pa-Guru-IN-u-nu-guru', numeralSystem: 'guru', script: 'Guru' })
//   => "₹੧੨,੩੪,੫੬੭"
```

## Text Handling and Plural Rules

Punjabi has a `one` / `other` plural split identical to English for cardinal numbers. Ordinal numbers however use a different suffix pattern in Gurmukhi. Use `Intl.PluralRules` for cardinal counts and provide Gurmukhi-appropriate suffix strings for ordinals.

```typescript
// src/lib/plural-pa.ts
export function punjabiPluralCategory(
  n: number,
  config: PunjabiLocaleConfig
): Intl.LDMLPluralRule {
  return new Intl.PluralRules(config.tag).select(n);
}

export function formatPunjabiPostCount(
  count: number,
  config: PunjabiLocaleConfig
): string {
  const category = punjabiPluralCategory(count, config);
  const formatted = formatPunjabiDecimal(count, config);
  // "ਪੋਸਟ" = post in Punjabi
  return category === 'one'
    ? `${formatted} ਪੋਸਟ`
    : `${formatted} ਪੋਸਟਾਂ`;
}

export function formatPunjabiOrdinal(
  n: number,
  config: PunjabiLocaleConfig
): string {
  const pr = new Intl.PluralRules(config.tag, { type: 'ordinal' });
  const category = pr.select(n);
  const formatted = formatPunjabiDecimal(n, config);
  // Gurmukhi ordinal suffixes from CLDR
  const suffixes: Record<Intl.LDMLPluralRule, string> = {
    one: 'ਲਾ', other: 'ਵਾਂ', zero: 'ਵਾਂ', two: 'ਵਾਂ', few: 'ਵਾਂ', many: 'ਵਾਂ',
  };
  return `${formatted}${suffixes[category]}`;
}

export function formatPunjabiList(
  items: string[],
  config: PunjabiLocaleConfig
): string {
  return new Intl.ListFormat(config.tag, {
    type: 'conjunction',
    style: 'long',
  }).format(items);
}
```

## KV Caching for Punjabi Locale Data

Store formatted values with a key that encodes both the script and numeral system. Because Gurmukhi and Latin numeral variants produce completely different strings, a single miss on numeral system results in serving the wrong script to users.

```typescript
// src/lib/kv-pa.ts
interface Env {
  LOCALE_CACHE: KVNamespace;
}

const TTL_STATIC = 86_400;   // 24 h — currency symbols, date formats
const TTL_RELATIVE = 30;     // 30 s — relative timestamps

export async function getCachedPunjabiFormat(
  env: Env,
  logicalKey: string,
  config: PunjabiLocaleConfig,
  compute: () => string,
  ttl = TTL_STATIC
): Promise<string> {
  // Include full BCP 47 tag to separate Guru-latn from Guru-guru variants
  const cacheKey = `i18n:${config.tag}:${logicalKey}`;
  const hit = await env.LOCALE_CACHE.get(cacheKey);
  if (hit !== null) return hit;

  const value = compute();
  env.LOCALE_CACHE.put(cacheKey, value, { expirationTtl: ttl });
  return value;
}

// Worker handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const nu = url.searchParams.get('nu') ?? 'latn';
    const config = resolvePunjabiLocale(request, nu);

    const amount = 50_000;
    const formatted = await getCachedPunjabiFormat(
      env,
      `inr:${amount}`,
      config,
      () => formatPunjabiCurrency(amount, config)
    );

    return new Response(JSON.stringify({ amount: formatted }), {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'private, max-age=300',
        'Vary': 'Cookie',
      },
    });
  },
};
```

## Anti-patterns

- Do not use the bare `pa` tag — it is ambiguous between Gurmukhi and Shahmukhi scripts; always use `pa-Guru-IN` or `pa-Arab-PK`.
- Do not hardcode Indian number grouping (e.g., inserting commas manually at positions 3, 5, 7) — `Intl.NumberFormat` handles it automatically and correctly.
- Do not cache Gurmukhi-numeral output under a Latin-numeral cache key — the KV key must include the full BCP 47 tag.
- Do not assume INR has no subunits; it does (paise = 1/100 INR), but tip/coin UI on example project should use `maximumFractionDigits: 0` because paise are not used in everyday transactions above ₹1.
- Do not apply RTL layout to Gurmukhi (`pa-Guru-IN` is LTR); only `pa-Arab-PK` (Shahmukhi) requires RTL.

## Gotchas

- `gurmukhiNumeralsSupported()` may return `false` on older Workers runtime snapshots where `pa-Guru-IN-u-nu-guru` is not fully resolved — fall back to `pa-Guru-IN` (Latin digits) gracefully.
- The Indian number grouping system (lakh/crore: `1,00,000` for 100,000) only activates when the locale is `pa-IN` or `pa-Guru-IN`; using `en-IN` produces a different symbol but the same grouping.
- `Intl.RelativeTimeFormat` for Punjabi may return strings with zero-width joiners (ZWJ, U+200D) in the Gurmukhi output — these are semantically significant and must not be stripped.
- Gurmukhi digits ੦–੯ (U+0A66–U+0A6F) are distinct from Devanagari digits ०–९ (U+0966–U+096F); do not conflate them in regex character classes.
- IST (UTC+5:30) has no DST transitions — `timeZone: 'Asia/Kolkata'` is safe year-round.

## Verification

1. Assert `formatPunjabiDecimal(1234567, { tag: 'pa-Guru-IN', ... })` produces `1,23,45,67` — wait, correct: `12,34,567` (three then groups of two).
2. Assert `formatPunjabiDecimal(1234567, { tag: 'pa-Guru-IN-u-nu-guru', ... })` contains codepoints in U+0A66–U+0A6F.
3. Assert `formatPunjabiCurrency(500, config)` contains `₹` (U+20B9).
4. Assert `formatPunjabiRelativeTime(-90, config)` returns a non-empty Gurmukhi or mixed string.
5. Test KV cache isolation: write a value with `latn` tag, then assert the `guru` tag key returns a cache miss (forcing recompute).

## Related

- [devanagari-hindi-locale-workers-intl-formatting.md](devanagari-hindi-locale-workers-intl-formatting.md) — parallel article for Hindi/Devanagari
- [indic-script-rendering.md](indic-script-rendering.md) — rendering Indic complex scripts
- [number-system-locale-workers-d1.md](number-system-locale-workers-d1.md) — storing locale numeral preferences in D1
- [currency-formatting-cloudflare-workers-intl-numberformat.md](currency-formatting-cloudflare-workers-intl-numberformat.md) — general currency formatting
- [translation-kv-caching-ttl-strategy.md](translation-kv-caching-ttl-strategy.md) — KV TTL design patterns

## Sources

- CLDR Locale Data — Punjabi Gurmukhi (pa-Guru): https://github.com/unicode-org/cldr/tree/main/common/main
- Unicode CLDR Plural Rules (Punjabi): https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- Unicode Gurmukhi block: https://www.unicode.org/charts/PDF/U0A00.pdf
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- BCP 47 script subtags: https://www.iana.org/assignments/language-subtag-registry
