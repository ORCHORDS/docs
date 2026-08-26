# Currency Formatting at the Edge with Intl.NumberFormat in Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Workers-based storefront or crypto dashboard needs to display prices in multiple currencies (USD, EUR, BRL, USDC, SOL) based on the user's locale without shipping large formatting libraries to the client. You want consistent, locale-sensitive decimal separators, the right currency symbol vs ISO code display, and sub-cent precision for crypto amounts — all computed at the edge and optionally cached in KV to avoid repeated instantiation overhead on hot paths.

## Context

Cloudflare Workers run V8 isolates with full `Intl` support since the Workers runtime adopted the V8 ICU data bundle. `Intl.NumberFormat` is available without any polyfill and handles the full CLDR currency formatting rules including symbol placement, grouping separators, and decimal separator locale variants. Crypto tokens like USDC and SOL are not ISO 4217 currencies, so they require custom display logic layered on top of `Intl.NumberFormat`. KV-based caching of pre-formatted strings is viable for price boards that show a fixed set of (locale, currency, amount) tuples.

## Intl.NumberFormat Basics in the Workers Runtime

`Intl.NumberFormat` is instantiated once per isolate lifecycle and shared across requests through a module-level cache. Avoid constructing a new formatter per request — V8 ICU initialisation for each `new Intl.NumberFormat()` call is non-trivial.

```typescript
// src/formatting/currency.ts

type CurrencyDisplay = "symbol" | "narrowSymbol" | "code" | "name";

interface FormatOptions {
  locale: string;
  currency: string;
  display?: CurrencyDisplay;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

// Module-level formatter cache: key = "locale|currency|display|minFrac|maxFrac"
const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(opts: FormatOptions): Intl.NumberFormat {
  const key = `${opts.locale}|${opts.currency}|${opts.display ?? "symbol"}|${opts.minimumFractionDigits ?? "auto"}|${opts.maximumFractionDigits ?? "auto"}`;
  if (formatterCache.has(key)) return formatterCache.get(key)!;

  const fmt = new Intl.NumberFormat(opts.locale, {
    style: "currency",
    currency: opts.currency,
    currencyDisplay: opts.display ?? "symbol",
    minimumFractionDigits: opts.minimumFractionDigits,
    maximumFractionDigits: opts.maximumFractionDigits,
  });
  formatterCache.set(key, fmt);
  return fmt;
}

export function formatFiatCurrency(
  amount: number,
  currency: string,
  locale: string,
  display: CurrencyDisplay = "symbol"
): string {
  return getFormatter({ locale, currency, display }).format(amount);
}

// Examples:
// formatFiatCurrency(1234.5, "EUR", "de-DE")        → "1.234,50 €"
// formatFiatCurrency(1234.5, "EUR", "en-US", "code") → "EUR 1,234.50"
// formatFiatCurrency(1234.5, "BRL", "pt-BR")        → "R$ 1.234,50"
```

## Formatting Crypto Amounts (USDC / SOL)

USDC is pegged to USD and displayed with 2 decimal places in fiat contexts but may need up to 6 for protocol-level precision. SOL typically shows 4–9 significant fractional digits. Since `USDC` and `SOL` are not ISO 4217 codes, use `Intl.NumberFormat` in `"decimal"` style and append the ticker manually.

```typescript
// src/formatting/crypto.ts

type CryptoToken = "USDC" | "SOL" | "ETH" | "BTC";

const CRYPTO_FRACTION: Record<CryptoToken, { min: number; max: number }> = {
  USDC: { min: 2, max: 6 },
  SOL:  { min: 2, max: 9 },
  ETH:  { min: 4, max: 8 },
  BTC:  { min: 5, max: 8 },
};

const decimalFormatterCache = new Map<string, Intl.NumberFormat>();

function getDecimalFormatter(locale: string, min: number, max: number): Intl.NumberFormat {
  const key = `${locale}|${min}|${max}`;
  if (decimalFormatterCache.has(key)) return decimalFormatterCache.get(key)!;
  const fmt = new Intl.NumberFormat(locale, {
    style: "decimal",
    minimumFractionDigits: min,
    maximumFractionDigits: max,
    useGrouping: true,
  });
  decimalFormatterCache.set(key, fmt);
  return fmt;
}

export function formatCryptoAmount(
  amount: number,
  token: CryptoToken,
  locale: string,
  display: "symbol" | "code" = "symbol"
): string {
  const { min, max } = CRYPTO_FRACTION[token];
  const formatted = getDecimalFormatter(locale, min, max).format(amount);

  // Display mode: "symbol" = prefix "◎" for SOL, "$" for USDC, etc.
  // "code" = append the ticker string
  const symbols: Record<CryptoToken, string> = {
    USDC: "$",
    SOL: "◎",
    ETH: "Ξ",
    BTC: "₿",
  };

  if (display === "symbol") {
    return `${symbols[token]}${formatted}`;
  }
  return `${formatted} ${token}`;
}

// formatCryptoAmount(1500.123456, "USDC", "pt-BR", "symbol") → "$1.500,123456"
// formatCryptoAmount(0.008734, "SOL", "en-US", "code")       → "0.008734000 SOL"
// formatCryptoAmount(0.00123456, "ETH", "de-DE", "symbol")   → "Ξ0,0012345600"
```

## Caching Formatted Outputs in KV

For a price-board Worker that formats the same (locale, currency, amount) combinations thousands of times per minute, pre-serialise the formatted strings into KV. Invalidate on price updates by writing new values under a timestamped or version-keyed namespace rather than relying on KV TTL alone.

```typescript
// src/formatting/kv-cache.ts

interface PriceEntry {
  formatted: string;
  rawAmount: number;
  updatedAt: number; // Unix ms
}

const KV_NAMESPACE_PREFIX = "price:";
const KV_TTL_SECONDS = 30; // maximum acceptable staleness

export async function getOrFormatPrice(
  kv: KVNamespace,
  token: CryptoToken,
  locale: string,
  fetchLiveAmount: () => Promise<number>
): Promise<string> {
  const key = `${KV_NAMESPACE_PREFIX}${token}:${locale}`;
  const cached = await kv.get<PriceEntry>(key, "json");

  if (cached && Date.now() - cached.updatedAt < KV_TTL_SECONDS * 1000) {
    return cached.formatted;
  }

  const amount = await fetchLiveAmount();
  const formatted = formatCryptoAmount(amount, token as CryptoToken, locale, "code");

  const entry: PriceEntry = { formatted, rawAmount: amount, updatedAt: Date.now() };
  // Fire-and-forget write — don't block the response on KV write latency
  kv.put(key, JSON.stringify(entry), { expirationTtl: KV_TTL_SECONDS * 4 }).catch(() => {
    // Log but don't fail the request on KV write errors
    console.error(`KV write failed for ${key}`);
  });

  return formatted;
}

// Worker handler using the above:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locale = url.searchParams.get("locale") ?? "en-US";
    const token = (url.searchParams.get("token") ?? "USDC") as CryptoToken;

    const formatted = await getOrFormatPrice(
      env.PRICES_KV,
      token,
      locale,
      async () => {
        // Replace with real price oracle call
        const resp = await fetch(`https://api.example.com/price/${token}`);
        const { price } = await resp.json<{ price: number }>();
        return price;
      }
    );

    return new Response(JSON.stringify({ token, locale, formatted }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Anti-patterns

- Constructing `new Intl.NumberFormat()` inside the `fetch` handler on every request — pays ICU initialisation cost on every isolate wake-up and wastes CPU on hot paths.
- Passing `currency: "USDC"` to `Intl.NumberFormat` — V8 will throw `RangeError: Invalid currency code` for non-ISO 4217 codes; always use `style: "decimal"` for crypto tokens and format the ticker separately.
- Hardcoding `"$"` as the USD symbol for all locales — `Intl.NumberFormat("fr-FR", { style:"currency", currency:"USD" })` renders `"US$"` or `"$US"` depending on the CLDR version; let `Intl` pick the symbol.

## Gotchas

- `Intl.NumberFormat` in Workers uses the ICU data version bundled with the specific V8 build deployed to Cloudflare's network — CLDR currency data may lag behind the latest CLDR release. Pin the Workers compatibility date and test after Workers runtime version bumps.
- The `"narrowSymbol"` `currencyDisplay` option is not available in all older compatibility dates; guard with a try/catch or check `Intl.supportedValuesOf("currency")` before relying on it.
- KV reads from the Worker's local data centre are fast (~1 ms), but KV is eventually consistent — a race between two Workers instances writing the same key is benign for price display but could cause a brief flash of the old price.

## Verification

```bash
# Confirm Workers runtime exposes Intl.NumberFormat with currency style
curl -s "https://your-worker.workers.dev/?locale=de-DE&token=USDC" \
  | jq '.formatted'
# Expected: something like "1.234,56 USDC"

# Check pt-BR decimal separator (comma, not period)
curl -s "https://your-worker.workers.dev/?locale=pt-BR&token=SOL" \
  | jq -r '.formatted'

# Verify KV cache hit on second request (latency should drop)
time curl -s "https://your-worker.workers.dev/?locale=en-US&token=ETH" > /dev/null
time curl -s "https://your-worker.workers.dev/?locale=en-US&token=ETH" > /dev/null

# Validate non-ISO currency code guard in unit tests
npx vitest run src/formatting/crypto.test.ts
```

## Related

- `i18n/intl-api-workers-edge-formatting.md`
- `i18n/currency-formatting-patterns.md`
- `i18n/translation-kv-caching-ttl-strategy.md`
- `i18n/locale-aware-number-currency-formatting.md`
- `i18n/number-currency-formatting-2026.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-standards/#javascript-standards
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- https://tc39.es/ecma402/#numberformat-objects
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://www.currency-iso.org/en/path/to/project
