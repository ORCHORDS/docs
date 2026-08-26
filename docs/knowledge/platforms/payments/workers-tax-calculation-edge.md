# Tax Calculation at the Edge with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your checkout flow calls a third-party tax API (TaxJar, Avalara) on every cart update. The P99 latency adds 400–800 ms per request, and the per-call cost adds up at scale. You also need to handle EU VAT rules for digital services, validate VAT numbers via VIES before zero-rating B2B sales, and produce audit-ready tax line items that survive a revenue audit. Moving tax calculation to the edge in a Worker eliminates the external round-trip for common cases and lets you cache rates in KV.

## Context

This pattern combines:
- **D1** for a pre-loaded US sales tax table (state + county rates) and EU VAT rates.
- **KV** for caching computed rates with a 24-hour TTL.
- **VIES API** for EU VAT number validation (B2B zero-rating).
- **Banker's rounding** (round-half-to-even) for tax amounts, as required by several EU jurisdictions.

The Worker receives a cart payload, determines the applicable tax jurisdiction, computes the tax amount, and returns structured line items.

## Solution

```typescript
import { Env } from './types';

// ── Types ─────────────────────────────────────────────────────────────────────

type CartItem = {
  sku: string;
  description: string;
  unitPrice: number; // cents
  quantity: number;
  taxCategory: 'digital_service' | 'physical_good' | 'saas' | 'exempt';
};

type TaxAddress = {
  country: string; // ISO 3166-1 alpha-2
  state?: string; // US state code e.g. 'CA'
  county?: string; // US county name
  vatNumber?: string; // EU VAT number for B2B
};

type TaxLineItem = {
  description: string;
  taxableAmount: number; // cents
  taxRate: number; // e.g. 0.0725
  taxAmount: number; // cents
  jurisdiction: string;
  taxType: 'sales_tax' | 'vat' | 'exempt';
};

type TaxResult = {
  subtotal: number;
  taxTotal: number;
  total: number;
  taxInclusive: boolean;
  lines: TaxLineItem[];
  vatValidated: boolean;
  cacheHit: boolean;
};

// ── Banker's rounding (round-half-to-even) ────────────────────────────────────

function bankersRound(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (Math.abs(diff - 0.5) > Number.EPSILON) return Math.round(value);
  // Exactly half — round to even.
  return floor % 2 === 0 ? floor : floor + 1;
}

// ── KV cache helpers ──────────────────────────────────────────────────────────

type RateCache = { rate: number; jurisdiction: string; taxType: 'sales_tax' | 'vat' };

async function getCachedRate(
  kv: KVNamespace,
  cacheKey: string,
): Promise<RateCache | null> {
  const raw = await kv.get(cacheKey, 'json');
  return raw as RateCache | null;
}

async function setCachedRate(
  kv: KVNamespace,
  cacheKey: string,
  rate: RateCache,
): Promise<void> {
  await kv.put(cacheKey, JSON.stringify(rate), { expirationTtl: 86_400 }); // 24 h
}

// ── US sales tax lookup (D1) ──────────────────────────────────────────────────

type UsTaxRow = { combined_rate: number; state_code: string; county_name: string };

async function getUsTaxRate(
  db: D1Database,
  kv: KVNamespace,
  state: string,
  county: string,
): Promise<RateCache> {
  const cacheKey = `tax:us:${state.toLowerCase()}:${county.toLowerCase()}`;
  const cached = await getCachedRate(kv, cacheKey);
  if (cached) return cached;

  const row = await db
    .prepare(
      `SELECT combined_rate, state_code, county_name
       FROM us_tax_rates
       WHERE state_code = ? AND county_name = ?
       LIMIT 1`,
    )
    .bind(state.toUpperCase(), county.toLowerCase())
    .first<UsTaxRow>();

  if (!row) throw new Error(`No US tax rate found for ${state}, ${county}`);

  const result: RateCache = {
    rate: row.combined_rate,
    jurisdiction: `${row.state_code} - ${row.county_name}`,
    taxType: 'sales_tax',
  };

  await setCachedRate(kv, cacheKey, result);
  return result;
}

// ── EU VAT lookup (D1) ────────────────────────────────────────────────────────

type EuVatRow = { standard_rate: number; digital_services_rate: number; country_code: string };

async function getEuVatRate(
  db: D1Database,
  kv: KVNamespace,
  country: string,
  isDigitalService: boolean,
): Promise<RateCache> {
  const cacheKey = `tax:eu:${country.toLowerCase()}:${isDigitalService ? 'digital' : 'standard'}`;
  const cached = await getCachedRate(kv, cacheKey);
  if (cached) return cached;

  const row = await db
    .prepare(
      `SELECT standard_rate, digital_services_rate, country_code
       FROM eu_vat_rates
       WHERE country_code = ?
       LIMIT 1`,
    )
    .bind(country.toUpperCase())
    .first<EuVatRow>();

  if (!row) throw new Error(`No EU VAT rate found for ${country}`);

  const rate = isDigitalService ? row.digital_services_rate : row.standard_rate;
  const result: RateCache = {
    rate,
    jurisdiction: `EU VAT - ${row.country_code}`,
    taxType: 'vat',
  };

  await setCachedRate(kv, cacheKey, result);
  return result;
}

// ── VIES VAT number validation ────────────────────────────────────────────────

async function validateVatNumber(vatNumber: string): Promise<boolean> {
  const countryCode = vatNumber.slice(0, 2).toUpperCase();
  const number = vatNumber.slice(2);

  // VIES SOAP endpoint — note: outbound from Workers requires the host
  // to be reachable. Add it to your allowed hosts if using Smart Placement.
  const soapBody = `<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkVat xmlns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
      <countryCode>${countryCode}</countryCode>
      <vatNumber>${number}</vatNumber>
    </checkVat>
  </soap:Body>
</soap:Envelope>`;

  try {
    const response = await fetch(
      'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
      {
        method: 'POST',
        headers: { 'Content-Type': 'text/xml;charset=UTF-8', SOAPAction: '' },
        body: soapBody,
        signal: AbortSignal.timeout(3_000),
      },
    );

    const text = await response.text();
    return text.includes('<valid>true</valid>');
  } catch {
    // VIES is notoriously unreliable. On error, fall back to not zero-rating.
    console.warn('[tax] VIES validation failed, defaulting to non-zero-rated');
    return false;
  }
}

// ── Core tax calculation ──────────────────────────────────────────────────────

async function calculateTax(
  db: D1Database,
  kv: KVNamespace,
  items: CartItem[],
  address: TaxAddress,
  taxInclusive: boolean,
): Promise<Omit<TaxResult, 'cacheHit'> & { cacheHit: boolean }> {
  const isEu = await isEuCountry(db, address.country);
  const isUs = address.country === 'US';

  let vatValidated = false;
  let zeroRated = false;

  if (isEu && address.vatNumber) {
    vatValidated = await validateVatNumber(address.vatNumber);
    // Valid VAT number = B2B reverse-charge; zero-rate the sale.
    zeroRated = vatValidated;
  }

  const lines: TaxLineItem[] = [];
  let subtotal = 0;
  let taxTotal = 0;
  let cacheHit = true;

  for (const item of items) {
    const lineSubtotal = item.unitPrice * item.quantity;
    subtotal += lineSubtotal;

    if (item.taxCategory === 'exempt' || zeroRated) {
      lines.push({
        description: item.description,
        taxableAmount: lineSubtotal,
        taxRate: 0,
        taxAmount: 0,
        jurisdiction: zeroRated ? 'EU B2B reverse charge' : 'exempt',
        taxType: 'exempt',
      });
      continue;
    }

    let rateInfo: RateCache;
    const isDigital = item.taxCategory === 'digital_service' || item.taxCategory === 'saas';

    if (isUs && address.state && address.county) {
      const cacheKey = `tax:us:${address.state.toLowerCase()}:${address.county.toLowerCase()}`;
      const preCached = await getCachedRate(kv, cacheKey);
      if (!preCached) cacheHit = false;
      rateInfo = await getUsTaxRate(db, kv, address.state, address.county);
    } else if (isEu) {
      const cacheKey = `tax:eu:${address.country.toLowerCase()}:${isDigital ? 'digital' : 'standard'}`;
      const preCached = await getCachedRate(kv, cacheKey);
      if (!preCached) cacheHit = false;
      rateInfo = await getEuVatRate(db, kv, address.country, isDigital);
    } else {
      // Non-US, non-EU: no tax.
      lines.push({
        description: item.description,
        taxableAmount: lineSubtotal,
        taxRate: 0,
        taxAmount: 0,
        jurisdiction: 'no tax jurisdiction',
        taxType: 'exempt',
      });
      continue;
    }

    let taxableAmount: number;
    let taxAmount: number;

    if (taxInclusive) {
      // Tax is already baked into the price: extract it.
      // taxableAmount = lineSubtotal / (1 + rate)
      taxableAmount = bankersRound(lineSubtotal / (1 + rateInfo.rate));
      taxAmount = lineSubtotal - taxableAmount;
    } else {
      taxableAmount = lineSubtotal;
      taxAmount = bankersRound(lineSubtotal * rateInfo.rate);
    }

    taxTotal += taxAmount;
    lines.push({
      description: item.description,
      taxableAmount,
      taxRate: rateInfo.rate,
      taxAmount,
      jurisdiction: rateInfo.jurisdiction,
      taxType: rateInfo.taxType,
    });
  }

  return {
    subtotal,
    taxTotal,
    total: taxInclusive ? subtotal : subtotal + taxTotal,
    taxInclusive,
    lines,
    vatValidated,
    cacheHit,
  };
}

async function isEuCountry(db: D1Database, country: string): Promise<boolean> {
  const row = await db
    .prepare('SELECT 1 FROM eu_vat_rates WHERE country_code = ? LIMIT 1')
    .bind(country.toUpperCase())
    .first();
  return row !== null;
}

// ── Worker handler ────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{
      items: CartItem[];
      address: TaxAddress;
      taxInclusive?: boolean;
    }>();

    try {
      const result = await calculateTax(
        env.DB,
        env.TAX_KV,
        body.items,
        body.address,
        body.taxInclusive ?? false,
      );
      return Response.json(result);
    } catch (err) {
      console.error('[tax] Calculation error:', err);
      return new Response('Tax calculation failed', { status: 500 });
    }
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE us_tax_rates (
  state_code    TEXT NOT NULL,
  county_name   TEXT NOT NULL,
  state_rate    REAL NOT NULL,
  county_rate   REAL NOT NULL,
  combined_rate REAL NOT NULL,
  PRIMARY KEY (state_code, county_name)
);

CREATE TABLE eu_vat_rates (
  country_code          TEXT PRIMARY KEY,
  standard_rate         REAL NOT NULL,
  digital_services_rate REAL NOT NULL,
  country_name          TEXT NOT NULL
);

CREATE TABLE eu_countries (
  country_code TEXT PRIMARY KEY
);
```

Load US rates from the TaxJar CSV export or USPS ZIP+4 dataset. EU rates change rarely (typically annually); source from the European Commission's published VAT rates table.

**KV cache key scheme:**

| Key pattern | TTL | Example |
|-------------|-----|---------|
| `tax:us:{state}:{county}` | 24 h | `tax:us:ca:los angeles` |
| `tax:eu:{country}:{digital\|standard}` | 24 h | `tax:eu:de:digital` |

## Anti-patterns

- **Rounding each line with `Math.round` instead of banker's rounding.** Several EU jurisdictions require round-half-to-even. A €0.5 rounding error repeated over thousands of invoices triggers an audit flag.
- **Caching VIES validation results.** VAT numbers can be deregistered. Re-validate on every B2B order; only cache the tax rate, not the VAT validity.
- **Zero-rating without recording the VAT number.** Your audit trail must store the VAT number, validation timestamp, and VIES response for every zero-rated B2B transaction.
- **Treating SaaS the same as physical goods for EU VAT.** Under the EU digital services rules, SaaS sold to EU consumers is taxed at the buyer's country rate, not the seller's country rate.

## Gotchas

- VIES is frequently unavailable during EU business hours (up to 30% error rate for some country endpoints). Set a tight timeout (3 s) and fall back to charging VAT rather than zero-rating on error.
- `AbortSignal.timeout()` is available in Workers runtime; do not use `setTimeout` + `AbortController` — it does not behave the same in the Workers scheduler.
- Tax-inclusive pricing requires dividing `lineSubtotal / (1 + rate)`, not `lineSubtotal * (1 - rate)`. The latter is wrong and understates the tax by a small but auditable amount.
- US county names in tax tables are lowercase and may include spaces. Normalize both the lookup key and the stored county name to lowercase before comparison.

## Verification

```bash
# US sales tax — California, Los Angeles County:
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"sku":"plan_pro","description":"Pro Plan","unitPrice":9999,"quantity":1,"taxCategory":"saas"}],"address":{"country":"US","state":"CA","county":"los angeles"},"taxInclusive":false}'

# EU B2B zero-rate (DE VAT number):
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"sku":"plan_pro","description":"Pro Plan","unitPrice":9999,"quantity":1,"taxCategory":"saas"}],"address":{"country":"DE","vatNumber":"DE123456789"},"taxInclusive":false}'
# Expect taxTotal: 0, vatValidated: true

# Check KV cache:
wrangler kv key get --binding TAX_KV 'tax:us:ca:los angeles'
```

## Related

- `documentation/docs/policies/payments/workers-refund-automation-pipeline.md`
- `documentation/docs/policies/payments/workers-stripe-webhook-idempotency.md`

## Sources

- EU Digital Services VAT: https://ec.europa.eu/taxation_customs/business/vat/telecommunications-broadcasting-electronic-services_en
- VIES API: https://ec.europa.eu/taxation_customs/vies/#/technical-information
- Stripe Tax: https://stripe.com/docs/tax
- US Sales Tax by county: https://www.taxjar.com/sales-tax/
- Banker's Rounding: https://en.wikipedia.org/wiki/Rounding#Rounding_half_to_even
