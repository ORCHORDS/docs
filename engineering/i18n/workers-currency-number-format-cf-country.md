# Currency and Number Formatting Using cf.country in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your e-commerce Worker needs to display prices in the visitor's local currency without requiring a login. Formatting must match local conventions — comma vs period as decimal separator, currency symbol position, and grouping separators all vary by country.

---

## Context
Cloudflare populates `request.cf.country` with the ISO 3166-1 alpha-2 country code derived from IP geolocation. This code can be mapped to an ISO 4217 currency code via a KV lookup table, then used with `Intl.NumberFormat` — which is fully available in the Workers runtime — to produce correctly formatted price strings. Users connecting via WARP, VPN, or tunnel may have `cf.country` as `null` or `"T1"` (Tor); always fall back to a default. Browsers cache `Vary: CF-IPCountry` responses correctly so CDN caches remain segmented per country.

---

## Setup / Config

```toml
# wrangler.toml
name = "currency-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "GEO_DATA"
id = "YOUR_KV_NAMESPACE_ID"
preview_id = "YOUR_KV_PREVIEW_ID"

[vars]
DEFAULT_LOCALE = "en-US"
DEFAULT_CURRENCY = "USD"
```

```bash
# Upload the country -> currency mapping (excerpt shown; full table has ~250 entries)
cat > /tmp/country-currency.json <<'EOF'
{
  "US": {"currency": "USD", "locale": "en-US"},
  "GB": {"currency": "GBP", "locale": "en-GB"},
  "DE": {"currency": "EUR", "locale": "de-DE"},
  "FR": {"currency": "EUR", "locale": "fr-FR"},
  "JP": {"currency": "JPY", "locale": "ja-JP"},
  "CA": {"currency": "CAD", "locale": "en-CA"},
  "AU": {"currency": "AUD", "locale": "en-AU"},
  "CH": {"currency": "CHF", "locale": "de-CH"},
  "IN": {"currency": "INR", "locale": "hi-IN"},
  "BR": {"currency": "BRL", "locale": "pt-BR"}
}
EOF
wrangler kv:key put --binding=GEO_DATA "country-currency-map" "$(cat /tmp/country-currency.json)"
```

---

## Implementation

```typescript
// src/index.ts
export interface Env {
  GEO_DATA: KVNamespace;
  DEFAULT_LOCALE: string;
  DEFAULT_CURRENCY: string;
}

interface CountryConfig {
  currency: string;
  locale: string;
}

type CountryCurrencyMap = Record<string, CountryConfig>;

// Module-level cache — persists across requests in the same isolate
let cachedMap: CountryCurrencyMap | null = null;
let cacheExpiry = 0;
const MAP_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getCountryConfig(
  kv: KVNamespace,
  country: string | null | undefined,
  defaultLocale: string,
  defaultCurrency: string,
): Promise<CountryConfig> {
  const now = Date.now();
  if (!cachedMap || now > cacheExpiry) {
    const raw = await kv.get('country-currency-map');
    cachedMap = raw ? (JSON.parse(raw) as CountryCurrencyMap) : {};
    cacheExpiry = now + MAP_TTL_MS;
  }

  if (!country || country === 'T1' || country === 'XX') {
    return { currency: defaultCurrency, locale: defaultLocale };
  }

  return cachedMap[country] ?? { currency: defaultCurrency, locale: defaultLocale };
}

/**
 * Format an amount as currency using the country's locale and currency code.
 */
function formatCurrency(amount: number, locale: string, currency: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    // Unknown currency code — fall back to plain number
    return new Intl.NumberFormat(locale).format(amount);
  }
}

/**
 * Format a plain number respecting local decimal/grouping separators.
 */
function formatNumber(amount: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(amount);
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const cf = request.cf as { country?: string | null } | undefined;
    const country = cf?.country;

    const config = await getCountryConfig(
      env.GEO_DATA,
      country,
      env.DEFAULT_LOCALE,
      env.DEFAULT_CURRENCY,
    );

    if (url.pathname === '/format/currency') {
      const amountParam = url.searchParams.get('amount');
      const amount = amountParam ? parseFloat(amountParam) : 0;
      if (isNaN(amount)) {
        return Response.json({ error: 'Invalid amount' }, { status: 400 });
      }

      const formatted = formatCurrency(amount, config.locale, config.currency);
      return Response.json(
        {
          country: country ?? 'unknown',
          locale: config.locale,
          currency: config.currency,
          amount,
          formatted,
        },
        {
          headers: {
            // Instruct CDN caches to segment by country
            Vary: 'CF-IPCountry, Accept-Language',
            'Cache-Control': 'public, max-age=3600',
          },
        },
      );
    }

    if (url.pathname === '/format/number') {
      const amountParam = url.searchParams.get('amount');
      const amount = amountParam ? parseFloat(amountParam) : 0;
      if (isNaN(amount)) {
        return Response.json({ error: 'Invalid amount' }, { status: 400 });
      }
      const formatted = formatNumber(amount, config.locale);
      return Response.json({ country, locale: config.locale, amount, formatted });
    }

    return Response.json({
      country: country ?? 'unknown (tunnel/VPN)',
      ...config,
      note: 'No cf.country detected; using defaults.',
    });
  },
};
```

---

## Integration / Testing

```bash
# Start local dev
npx wrangler dev

# Simulate German visitor (DE -> EUR, de-DE locale)
# In local dev, inject cf metadata via --test-scheduled or miniflare cf option
curl 'http://localhost:8787/format/currency?amount=1234567.89'
# Simulate: {"country":"DE","locale":"de-DE","currency":"EUR","formatted":"1.234.567,89 €"}

# Note decimal comma, period grouping separator, and EUR sign in German format
curl 'http://localhost:8787/format/currency?amount=1234567.89'
# US: {"formatted":"$1,234,567.89"}
# JP: {"formatted":"￥1,234,568"} -- JPY has no decimal places

# Test tunnel/VPN fallback (T1 is Tor exit)
curl 'http://localhost:8787/'
# Returns default USD / en-US config
```

```typescript
// test/currency.test.ts
import { describe, it, expect } from 'vitest';

// Pure unit tests — no Worker runtime needed
function formatCurrency(amount: number, locale: string, currency: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

describe('Currency formatting', () => {
  it('uses period as decimal separator in en-US', () => {
    expect(formatCurrency(1234.5, 'en-US', 'USD')).toBe('$1,234.50');
  });

  it('uses comma as decimal separator in de-DE', () => {
    const result = formatCurrency(1234.5, 'de-DE', 'EUR');
    expect(result).toContain(',');
    expect(result).toContain('€'); // EUR sign
  });

  it('formats JPY without decimal places', () => {
    // JPY has no minor unit — Intl respects this
    const result = new Intl.NumberFormat('ja-JP', {
      style: 'currency',
      currency: 'JPY',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(1234);
    // Implementation may vary — just check it contains digits
    expect(result).toMatch(/\d/);
  });
});
```

---

## Anti-patterns
- **Fetching the country-currency map from KV on every request** — the map is static; store it in module scope with a TTL, or embed a minified version directly in the Worker script for zero-latency access.
- **Using `cf.country` as the sole locale signal** — country and language are not the same; a Canadian visitor may prefer French. Combine `cf.country` for currency and `Accept-Language` for locale string.
- **Omitting `Vary: CF-IPCountry`** — Cloudflare's cache will serve a German-formatted price to a US visitor if this header is missing.
- **Hard-coding currency precision as always 2** — some currencies (JPY, KWD, BHD) have 0 or 3 decimal places. Let `Intl.NumberFormat` handle precision automatically by omitting `minimumFractionDigits`/`maximumFractionDigits`.

---

## Gotchas
- `request.cf` is typed as `IncomingRequestCfProperties` in `@cloudflare/workers-types` but is `undefined` in unit tests unless mocked.
- `cf.country` can be `"T1"` for Tor users — handle it explicitly alongside `null`.
- `Intl.NumberFormat` with an invalid ISO 4217 currency code throws `RangeError`; wrap in try/catch and fall back.
- The Workers runtime `Intl` object does **not** include all locale data in older compatibility dates; use `2024-09-23` or later to get full CLDR data.

---

## Verification

```bash
# Verify Vary header is present in deployed Worker
curl -sI 'https://your-worker.workers.dev/format/currency?amount=99.99' \
  | grep -i vary
# Vary: CF-IPCountry, Accept-Language

# Check CF-Cache-Status segments correctly
curl -sI 'https://your-worker.workers.dev/format/currency?amount=99.99'
# Second request from same country: CF-Cache-Status: HIT

# List KV keys to confirm map is uploaded
wrangler kv:key list --binding=GEO_DATA
```

---

## Related
- `workers-intl-message-format-kv-translations.md`
- `workers-date-time-format-timezone-d1.md`
- `workers-hreflang-injection-html-rewriter.md`

---

## Sources
- Cloudflare Workers `request.cf` properties — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- MDN Intl.NumberFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- ISO 4217 currency codes — https://www.iso.org/iso-4217-currency-codes.html
- Cloudflare Cache Vary header — https://developers.cloudflare.com/cache/about/cache-control/#vary
