# Tax Rate Lookup and Caching with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every checkout must apply the correct sales tax / VAT rate for the buyer's jurisdiction. Tax rates change quarterly (sometimes more often), but they do not change on every request. Hitting a D1 database on every checkout creates unnecessary latency and load. You need a fast, globally-distributed lookup with a safe invalidation path when rates change.

## Context

Cloudflare Workers KV is eventually consistent with a configurable TTL, making it ideal for data that is read frequently but updated rarely. D1 is the source of truth. The pattern: serve from KV → on KV miss, query D1 → write result back to KV with a TTL.

Cloudflare's `request.cf.country` and `request.cf.regionCode` fields are injected by the edge and available in every Worker invocation at zero cost.

## Solution

### 1. D1 Tax Rate Schema

```sql
-- migrations/003_tax_rates.sql
CREATE TABLE IF NOT EXISTS tax_rates (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  country_code  TEXT NOT NULL,        -- ISO 3166-1 alpha-2, e.g. 'US'
  region_code   TEXT,                 -- ISO 3166-2 subdivision, e.g. 'CA'
  product_type  TEXT NOT NULL DEFAULT 'general',
  rate_bps      INTEGER NOT NULL,     -- rate in basis points (500 = 5.00 %)
  effective_from TEXT NOT NULL,       -- ISO-8601 date
  effective_to   TEXT,                -- NULL means currently in effect
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_tax_rates_jurisdiction ON tax_rates
  (country_code, COALESCE(region_code, ''), product_type, effective_from);

CREATE INDEX idx_tax_rates_lookup ON tax_rates
  (country_code, region_code, product_type, effective_to);

-- Seed example rates
INSERT INTO tax_rates (country_code, region_code, product_type, rate_bps, effective_from)
VALUES
  ('US', 'CA', 'general',  725, '2024-01-01'),
  ('US', 'NY', 'general',  800, '2024-01-01'),
  ('US', 'TX', 'general',  625, '2024-01-01'),
  ('GB', NULL, 'general', 2000, '2024-01-01'),
  ('DE', NULL, 'general', 1900, '2024-01-01'),
  ('AU', NULL, 'general', 1000, '2024-01-01');
```

### 2. KV Key Convention

```typescript
// src/utils/taxKeys.ts
export function taxRateKVKey(
  countryCode: string,
  regionCode: string | null,
  productType: string
): string {
  // e.g. 'tax:US:CA:general' or 'tax:GB::general'
  return `tax:${countryCode}:${regionCode ?? ''}:${productType}`;
}

export const TAX_KV_TTL_SECONDS = 3600; // 1 hour — adjust per rate-change cadence
```

### 3. Jurisdiction Resolution

```typescript
// src/services/jurisdiction.ts

export interface Jurisdiction {
  countryCode: string;
  regionCode: string | null;
}

export function resolveJurisdiction(request: Request): Jurisdiction {
  // Cloudflare injects these from Anycast geolocation — no extra API calls
  const cf = (request as any).cf as CfProperties | undefined;

  const countryCode = cf?.country ?? 'US';
  // regionCode format: 'US-CA', 'US-NY' — extract subdivision
  const rawRegion = cf?.regionCode ?? null;
  const regionCode = rawRegion?.includes('-')
    ? rawRegion.split('-')[1]
    : rawRegion;

  return { countryCode: countryCode.toUpperCase(), regionCode };
}

// Override with explicitly provided values (billing address takes precedence)
export function resolveJurisdictionFromAddress(
  countryCode: string,
  regionCode: string | null
): Jurisdiction {
  return {
    countryCode: countryCode.toUpperCase(),
    regionCode: regionCode?.toUpperCase() ?? null,
  };
}
```

### 4. Tax Rate Lookup with KV Cache

```typescript
// src/services/taxRates.ts
import { Env } from '../types';
import { taxRateKVKey, TAX_KV_TTL_SECONDS } from '../utils/taxKeys';

export interface TaxRate {
  countryCode: string;
  regionCode: string | null;
  productType: string;
  rateBps: number;     // basis points
  ratePercent: number; // convenience: rateBps / 100
  source: 'kv' | 'd1';
}

export async function lookupTaxRate(
  env: Env,
  countryCode: string,
  regionCode: string | null,
  productType = 'general'
): Promise<TaxRate | null> {
  const key = taxRateKVKey(countryCode, regionCode, productType);

  // 1. Try KV cache first
  const cached = await env.TAX_RATES_KV.get(key, 'json') as
    { rateBps: number } | null;

  if (cached !== null) {
    return {
      countryCode, regionCode, productType,
      rateBps: cached.rateBps,
      ratePercent: cached.rateBps / 100,
      source: 'kv',
    };
  }

  // 2. KV miss — query D1
  // Try region-specific rate first, fall back to country-level
  const row = await env.DB
    .prepare(`
      SELECT rate_bps FROM tax_rates
      WHERE country_code = ?
        AND (region_code = ? OR region_code IS NULL)
        AND product_type = ?
        AND effective_from <= date('now')
        AND (effective_to IS NULL OR effective_to > date('now'))
      ORDER BY region_code IS NULL ASC  -- region-specific rows sort first
      LIMIT 1
    `)
    .bind(countryCode, regionCode, productType)
    .first<{ rate_bps: number }>();

  if (!row) return null;

  // 3. Backfill KV
  await env.TAX_RATES_KV.put(
    key,
    JSON.stringify({ rateBps: row.rate_bps }),
    { expirationTtl: TAX_KV_TTL_SECONDS }
  );

  return {
    countryCode, regionCode, productType,
    rateBps: row.rate_bps,
    ratePercent: row.rate_bps / 100,
    source: 'd1',
  };
}
```

### 5. Tax Calculation Endpoint

```typescript
// src/handlers/tax/calculate.ts
import { Env } from '../../types';
import { resolveJurisdiction, resolveJurisdictionFromAddress } from '../../services/jurisdiction';
import { lookupTaxRate } from '../../services/taxRates';

interface TaxRequest {
  amountCents: number;
  currency: string;
  productType?: string;
  billingCountry?: string;
  billingRegion?: string;
}

export async function handleTaxCalculate(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json() as TaxRequest;

  if (!body.amountCents || body.amountCents <= 0) {
    return new Response(
      JSON.stringify({ error: 'amountCents must be a positive integer' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const jurisdiction =
    body.billingCountry
      ? resolveJurisdictionFromAddress(body.billingCountry, body.billingRegion ?? null)
      : resolveJurisdiction(request);

  const taxRate = await lookupTaxRate(
    env,
    jurisdiction.countryCode,
    jurisdiction.regionCode,
    body.productType ?? 'general'
  );

  if (!taxRate) {
    // No tax rate configured for this jurisdiction — treat as 0 %
    return new Response(
      JSON.stringify({
        amountCents: body.amountCents,
        taxCents: 0,
        totalCents: body.amountCents,
        taxRateBps: 0,
        jurisdiction,
        source: 'none',
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  }

  const taxCents = Math.round(body.amountCents * taxRate.rateBps / 10000);

  return new Response(
    JSON.stringify({
      amountCents: body.amountCents,
      taxCents,
      totalCents: body.amountCents + taxCents,
      taxRateBps: taxRate.rateBps,
      taxRatePercent: taxRate.ratePercent,
      jurisdiction,
      source: taxRate.source,
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );
}
```

### 6. Cache Warming Cron Trigger

```typescript
// src/handlers/cron/warmTaxCache.ts
// Runs every hour to pre-populate KV before TTL expires
import { Env } from '../../types';
import { taxRateKVKey, TAX_KV_TTL_SECONDS } from '../../utils/taxKeys';

export async function warmTaxCache(env: Env): Promise<void> {
  const rows = await env.DB
    .prepare(`
      SELECT country_code, region_code, product_type, rate_bps
      FROM tax_rates
      WHERE effective_from <= date('now')
        AND (effective_to IS NULL OR effective_to > date('now'))
    `)
    .all<{
      country_code: string;
      region_code: string | null;
      product_type: string;
      rate_bps: number;
    }>();

  const puts = rows.results.map((row) =>
    env.TAX_RATES_KV.put(
      taxRateKVKey(row.country_code, row.region_code, row.product_type),
      JSON.stringify({ rateBps: row.rate_bps }),
      { expirationTtl: TAX_KV_TTL_SECONDS }
    )
  );

  await Promise.all(puts);
  console.log(`Tax cache warmed: ${puts.length} entries`);
}
```

### 7. Rate Change Invalidation

```typescript
// src/handlers/admin/invalidateTaxCache.ts
// Called by an internal admin endpoint after rate table updates
import { Env } from '../../types';
import { taxRateKVKey } from '../../utils/taxKeys';

interface InvalidationRequest {
  adminToken: string;
  countryCode?: string;  // omit to invalidate ALL
  regionCode?: string;
  productType?: string;
}

export async function handleTaxCacheInvalidation(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json() as InvalidationRequest;

  if (body.adminToken !== env.ADMIN_TOKEN) {
    return new Response('Unauthorized', { status: 401 });
  }

  if (body.countryCode) {
    // Targeted invalidation
    const key = taxRateKVKey(
      body.countryCode,
      body.regionCode ?? null,
      body.productType ?? 'general'
    );
    await env.TAX_RATES_KV.delete(key);
    return new Response(JSON.stringify({ invalidated: [key] }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Bulk invalidation: list and delete all tax: keys
  const listed = await env.TAX_RATES_KV.list({ prefix: 'tax:' });
  const deletions = listed.keys.map((k) => env.TAX_RATES_KV.delete(k.name));
  await Promise.all(deletions);

  return new Response(
    JSON.stringify({ invalidated: listed.keys.map((k) => k.name) }),
    { headers: { 'Content-Type': 'application/json' } }
  );
}
```

### 8. wrangler.toml

```toml
[[kv_namespaces]]
binding = "TAX_RATES_KV"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id = "<your-d1-database-id>"

[triggers]
crons = ["0 * * * *"]  # warm cache every hour
```

## Implementation Details

**Basis points**: Storing rates as integers (basis points = 1/100 of a percent) avoids floating-point rounding errors in the database and in arithmetic. `725 bps = 7.25 %`.

**Fallback hierarchy**: The D1 query orders `region_code IS NULL ASC` (false=0, true=1), so a region-specific row (e.g. `US/CA`) sorts before a country-level row (`US/NULL`). If no region match exists, the country-level row is returned.

**KV eventual consistency**: In rare cases, two Workers may simultaneously miss KV and both query D1, writing the same value back. This is harmless — both writes are idempotent.

**Cache warming**: The cron pre-populates KV so the first request after a cold start does not take the D1 read path. Without warming, a KV TTL expiry at peak traffic could cause a stampede.

## Anti-patterns

- **Storing rates as floats in the DB**: `0.0725 * 0.0725` accumulates IEEE 754 drift. Always use integer basis points.
- **Using IP geolocation for tax compliance without billing address**: IP location is a best-effort heuristic. For tax collection, the customer-provided billing address is the authoritative jurisdiction.
- **Cache with no TTL**: If you omit `expirationTtl`, old rates survive indefinitely. Set a TTL no longer than your rate-change notification window.
- **Global invalidation on every rate update**: If you sell in 150 jurisdictions, invalidating all 150 KV keys synchronously in a single request can hit KV rate limits. Use targeted invalidation by key.

## Gotchas

- `request.cf.country` returns `'T1'` for Tor exit nodes and `'XX'` for unknown — handle these gracefully by defaulting to a jurisdiction with a known rate or returning 0 %.
- KV `list` returns a maximum of 1,000 keys per call. For large rate tables, paginate using the `cursor` field.
- D1's `date('now')` is UTC. If your rate `effective_from` uses local dates, normalise to UTC on insert.
- Cloudflare KV reads from the nearest edge replica — a write may take up to 60 seconds to propagate globally. Factor this into your invalidation SLA.

## Verification

```bash
# Calculate tax for a California buyer (billing address)
curl -X POST https://your-worker.workers.dev/tax/calculate \
  -H 'Content-Type: application/json' \
  -d '{"amountCents":10000,"currency":"usd",\
"billingCountry":"US","billingRegion":"CA"}'
# Expected: taxCents ~725, source: 'kv' on 2nd call

# Warm cache manually
curl -X POST https://your-worker.workers.dev/cron/warm-tax-cache \
  -H 'Authorization: Bearer <admin-token>'

# Inspect KV entries
wrangler kv key list --namespace-id <id> --prefix tax:
```

## Related

- `documentation/categories/payments/workers-stripe-connect-oauth-flow.md`
- `documentation/categories/payments/workers-pci-dss-scope-reduction.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/d1/
- https://taxfoundation.org/data/all/state/state-and-local-sales-tax-rates-2024/
