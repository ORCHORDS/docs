# Edge-Side Currency Formatting Using Intl.NumberFormat in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Prices arrive from your API as raw numbers (`1299.99`). The client renders them — but different users see different currencies, decimal conventions, and grouping separators depending on locale. Doing this in the browser causes a flash of unformatted numbers and requires shipping formatting logic to every client. You want prices to arrive pre-formatted, correctly, without adding an origin service.

---

## Context

`Intl.NumberFormat` is part of the ECMAScript Internationalisation API and is fully available inside the Cloudflare Workers runtime (V8-backed, compatibility date 2022-03-21 or later). It handles:

- Currency symbol placement (prefix vs. suffix)
- Decimal and thousands separators by locale
- Correct fraction digit counts per currency (JPY: 0, KWD: 3, USD: 2)
- Narrow/standard/accounting sign display

Formatting at the edge means the HTML that reaches the browser already contains `¥1,299` or `1.299,00 €` — no JS hydration needed for prices, which reduces layout shift and improves CWV scores.

---

## Solution

### 1. Currency Resolution — Locale to Currency Code

```typescript
// src/i18n/currency.ts

/**
 * Map of BCP 47 region subtags to ISO 4217 currency codes.
 * Only the most commercially significant regions are listed;
 * extend as needed.
 */
export const REGION_TO_CURRENCY: Record<string, string> = {
  US: 'USD', CA: 'CAD', GB: 'GBP', AU: 'AUD', NZ: 'NZD',
  EU: 'EUR', // virtual region used as fallback for Eurozone
  DE: 'EUR', FR: 'EUR', IT: 'EUR', ES: 'EUR', NL: 'EUR',
  JP: 'JPY', CN: 'CNY', KR: 'KRW', IN: 'INR',
  SA: 'SAR', AE: 'AED', KW: 'KWD', BH: 'BHD',
  BR: 'BRL', MX: 'MXN', AR: 'ARS',
  CH: 'CHF', SE: 'SEK', NO: 'NOK', DK: 'DKK',
  PL: 'PLN', CZ: 'CZK', HU: 'HUF', RO: 'RON',
  IL: 'ILS', TR: 'TRY', ZA: 'ZAR', NG: 'NGN',
};

/**
 * Derive the ISO 4217 currency code from a BCP 47 locale string.
 * Extracts the region subtag (e.g., "en-GB" → "GB" → "GBP").
 * Falls back to USD when region is absent or unmapped.
 */
export function currencyFromLocale(locale: string): string {
  const parts = locale.split('-');
  // Region subtag is the second segment when it is 2 uppercase letters
  const region = parts.find((p) => /^[A-Z]{2}$/.test(p));
  return (region && REGION_TO_CURRENCY[region]) ?? 'USD';
}
```

### 2. KV-Stored User Currency Preference

```typescript
// src/i18n/prefs.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface CurrencyPrefs {
  currencyCode: string;
  locale: string;
}

export async function getUserCurrencyPrefs(
  sessionId: string | null,
  defaultLocale: string,
  kv: KVNamespace,
): Promise<CurrencyPrefs> {
  if (sessionId) {
    const raw = await kv.get(`currency:${sessionId}`, 'json') as
      | { currencyCode?: string; locale?: string }
      | null;
    if (raw?.currencyCode) {
      return {
        currencyCode: raw.currencyCode,
        locale: raw.locale ?? defaultLocale,
      };
    }
  }

  const { currencyFromLocale } = await import('./currency');
  return {
    currencyCode: currencyFromLocale(defaultLocale),
    locale: defaultLocale,
  };
}
```

### 3. Intl.NumberFormat Wrapper with Per-Currency Rules

```typescript
// src/i18n/format-currency.ts

interface FormatOptions {
  locale: string;
  currencyCode: string;
  /** Override fraction digits. Omit to use ISO 4217 defaults. */
  fractionDigits?: number;
  /** 'standard' | 'accounting' — accounting wraps negatives in parentheses */
  signDisplay?: 'auto' | 'never' | 'always' | 'exceptZero';
  currencyDisplay?: 'symbol' | 'narrowSymbol' | 'code' | 'name';
}

/**
 * Currencies where ISO 4217 specifies zero minor units.
 * Intl.NumberFormat usually handles this automatically,
 * but explicitly listing them guards against runtime edge cases.
 */
const ZERO_DECIMAL_CURRENCIES = new Set([
  'BIF', 'BYR', 'CLP', 'DJF', 'GNF', 'ISK', 'JPY',
  'KMF', 'KRW', 'MGA', 'PYG', 'RWF', 'UGX', 'UYI',
  'VND', 'VUV', 'XAF', 'XOF', 'XPF',
]);

/**
 * Currencies with 3 minor units (1/1000 of the major unit).
 */
const THREE_DECIMAL_CURRENCIES = new Set([
  'BHD', 'IQD', 'JOD', 'KWD', 'LYD', 'OMR', 'TND',
]);

function getDefaultFractionDigits(currencyCode: string): {
  minimumFractionDigits: number;
  maximumFractionDigits: number;
} {
  if (ZERO_DECIMAL_CURRENCIES.has(currencyCode)) {
    return { minimumFractionDigits: 0, maximumFractionDigits: 0 };
  }
  if (THREE_DECIMAL_CURRENCIES.has(currencyCode)) {
    return { minimumFractionDigits: 3, maximumFractionDigits: 3 };
  }
  return { minimumFractionDigits: 2, maximumFractionDigits: 2 };
}

/**
 * Format a numeric amount as a localised currency string.
 *
 * @example
 * formatCurrency(1299.99, { locale: 'de-DE', currencyCode: 'EUR' })
 * // → "1.299,99 €"
 *
 * formatCurrency(1299, { locale: 'ja-JP', currencyCode: 'JPY' })
 * // → "¥1,299"
 *
 * formatCurrency(1.500, { locale: 'ar-KW', currencyCode: 'KWD' })
 * // → "1.500 د.ك."
 */
export function formatCurrency(
  amount: number,
  opts: FormatOptions,
): string {
  const fractionOverride = opts.fractionDigits !== undefined
    ? { minimumFractionDigits: opts.fractionDigits, maximumFractionDigits: opts.fractionDigits }
    : getDefaultFractionDigits(opts.currencyCode);

  const formatter = new Intl.NumberFormat(opts.locale, {
    style: 'currency',
    currency: opts.currencyCode,
    currencyDisplay: opts.currencyDisplay ?? 'symbol',
    signDisplay: opts.signDisplay ?? 'auto',
    ...fractionOverride,
  });

  return formatter.format(amount);
}

/**
 * Format a range of prices (e.g., "$10 – $20") using
 * Intl.NumberFormat.prototype.formatRange where available.
 */
export function formatCurrencyRange(
  min: number,
  max: number,
  opts: FormatOptions,
): string {
  const fractionOverride = getDefaultFractionDigits(opts.currencyCode);
  const formatter = new Intl.NumberFormat(opts.locale, {
    style: 'currency',
    currency: opts.currencyCode,
    currencyDisplay: opts.currencyDisplay ?? 'symbol',
    ...fractionOverride,
  }) as Intl.NumberFormat & { formatRange?(a: number, b: number): string };

  if (typeof formatter.formatRange === 'function') {
    return formatter.formatRange(min, max);
  }
  // Fallback for runtimes without formatRange
  return `${formatter.format(min)} – ${formatter.format(max)}`;
}
```

### 4. HTMLRewriter — Server-Side Price Rendering

```typescript
// src/i18n/price-rewriter.ts
import { formatCurrency } from './format-currency';

interface PriceHandlerOptions {
  locale: string;
  currencyCode: string;
}

/**
 * Rewrites elements carrying `data-price` attributes.
 *
 * Origin HTML:
 *   <span class="price" data-price="1299.99" data-currency="USD">Loading...</span>
 *
 * After rewrite:
 *   <span class="price" data-price="1299.99" data-currency="USD">$1,299.99</span>
 */
class PriceElementHandler implements HTMLRewriterElementContentHandlers {
  private readonly opts: PriceHandlerOptions;

  constructor(opts: PriceHandlerOptions) {
    this.opts = opts;
  }

  element(el: Element): void {
    const rawPrice = el.getAttribute('data-price');
    if (!rawPrice) return;

    const amount = parseFloat(rawPrice);
    if (Number.isNaN(amount)) return;

    // Allow per-element currency override via data attribute
    const elementCurrency =
      el.getAttribute('data-currency') ?? this.opts.currencyCode;

    const formatted = formatCurrency(amount, {
      locale: this.opts.locale,
      currencyCode: elementCurrency,
    });

    el.setInnerContent(formatted);
    // Signal to JS that this price was rendered server-side
    el.setAttribute('data-price-rendered', 'edge');
  }
}

export function buildPriceRewriter(
  locale: string,
  currencyCode: string,
): HTMLRewriter {
  return new HTMLRewriter().on(
    '[data-price]',
    new PriceElementHandler({ locale, currencyCode }),
  );
}
```

### 5. Caching by Locale

```typescript
// src/cache.ts
import type { KVNamespace } from '@cloudflare/workers-types';

/**
 * Cache formatted HTML responses keyed by (URL, locale, currency).
 * TTL: 5 minutes — short enough to pick up price changes, long enough
 * to absorb traffic spikes.
 */
export async function getCachedResponse(
  url: string,
  locale: string,
  currencyCode: string,
  cache: KVNamespace,
): Promise<string | null> {
  const key = `html:${url}:${locale}:${currencyCode}`;
  return cache.get(key);
}

export async function setCachedResponse(
  url: string,
  locale: string,
  currencyCode: string,
  html: string,
  cache: KVNamespace,
): Promise<void> {
  const key = `html:${url}:${locale}:${currencyCode}`;
  await cache.put(key, html, { expirationTtl: 300 }); // 5 min TTL
}
```

### 6. Worker Entry Point — Full Pipeline

```typescript
// src/index.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { parseAcceptLanguage } from './i18n/detect';
import { getUserCurrencyPrefs } from './i18n/prefs';
import { buildPriceRewriter } from './i18n/price-rewriter';
import { getCachedResponse, setCachedResponse } from './cache';

export interface Env {
  USER_PREFS: KVNamespace;
  HTML_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const sessionId = request.headers.get('x-session-id');
    const locale = parseAcceptLanguage(
      request.headers.get('accept-language'),
    );
    const prefs = await getUserCurrencyPrefs(sessionId, locale, env.USER_PREFS);

    // Cache hit
    const cached = await getCachedResponse(
      url.pathname, prefs.locale, prefs.currencyCode, env.HTML_CACHE,
    );
    if (cached) {
      return new Response(cached, {
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'x-cache': 'HIT',
        },
      });
    }

    // Fetch from origin
    const origin = await fetch(request);
    if (!origin.headers.get('content-type')?.includes('text/html')) {
      return origin;
    }

    // Apply price rewriting
    const rewriter = buildPriceRewriter(prefs.locale, prefs.currencyCode);
    const transformed = rewriter.transform(origin);
    const html = await transformed.text();

    // Store in cache
    await setCachedResponse(
      url.pathname, prefs.locale, prefs.currencyCode, html, env.HTML_CACHE,
    );

    return new Response(html, {
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'vary': 'Accept-Language',
        'x-cache': 'MISS',
        'x-i18n-locale': prefs.locale,
        'x-i18n-currency': prefs.currencyCode,
      },
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

### Intl.NumberFormat Stability in Workers

The Workers runtime (V8 + ICU) supports `Intl.NumberFormat` with full CLDR data. Fraction digit resolution is driven by ISO 4217 when you pass `style: 'currency'` — you do not need to specify `minimumFractionDigits` for most currencies. The explicit sets in `format-currency.ts` above are a safety net for unusual currencies where CLDR data may lag ISO updates.

### `Intl.NumberFormat` Caching

Constructing an `Intl.NumberFormat` instance is expensive relative to calling `.format()`. In a hot Worker, cache the formatter instance in a module-level `Map` keyed by `${locale}:${currencyCode}`:

```typescript
const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(locale: string, currencyCode: string): Intl.NumberFormat {
  const key = `${locale}:${currencyCode}`;
  if (!formatterCache.has(key)) {
    formatterCache.set(key, new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: currencyCode,
    }));
  }
  return formatterCache.get(key)!;
}
```

Module-level state persists across requests within the same isolate lifetime — this is safe for immutable formatters.

### JSONata / API Response Rewriting

If your API returns JSON with `{ "price": 1299.99, "currency": "USD" }`, you can rewrite JSON responses too:

```typescript
if (contentType.includes('application/json')) {
  const data = await response.json() as { price?: number; currency?: string }[];
  const formatted = data.map((item) => ({
    ...item,
    price_formatted: item.price != null
      ? formatCurrency(item.price, { locale, currencyCode: item.currency ?? currencyCode })
      : undefined,
  }));
  return Response.json(formatted);
}
```

---

## Anti-patterns

- **Do not use `toLocaleString()` directly on numbers without specifying `options`.** Without `style: 'currency'`, it only formats the number; currency symbols and fraction rules are ignored.
- **Never hardcode currency symbols** (`$`, `€`) in templates. The symbol position varies by locale — `$1,299` in `en-US` but `1.299 $` in some locales.
- **Do not cache at a granularity coarser than (URL, locale, currency).** A cache keyed only on URL will serve `$1,299.99` to German users expecting `1.299,99 €`.
- **Avoid rounding in the Worker.** Pass the raw float from your API to `Intl.NumberFormat`; it applies the correct rounding per currency. Pre-rounding can cause double-rounding errors.

---

## Gotchas

- `Intl.NumberFormat` for `ar` (Arabic) uses Eastern Arabic-Indic numerals (`١٢٣`) by default. To force Western Arabic numerals for all locales, use `ar-u-nu-latn` as the locale tag or set `numberingSystem: 'latn'` in options (where supported).
- KWD, BHD, and OMR have 3 decimal places. If your API stores them as integers in fils (smallest unit), divide by 1000 before formatting, not 100.
- The Workers free tier has a 10 ms CPU time limit. Formatting 500 price elements via HTMLRewriter per request is fine. Formatting 10,000 elements would breach the limit — paginate or move bulk formatting to an origin service.
- `currencyDisplay: 'narrowSymbol'` (e.g., `$` instead of `US$`) may not be supported in all Workers runtime versions. Test with your `compatibility_date`.

---

## Verification

```bash
# Start local dev
npx wrangler dev --local

# USD formatting (English US)
curl -s -H 'Accept-Language: en-US' 'http://localhost:8787/product/123' \
  | grep 'data-price-rendered'
# Expected: data-price-rendered="edge" with content like $1,299.99

# JPY — zero decimals
curl -s -H 'Accept-Language: ja-JP' 'http://localhost:8787/product/123' \
  | grep -o 'data-price-rendered.*</span>'
# Expected: ¥1,300 (no decimals)

# EUR — German grouping
curl -s -H 'Accept-Language: de-DE' 'http://localhost:8787/product/123'
# Expected: 1.299,99 €

# KWD — three decimals
curl -s -H 'Accept-Language: ar-KW' 'http://localhost:8787/product/123'
# Expected: 1.500 د.ك. (for a 1.500 KWD price)

# Cache header
curl -sI -H 'Accept-Language: en-US' 'http://localhost:8787/product/123' \
  | grep x-cache
# First: MISS, subsequent: HIT
```

---

## Related

- `workers-rtl-html-direction-edge.md` — RTL layout injection
- `workers-translation-fallback-chain-kv.md` — KV message store patterns
- `workers-geo-redirect-locale-detection.md` — locale detection
- MDN: Intl.NumberFormat
- ISO 4217 Currency Codes

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- https://www.six-group.com/en/products-services/financial-information/data-standards.html (ISO 4217)
- https://cldr.unicode.org/
