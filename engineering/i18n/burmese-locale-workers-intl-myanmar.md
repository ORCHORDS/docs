# Burmese Locale: Cloudflare Workers Intl API for Myanmar

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) is expanding into Myanmar, where users expect dates, numbers, and currency to appear in Burmese (Myanmar language, `my-MM`). Anonymous posts with English-formatted timestamps or MMK amounts displayed as plain integers look unprofessional and reduce engagement. The platform must serve locale-aware formatting at the edge without shipping ICU data to the client.

## Context

Burmese (Myanmar language) uses the Myanmar script and has two numbering systems in common use: the standard Latin numerals (`latn`) and traditional Myanmar numerals (`mymr`). The `Intl` APIs in Cloudflare Workers' V8 runtime support both via the `-u-nu-` extension. Myanmar uses the Myanmar Kyat (MMK) as currency. The existing KB article `myanmar-zawgyi-unicode-conversion-workers.md` covers the Zawgyi-to-Unicode encoding problem; this article focuses on `Intl` API locale formatting once the text is already in Unicode (NFC-normalised Myanmar script).

## Locale Configuration in Workers

The BCP 47 tag is `my-MM`. To request Myanmar numerals add `-u-nu-mymr`; for Latin numerals (more common in digital UI) use the bare `my-MM` tag which defaults to `latn`. Detect the preference from a user-set cookie or fall back to country detection.

```typescript
// src/lib/locale-my.ts
export type MyanmarNumeralSystem = 'latn' | 'mymr';

export interface MyanmarLocaleConfig {
  tag: string;          // full BCP 47 tag
  numeralSystem: MyanmarNumeralSystem;
}

export function resolveMyanmarLocale(
  request: Request,
  cookieNu?: string
): MyanmarLocaleConfig {
  const nu: MyanmarNumeralSystem =
    cookieNu === 'mymr' ? 'mymr' : 'latn';
  const tag = nu === 'mymr' ? 'my-MM-u-nu-mymr' : 'my-MM';
  return { tag, numeralSystem: nu };
}

// Validate inbound locale tags from API consumers
export function assertMyanmarLocaleTag(tag: string): string {
  const valid = ['my-MM', 'my-MM-u-nu-mymr', 'my-MM-u-nu-latn'];
  if (!valid.includes(tag)) throw new RangeError(`Invalid Myanmar locale tag: ${tag}`);
  return tag;
}
```

## Date and Time Formatting

Myanmar uses the Gregorian calendar in official and digital contexts (`gregory`), but the traditional Myanmar calendar (`buddhist`-adjacent local calendar) is used culturally. For example project, use the Gregorian calendar for post timestamps and display month names in Burmese script.

```typescript
// src/lib/date-my.ts
export function formatMyanmarDate(
  date: Date,
  config: MyanmarLocaleConfig,
  style: 'full' | 'long' | 'medium' | 'short' = 'medium'
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: style,
    calendar: 'gregory',
  }).format(date);
}

export function formatMyanmarDateTime(
  date: Date,
  config: MyanmarLocaleConfig
): string {
  return new Intl.DateTimeFormat(config.tag, {
    dateStyle: 'long',
    timeStyle: 'short',
    // Myanmar Standard Time: UTC+6:30 (no DST)
    timeZone: 'Asia/Rangoon',
    calendar: 'gregory',
  }).format(date);
}

export function formatMyanmarRelativeTime(
  diffSeconds: number,
  config: MyanmarLocaleConfig
): string {
  const rtf = new Intl.RelativeTimeFormat(config.tag, { numeric: 'auto' });
  const abs = Math.abs(diffSeconds);
  if (abs < 60)    return rtf.format(Math.round(diffSeconds), 'second');
  if (abs < 3600)  return rtf.format(Math.round(diffSeconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
  return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

// With mymr numerals, date parts render in Myanmar digits (၀-၉)
// Example: formatMyanmarDate(new Date('2026-08-23'), { tag: 'my-MM-u-nu-mymr', numeralSystem: 'mymr' })
//   => "၂၀၂၆ ဩဂုတ် ၂၃"
// With latn: "2026 ဩဂုတ် 23"
```

## Number and Currency Formatting

Myanmar Kyat (MMK) does not use subunits in practice — all everyday amounts are whole kyat. Always set `maximumFractionDigits: 0`. The `narrowSymbol` display renders `K` in most CLDR data; `symbol` renders `MMK`.

```typescript
// src/lib/currency-my.ts
export function formatMyanmarCurrency(
  amount: number,
  config: MyanmarLocaleConfig,
  display: 'narrowSymbol' | 'symbol' | 'code' = 'narrowSymbol'
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'currency',
    currency: 'MMK',
    currencyDisplay: display,
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  }).format(amount);
}

export function formatMyanmarDecimal(
  value: number,
  config: MyanmarLocaleConfig,
  fractionDigits = 0
): string {
  return new Intl.NumberFormat(config.tag, {
    style: 'decimal',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

export function formatMyanmarCompact(
  value: number,
  config: MyanmarLocaleConfig
): string {
  return new Intl.NumberFormat(config.tag, {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(value);
}

// formatMyanmarCurrency(15000, { tag: 'my-MM', numeralSystem: 'latn' })
//   => "K 15,000"  (or "MMK 15,000" with display:'symbol')
// formatMyanmarCompact(1_500_000, { tag: 'my-MM-u-nu-mymr', numeralSystem: 'mymr' })
//   => Myanmar-script compact form
```

## Text Handling and Plural Rules

Burmese has no grammatical plural — the language does not inflect nouns for number. CLDR assigns `my` a single plural category: `other`. This simplifies ICU message formatting: every numeric template uses a single form.

```typescript
// src/lib/plural-my.ts
export function formatMyanmarPostCount(
  count: number,
  config: MyanmarLocaleConfig
): string {
  // Burmese: always 'other' — no singular/plural distinction
  const pr = new Intl.PluralRules(config.tag);
  const category = pr.select(count); // always 'other' for my-MM
  const formatted = formatMyanmarDecimal(count, config);

  // "N ပိုစ့်" (posts in Burmese)
  return `${formatted} ပိုစ့်`;
}

export function formatMyanmarList(
  items: string[],
  config: MyanmarLocaleConfig,
  type: 'conjunction' | 'disjunction' = 'conjunction'
): string {
  return new Intl.ListFormat(config.tag, { type, style: 'long' }).format(items);
}

// Segment Burmese text — Burmese has no spaces between words;
// Intl.Segmenter with granularity:'word' handles syllable boundaries
export function segmentBurmeseText(text: string, config: MyanmarLocaleConfig): string[] {
  const segmenter = new Intl.Segmenter(config.tag, { granularity: 'word' });
  return Array.from(segmenter.segment(text))
    .filter(s => s.isWordLike)
    .map(s => s.segment);
}
```

## KV Caching for Myanmar Locale Data

Cache formatted outputs keyed by locale tag (including the numeral extension) so Latin and Myanmar numeral variants are stored separately.

```typescript
// src/lib/kv-my.ts
interface Env {
  LOCALE_CACHE: KVNamespace;
}

export async function getCachedMyanmarFormat(
  env: Env,
  cacheKey: string,
  config: MyanmarLocaleConfig,
  compute: () => string,
  ttl = 86_400
): Promise<string> {
  // Include the full BCP 47 tag (with -u-nu- extension) in the key
  const key = `i18n:${config.tag}:${cacheKey}`;
  const hit = await env.LOCALE_CACHE.get(key);
  if (hit !== null) return hit;

  const value = compute();
  env.LOCALE_CACHE.put(key, value, { expirationTtl: ttl });
  return value;
}

// Worker entry point example
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const nuCookie = new URL(request.url).searchParams.get('nu') ?? undefined;
    const config = resolveMyanmarLocale(request, nuCookie);
    const amount = 25_000;

    const formatted = await getCachedMyanmarFormat(
      env,
      `mmk:${amount}`,
      config,
      () => formatMyanmarCurrency(amount, config)
    );

    return new Response(JSON.stringify({ currency: formatted }), {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Vary': 'Cookie',
      },
    });
  },
};
```

## Anti-patterns

- Do not use the bare `my` tag without the `MM` region subtag — CLDR subtleties around number grouping require the full tag.
- Do not mix Zawgyi and Unicode Myanmar text in the same KV value; ensure all text is Unicode before caching (see `myanmar-zawgyi-unicode-conversion-workers.md`).
- Do not assume the Myanmar numeral system is preferred by all users; default to Latin numerals and let users opt into `mymr` via a preference cookie.
- Do not display MMK with decimal places (e.g., `K 1,500.50`) — the kyat has no subunit in common use.
- Do not use `Asia/Yangon` without checking your runtime's IANA database; both `Asia/Yangon` and `Asia/Rangoon` should resolve to UTC+6:30 in modern V8.

## Gotchas

- Myanmar Standard Time (MMT) is UTC+6:30 — a non-standard 30-minute offset. Confirm that `Intl.DateTimeFormat` with `timeZone: 'Asia/Rangoon'` renders times correctly in your Workers runtime version.
- `Intl.Segmenter` with `granularity: 'word'` does not perform perfect Burmese word segmentation (Burmese has no whitespace delimiters); it is useful for syllable-level splitting but not dictionary-based word breaks.
- The Myanmar calendar (Thingyan/traditional) is NOT the `buddhist` calendar. If users ask for the traditional calendar, custom conversion logic is required — `Intl` does not expose the traditional Myanmar calendar.
- V8's CLDR data for `my-MM` may lag behind CLDR releases by a version or two; test currency symbol output after Cloudflare runtime updates.
- `narrowSymbol` for MMK may render as `K` or `MMK` depending on the CLDR version — validate in the Workers preview environment.

## Verification

1. Write a test Worker that outputs `formatMyanmarDate`, `formatMyanmarCurrency`, and `formatMyanmarRelativeTime` for both `my-MM` and `my-MM-u-nu-mymr`.
2. Assert that Myanmar numeral output contains codepoints in range U+1040–U+1049 (Myanmar digits ၀–၉).
3. Assert that `formatMyanmarCurrency(5000, { tag: 'my-MM', numeralSystem: 'latn' })` contains `5,000` without decimals.
4. Assert `formatMyanmarRelativeTime(-300, config)` produces a Burmese-script string.
5. Confirm `Asia/Rangoon` timezone renders correctly by comparing against a known UTC+6:30 reference time.

## Related

- [myanmar-zawgyi-unicode-conversion-workers.md](myanmar-zawgyi-unicode-conversion-workers.md) — Zawgyi-to-Unicode conversion at the Workers edge
- [indic-script-rendering.md](indic-script-rendering.md) — rendering considerations for complex scripts
- [intl-segmenter-cloudflare-workers-text-processing.md](intl-segmenter-cloudflare-workers-text-processing.md) — Intl.Segmenter usage in Workers
- [currency-formatting-cloudflare-workers-intl-numberformat.md](currency-formatting-cloudflare-workers-intl-numberformat.md) — general currency formatting
- [translation-kv-caching-ttl-strategy.md](translation-kv-caching-ttl-strategy.md) — KV TTL design

## Sources

- CLDR Locale Data — Burmese (my): https://github.com/unicode-org/cldr/tree/main/common/main
- Unicode CLDR Plural Rules (Burmese): https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- Cloudflare Workers Runtime: https://developers.cloudflare.com/workers/runtime-apis/
- IANA Time Zone Database — Asia/Rangoon: https://www.iana.org/time-zones
- Unicode Myanmar block: https://www.unicode.org/charts/PDF/U1000.pdf
