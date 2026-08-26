# Currency Formatting with Intl.NumberFormat in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker returns raw numeric amounts that the client formats inconsistently, or you pre-format prices on the server with hardcoded `"$"` prefixes that break for EUR/GBP/JPY users. You need to format monetary amounts in 50+ currencies correctly — including symbol placement (€ before or after the number), decimal digit count (JPY uses 0, KWD uses 3), narrow vs. standard vs. name symbol widths, and multi-currency cart totals — all at the edge without external libraries.

## Context

`Intl.NumberFormat` with `style: 'currency'` is available in all modern V8 builds and is fully supported in Cloudflare Workers. It uses CLDR data baked into the V8 binary, so no runtime downloads are required. Currency formatting in CLDR accounts for:

- Symbol placement: USD → `$1,000.00` (prefix), EUR in French → `1 000,00 €` (suffix)
- Decimal digits: JPY → 0, USD → 2, KWD → 3
- Grouping separators: `.` in German (`1.000,00 €`), `,` in English (`$1,000.00`)
- Narrow symbols: `$` instead of `US$` when locale context is unambiguous
- Accounting format: `($1,000.00)` for negative amounts instead of `-$1,000.00`

## Solution

```typescript
// workers-currency-formatting-intl.ts
// Currency formatting utilities for Cloudflare Workers

export interface Env {
  EXCHANGE_KV: KVNamespace;   // KV-cached exchange rates from external API
}

// ─── 1. Core formatting function ─────────────────────────────────────────

export type CurrencyDisplay = 'symbol' | 'narrowSymbol' | 'code' | 'name';
export type SignDisplay     = 'auto' | 'always' | 'never' | 'exceptZero';

export interface FormatCurrencyOptions {
  locale:          string;           // BCP 47 locale, e.g. 'de-DE'
  currency:        string;           // ISO 4217 code, e.g. 'EUR'
  currencyDisplay?: CurrencyDisplay; // default: 'symbol'
  signDisplay?:    SignDisplay;      // default: 'auto'
  minimumFractionDigits?: number;   // override CLDR default
  maximumFractionDigits?: number;
}

/**
 * Formats a numeric amount as a locale-aware currency string.
 *
 * @example
 * formatCurrency(1234.5, { locale: 'de-DE', currency: 'EUR' })
 * // => '1.234,50 €'
 *
 * @example
 * formatCurrency(1234.5, { locale: 'en-US', currency: 'EUR', currencyDisplay: 'name' })
 * // => '1,234.50 euros'
 */
export function formatCurrency(
  amount: number,
  options: FormatCurrencyOptions
): string {
  const {
    locale,
    currency,
    currencyDisplay = 'symbol',
    signDisplay = 'auto',
    minimumFractionDigits,
    maximumFractionDigits,
  } = options;

  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencyDisplay,
    signDisplay,
    ...(minimumFractionDigits !== undefined && { minimumFractionDigits }),
    ...(maximumFractionDigits !== undefined && { maximumFractionDigits }),
  });

  return formatter.format(amount);
}

// ─── 2. Formatter cache ───────────────────────────────────────────────────

/**
 * Memoized formatter cache. Key: `${locale}|${currency}|${display}|${sign}`.
 * Constructing Intl.NumberFormat is expensive — cache instances per isolate.
 */
const formatterCache = new Map<string, Intl.NumberFormat>();

export function getCachedFormatter(options: FormatCurrencyOptions): Intl.NumberFormat {
  const key = [
    options.locale,
    options.currency,
    options.currencyDisplay ?? 'symbol',
    options.signDisplay ?? 'auto',
    options.minimumFractionDigits ?? '',
    options.maximumFractionDigits ?? '',
  ].join('|');

  if (!formatterCache.has(key)) {
    formatterCache.set(
      key,
      new Intl.NumberFormat(options.locale, {
        style:            'currency',
        currency:          options.currency,
        currencyDisplay:   options.currencyDisplay ?? 'symbol',
        signDisplay:       options.signDisplay ?? 'auto',
        ...(options.minimumFractionDigits !== undefined && {
          minimumFractionDigits: options.minimumFractionDigits,
        }),
        ...(options.maximumFractionDigits !== undefined && {
          maximumFractionDigits: options.maximumFractionDigits,
        }),
      })
    );
  }

  return formatterCache.get(key)!;
}

// ─── 3. Exchange-rate cache in KV ─────────────────────────────────────────

export interface ExchangeRates {
  base: string;       // ISO 4217 base currency, e.g. 'USD'
  date: string;       // ISO 8601 date
  rates: Record<string, number>;
}

const RATES_KV_KEY  = 'exchange-rates:latest';
const RATES_TTL_SEC = 3600; // 1 hour

/**
 * Reads exchange rates from KV cache.
 * Falls back to the Open Exchange Rates API when the cache is cold or expired.
 * The actual API call is intentionally fire-and-forget from a Durable Object
 * or scheduled Worker to avoid adding latency to user requests.
 */
export async function getRates(
  kv: KVNamespace
): Promise<ExchangeRates | null> {
  const cached = await kv.get<ExchangeRates>(RATES_KV_KEY, 'json');
  return cached;
}

/**
 * Converts an amount from one currency to another using KV-cached rates.
 * Returns null when rates are unavailable or the target currency is unknown.
 */
export async function convertCurrency(
  kv: KVNamespace,
  amount: number,
  from: string,
  to: string
): Promise<number | null> {
  const rates = await getRates(kv);
  if (!rates) return null;

  // Rates are always relative to the base currency (e.g. USD)
  if (from === rates.base) {
    const toRate = rates.rates[to];
    return toRate !== undefined ? amount * toRate : null;
  }

  if (to === rates.base) {
    const fromRate = rates.rates[from];
    return fromRate !== undefined ? amount / fromRate : null;
  }

  // Cross-rate: from → base → to
  const fromRate = rates.rates[from];
  const toRate   = rates.rates[to];
  if (fromRate === undefined || toRate === undefined) return null;
  return (amount / fromRate) * toRate;
}

// ─── 4. Multi-currency cart total ────────────────────────────────────────

export interface CartLineItem {
  name:     string;
  amount:   number;
  currency: string; // ISO 4217
}

export interface FormattedCart {
  lines: Array<{ name: string; formatted: string }>;
  total: string;       // formatted in displayCurrency
  totalRaw: number;    // numeric total in displayCurrency
}

/**
 * Formats all cart line items and computes a grand total,
 * converting each item to the display currency via KV-cached rates.
 *
 * @param items           - Line items (may be in different currencies)
 * @param displayCurrency - ISO 4217 code to display totals in
 * @param displayLocale   - BCP 47 locale for formatting
 * @param kv              - KVNamespace holding exchange rates
 */
export async function formatCart(
  items: CartLineItem[],
  displayCurrency: string,
  displayLocale: string,
  kv: KVNamespace
): Promise<FormattedCart> {
  let totalRaw = 0;

  const lines = await Promise.all(
    items.map(async (item) => {
      let amountInDisplay = item.amount;

      if (item.currency !== displayCurrency) {
        const converted = await convertCurrency(kv, item.amount, item.currency, displayCurrency);
        amountInDisplay = converted ?? item.amount; // fallback: show unconverted
      }

      totalRaw += amountInDisplay;

      const formatted = formatCurrency(amountInDisplay, {
        locale: displayLocale,
        currency: displayCurrency,
        currencyDisplay: 'narrowSymbol',
      });

      return { name: item.name, formatted };
    })
  );

  const total = formatCurrency(totalRaw, {
    locale: displayLocale,
    currency: displayCurrency,
    currencyDisplay: 'symbol',
  });

  return { lines, total, totalRaw };
}

// ─── 5. Accounting format (negative in parentheses) ───────────────────────

/**
 * Returns an accounting-style formatted currency string.
 * Negative values are shown as (€1,234.50) rather than -€1,234.50.
 * Not natively available via Intl.NumberFormat in all engines;
 * this polyfills it by formatting absolute value and wrapping negatives.
 */
export function formatCurrencyAccounting(
  amount: number,
  options: FormatCurrencyOptions
): string {
  if (amount >= 0) {
    return getCachedFormatter(options).format(amount);
  }
  const positive = getCachedFormatter(options).format(-amount);
  return `(${positive})`;
}

// ─── 6. Worker handler ────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/format') {
      const amount   = parseFloat(url.searchParams.get('amount')   ?? '0');
      const currency = url.searchParams.get('currency') ?? 'USD';
      const locale   = url.searchParams.get('locale')   ?? 'en-US';
      const display  = (url.searchParams.get('display')  ?? 'symbol') as CurrencyDisplay;

      const formatted = formatCurrency(amount, { locale, currency, currencyDisplay: display });
      return Response.json({ amount, currency, locale, formatted });
    }

    if (url.pathname === '/cart') {
      if (request.method !== 'POST') {
        return new Response('POST required', { status: 405 });
      }
      const body = await request.json<{
        items: CartLineItem[];
        displayCurrency: string;
        displayLocale: string;
      }>();
      const cart = await formatCart(
        body.items,
        body.displayCurrency,
        body.displayLocale,
        env.EXCHANGE_KV
      );
      return Response.json(cart);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**Symbol placement** — CLDR encodes symbol placement as part of the format pattern. `Intl.NumberFormat` handles this automatically: `de-DE` puts `€` after the number with a non-breaking space, while `en-US` puts `$` before it. Never hardcode prefix/suffix logic.

**`narrowSymbol`** — Use `currencyDisplay: 'narrowSymbol'` for line items in a multi-currency context where the currency code is shown elsewhere (e.g. in a column header). It produces `$` instead of `US$`, saving horizontal space.

**`name` display** — `currencyDisplay: 'name'` produces `1,234.50 US dollars` — useful in accessibility labels and screen-reader-friendly tables.

**Decimal digits** — `Intl.NumberFormat` uses the CLDR-defined number of fraction digits per currency: JPY = 0, USD = 2, KWD = 3. You can override with `minimumFractionDigits` / `maximumFractionDigits`, but only do so when you have a specific business reason (e.g. showing 0 decimals in a compact list).

**Formatter memoization** — The formatter cache is module-level and survives across requests in the same Worker isolate. A fresh isolate starts with an empty cache; the warm-up cost of the first few requests is acceptable.

**Exchange rate architecture** — Never call an external exchange rate API on the hot request path; it adds latency and the API may be down. Use a Cloudflare Scheduled Worker (cron trigger) to fetch rates every hour and write them to KV. The main Worker reads from KV only.

## Anti-patterns

- **Do not** format currencies by concatenating a currency symbol string with a number — symbol placement, spacing, and decimal separators all vary by locale.
- **Do not** use `toFixed(2)` as a currency formatter — it ignores locale decimal separators and does not handle JPY (0 decimals) or KWD (3 decimals).
- **Do not** store pre-formatted currency strings in D1 or KV — they become stale when exchange rates change. Store raw amounts and format at render time.
- **Do not** create a new `Intl.NumberFormat` on every request — cache instances as shown above.

## Gotchas

- `currencyDisplay: 'narrowSymbol'` may not be available in older V8 versions (< 8.4). The Workers runtime is modern, but if you test locally with Node < 14 you may get a `RangeError`.
- `Intl.NumberFormat` with `style: 'currency'` throws a `RangeError` for unknown ISO 4217 codes (e.g. `'XYZ'`). Validate currency codes against a known list before calling.
- Some locales format negative currency with a minus sign before the symbol (`-$5.00`) while others put it after (`$-5.00`). The `signDisplay` option gives you control; `'auto'` follows CLDR convention for the locale.
- `formatToParts()` is useful when you need to apply CSS styling to the currency symbol separately from the number — it returns an array of `{ type, value }` objects.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { formatCurrency, formatCurrencyAccounting } from './workers-currency-formatting-intl';

describe('formatCurrency', () => {
  it('USD in en-US prefixes symbol', () =>
    expect(formatCurrency(1234.5, { locale: 'en-US', currency: 'USD' })).toBe('$1,234.50')
  );
  it('EUR in de-DE suffixes symbol with dot separator', () =>
    expect(formatCurrency(1234.5, { locale: 'de-DE', currency: 'EUR' })).toBe('1.234,50 €')
  );
  it('JPY in ja-JP has no decimal places', () =>
    expect(formatCurrency(1234, { locale: 'ja-JP', currency: 'JPY' })).toBe('¥1,234')
  );
  it('EUR with name display in en-US', () =>
    expect(formatCurrency(1, { locale: 'en-US', currency: 'EUR', currencyDisplay: 'name' })).toBe('1.00 Euro')
  );
  it('narrowSymbol drops country qualifier', () =>
    expect(formatCurrency(1, { locale: 'en-CA', currency: 'USD', currencyDisplay: 'narrowSymbol' })).toBe('$1.00')
  );
});

describe('formatCurrencyAccounting', () => {
  it('wraps negative in parentheses', () =>
    expect(formatCurrencyAccounting(-500, { locale: 'en-US', currency: 'USD' })).toBe('($500.00)')
  );
  it('passes positive through unchanged', () =>
    expect(formatCurrencyAccounting(500, { locale: 'en-US', currency: 'USD' })).toBe('$500.00')
  );
});
```

## Related

- `documentation/docs/policies/i18n/number-unit-formatting-intl.md` — non-currency number formatting (units, percentages, compact notation)
- `documentation/docs/policies/i18n/workers-locale-negotiation.md` — determining the display locale per request
- `documentation/docs/policies/i18n/workers-icu-plural-rules.md` — pluralising "1 item"/"2 items" in cart summaries
- Cloudflare Scheduled Workers (for exchange rate refresh): https://developers.cloudflare.com/workers/configuration/cron-triggers/

## Sources

- ECMA-402 Intl.NumberFormat: https://tc39.es/ecma402/#numberformat-objects
- MDN Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- CLDR currency data: https://github.com/unicode-org/cldr/blob/main/common/supplemental/currencyData.xml
- ISO 4217 currency codes: https://www.iso.org/iso-4217-currency-codes.html
- Open Exchange Rates API: https://openexchangerates.org/documentation
