# Live FX Currency Conversion with KV-Cached Rates and Locale Display in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your storefront stores prices in USD but must display them in the visitor's local currency with locale-correct formatting. Fetching live FX rates on every request is too slow and risks rate-limiting from the FX provider. You need a Workers pattern that: (1) fetches rates from a third-party FX API at a configurable interval, (2) caches them in KV with TTL, (3) converts and formats amounts with `Intl.NumberFormat` for the user's locale, and (4) falls back gracefully when the cache is cold or the provider is down.

## Context

`Intl.NumberFormat` in Cloudflare Workers fully supports the `style: "currency"` option and respects locale-specific symbol placement, grouping separators, decimal separators, and currency sign position (e.g., `de-DE` places `€` after the number; `en-US` places `$` before). FX rates are fetched once by a scheduled Worker (Cron Trigger), written to KV, and read by the request-serving Worker — this decouples rate refresh from user-facing latency.

---

## KV Rate Schema

```typescript
// Key:   fx:rates:{base}          e.g.  fx:rates:USD
// Value: { rates: { EUR: 0.923, JPY: 146.2, ... }, fetchedAt: 1724420400000 }
// TTL:   3600 s (1 hour KV TTL), refresh every 30 min via Cron Trigger

interface FxRatePayload {
  rates: Record<string, number>;
  fetchedAt: number;
}
```

---

## Scheduled Worker: Fetch and Cache Rates

```typescript
// src/fx-refresh.ts  — triggered by Cron: "*/30 * * * *"
interface Env {
  FX_KV: KVNamespace;
  FX_API_KEY: string; // stored in Workers secret
}

const BASE_CURRENCY = "USD";

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const url = `https://api.exchangerate.host/latest?base=${BASE_CURRENCY}&access_key=${env.FX_API_KEY}`;
    const res = await fetch(url, { cf: { cacheTtl: 0 } }); // bypass CF cache for fresh data
    if (!res.ok) {
      console.error(`FX fetch failed: ${res.status}`);
      return; // leave stale KV value intact as fallback
    }
    const data = await res.json<{ rates: Record<string, number> }>();
    const payload: FxRatePayload = {
      rates: data.rates,
      fetchedAt: Date.now(),
    };
    // Write with 2-hour KV TTL so cold Workers still have rates even if Cron misses
    await env.FX_KV.put(`fx:rates:${BASE_CURRENCY}`, JSON.stringify(payload), {
      expirationTtl: 7200,
    });
    console.log(`FX rates updated: ${Object.keys(data.rates).length} currencies`);
  },
};
```

---

## Reading Rates with Staleness Guard

```typescript
const MAX_RATE_AGE_MS = 2 * 60 * 60 * 1000; // 2 hours

async function getRates(
  kv: KVNamespace,
  base: string
): Promise<Record<string, number> | null> {
  const raw = await kv.get<FxRatePayload>(`fx:rates:${base}`, {
    type: "json",
    cacheTtl: 120, // KV edge cache: re-fetch from KV store at most every 2 min
  });
  if (!raw) return null;
  if (Date.now() - raw.fetchedAt > MAX_RATE_AGE_MS) {
    console.warn("FX rates stale; serving with caveat");
    // Still return them — stale rates beat a broken UI
  }
  return raw.rates;
}
```

---

## Convert and Format for the User's Locale

```typescript
interface ConversionResult {
  originalAmount: number;
  originalCurrency: string;
  convertedAmount: number;
  targetCurrency: string;
  formatted: string;
  rateAge: "fresh" | "stale" | "unavailable";
}

async function convertAndFormat(
  kv: KVNamespace,
  amountInBase: number,
  baseCurrency: string,
  targetCurrency: string,
  locale: string
): Promise<ConversionResult> {
  const rates = await getRates(kv, baseCurrency);

  if (!rates || !(targetCurrency in rates)) {
    // Fallback: display in base currency
    const formatted = new Intl.NumberFormat(locale, {
      style: "currency",
      currency: baseCurrency,
      maximumFractionDigits: 2,
    }).format(amountInBase);
    return {
      originalAmount: amountInBase,
      originalCurrency: baseCurrency,
      convertedAmount: amountInBase,
      targetCurrency: baseCurrency,
      formatted,
      rateAge: "unavailable",
    };
  }

  const rate = rates[targetCurrency];
  const converted = amountInBase * rate;

  // Respect CLDR fraction digits per currency (JPY = 0, KWD = 3)
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: targetCurrency,
    // Let Intl pick the correct fraction digits for the currency
  });

  return {
    originalAmount: amountInBase,
    originalCurrency: baseCurrency,
    convertedAmount: converted,
    targetCurrency,
    formatted: formatter.format(converted),
    rateAge: "fresh",
  };
}

// Usage examples:
// convertAndFormat(kv, 29.99, "USD", "EUR", "de-DE") → "27,69 €"
// convertAndFormat(kv, 29.99, "USD", "JPY", "ja-JP") → "¥4,381"
// convertAndFormat(kv, 29.99, "USD", "AED", "ar-AE") → "١١٠٫١١ د.إ."
```

---

## Currency Symbol Disambiguation via `currencyDisplay`

```typescript
function formatCurrencyWithContext(
  amount: number,
  currency: string,
  locale: string,
  context: "narrow" | "symbol" | "name" | "code" = "symbol"
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    currencyDisplay: context,
  }).format(amount);
}

// "$" vs "CA$" vs "Canadian dollar" vs "CAD" for 100 CAD in en-US
// formatCurrencyWithContext(100, "CAD", "en-US", "narrow")  → "$100.00"  (ambiguous)
// formatCurrencyWithContext(100, "CAD", "en-US", "symbol")  → "CA$100.00"
// formatCurrencyWithContext(100, "CAD", "en-US", "name")    → "100.00 Canadian dollars"
// formatCurrencyWithContext(100, "CAD", "en-US", "code")    → "CAD 100.00"
```

---

## Anti-patterns

- **Fetching FX rates inside the request handler**: adds 100–500 ms latency on every request and will hit rate limits under traffic spikes.
- **Hardcoding fraction digits** (`toFixed(2)`): JPY has 0 decimal places; KWD has 3. Always let `Intl.NumberFormat` decide.
- **Using `narrow` `currencyDisplay` for multi-currency UIs**: `$` is ambiguous between USD, CAD, AUD, SGD, and many more.
- **Storing converted prices in D1**: exchange rates change; store base-currency prices only and convert at display time.

## Gotchas

- KV `cacheTtl: 120` means the KV edge cache may serve rates up to 2 minutes after the Cron updates them. This is intentional; if you need sub-minute freshness, skip the `cacheTtl` parameter (but accept higher KV read billing).
- `Intl.NumberFormat` does **not** validate whether a currency code is currently active (e.g., `VEF` vs `VES`). Validate incoming currency codes against a known list before formatting.
- The `expirationTtl` on a KV write is a minimum — KV does not guarantee immediate eviction at expiry. Always check `fetchedAt` staleness in application logic.
- Arabic locale (`ar`, `ar-AE`) formats numbers with Arabic-Indic digits by default in many browsers but may format with ASCII digits in some Workers V8 builds. Use `numberingSystem: "latn"` via `Intl.Locale` if you need consistent ASCII digits.

## Verification

```bash
# Check that Cron writes KV rates
wrangler kv:key get --namespace-id=<FX_KV_ID> "fx:rates:USD"

# Validate formatting for several locales
node -e "
  const locales = ['de-DE', 'ja-JP', 'ar-AE', 'pt-BR', 'en-US'];
  const currencies = ['EUR', 'JPY', 'AED', 'BRL', 'USD'];
  locales.forEach((l, i) =>
    console.log(new Intl.NumberFormat(l, { style: 'currency', currency: currencies[i] }).format(1234.5))
  );
"

# Integration test
npx vitest run tests/fx-currency-conversion.test.ts
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `currency-formatting-cloudflare-workers-intl.md`
- `cldr-supplemental-currency-fraction-digits-workers.md`
- `translation-kv-caching-ttl-strategy.md`
- `locale-aware-number-currency-formatting.md`

## Sources

- `Intl.NumberFormat` currency style: https://tc39.es/ecma402/#sec-intl.numberformat
- CLDR currency fraction digits: https://github.com/unicode-org/cldr/blob/main/common/supplemental/supplementalData.xml
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- KV `expirationTtl`: https://developers.cloudflare.com/kv/api/write-key-value-pairs/
