# Stripe Tax API Integration on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Before creating a Stripe Checkout Session you need to calculate accurate tax (VAT, GST, sales tax) based on the customer's address and product tax codes. Your Cloudflare Worker proxies the Stripe Tax Calculation API, stores tax amounts in D1 per order, and generates a VAT invoice stub for EU customers.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 for order tax records
- Stripe Tax API: `POST /v1/tax/calculations`
- Stripe Checkout Sessions: created after tax calculation
- VAT invoice: stored as text in D1 (PDF generation deferred to separate pipeline)

---

## Step 1 - D1 Schema

```sql
-- migrations/0004_tax.sql
CREATE TABLE IF NOT EXISTS order_taxes (
  calculation_id   TEXT PRIMARY KEY,
  order_id         TEXT NOT NULL UNIQUE,
  customer_address TEXT NOT NULL,
  line_items       TEXT NOT NULL,
  tax_amount       INTEGER NOT NULL,   -- minor units
  amount_total     INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  expires_at       TEXT NOT NULL,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vat_invoices (
  invoice_id     TEXT PRIMARY KEY,
  order_id       TEXT NOT NULL UNIQUE,
  calculation_id TEXT NOT NULL,
  customer_name  TEXT,
  vat_number     TEXT,
  invoice_text   TEXT NOT NULL,
  issued_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (calculation_id) REFERENCES order_taxes(calculation_id)
);
```

---

## Step 2 - Stripe Tax Calculation

```typescript
// src/tax/calculate.ts
export interface LineItem {
  amount: number;       // minor units, tax-exclusive
  reference: string;
  taxCode: string;      // e.g. "txcd_10000000" for software
}

export interface CustomerAddress {
  line1: string;
  city: string;
  postal_code: string;
  country: string;      // ISO 3166-1 alpha-2
  state?: string;       // US only
}

export interface TaxCalculation {
  id: string;
  tax_amount_exclusive: number;
  amount_total: number;
  currency: string;
  expires_at: number;   // Unix timestamp
  line_items: {
    data: Array<{ amount: number; amount_tax: number; reference: string }>;
  };
}

export async function calculateTax(
  currency: string,
  lineItems: LineItem[],
  customerAddress: CustomerAddress,
  stripeKey: string
): Promise<TaxCalculation> {
  const params = new URLSearchParams();
  params.set('currency', currency.toLowerCase());
  params.set('customer_details[address][line1]', customerAddress.line1);
  params.set('customer_details[address][city]', customerAddress.city);
  params.set('customer_details[address][postal_code]', customerAddress.postal_code);
  params.set('customer_details[address][country]', customerAddress.country);
  if (customerAddress.state) {
    params.set('customer_details[address][state]', customerAddress.state);
  }
  params.set('customer_details[address_source]', 'billing');

  lineItems.forEach((item, i) => {
    params.set(`line_items[${i}][amount]`, String(item.amount));
    params.set(`line_items[${i}][reference]`, item.reference);
    params.set(`line_items[${i}][tax_code]`, item.taxCode);
  });

  const res = await fetch('https://api.stripe.com/v1/tax/calculations', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${stripeKey}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });

  const json = await res.json() as TaxCalculation & { error?: { message: string } };
  if (!res.ok) throw new Error(json.error?.message ?? 'Stripe Tax API error');
  return json;
}
```

---

## Step 3 - Persist Tax Data and Create Checkout Session

```typescript
// src/checkout/create-session.ts
import {
  calculateTax,
  type LineItem,
  type CustomerAddress,
  type TaxCalculation,
} from '../tax/calculate';

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

export async function createTaxedCheckoutSession(
  env: Env,
  orderId: string,
  currency: string,
  lineItems: LineItem[],
  customerAddress: CustomerAddress,
  successUrl: string,
  cancelUrl: string
): Promise<{ sessionUrl: string; taxCalculation: TaxCalculation }> {
  const tax = await calculateTax(
    currency,
    lineItems,
    customerAddress,
    env.STRIPE_SECRET_KEY
  );

  await env.DB
    .prepare(
      `INSERT OR REPLACE INTO order_taxes
       (calculation_id, order_id, customer_address, line_items,
        tax_amount, amount_total, currency, expires_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, datetime(?, 'unixepoch'))`
    )
    .bind(
      tax.id,
      orderId,
      JSON.stringify(customerAddress),
      JSON.stringify(lineItems),
      tax.tax_amount_exclusive,
      tax.amount_total,
      currency,
      tax.expires_at
    )
    .run();

  const params = new URLSearchParams();
  params.set('mode', 'payment');
  params.set('currency', currency.toLowerCase());
  params.set('automatic_tax[enabled]', 'true');
  params.set('tax_id_collection[enabled]', 'true');
  params.set('metadata[tax_calculation_id]', tax.id);
  params.set('metadata[order_id]', orderId);
  params.set('success_url', successUrl);
  params.set('cancel_url', cancelUrl);

  lineItems.forEach((item, i) => {
    const taxItem = tax.line_items.data[i];
    params.set(`line_items[${i}][price_data][currency]`, currency.toLowerCase());
    params.set(`line_items[${i}][price_data][product_data][name]`, item.reference);
    params.set(
      `line_items[${i}][price_data][unit_amount]`,
      String(item.amount + (taxItem?.amount_tax ?? 0))
    );
    params.set(`line_items[${i}][quantity]`, '1');
  });

  const sessionRes = await fetch(
    'https://api.stripe.com/v1/checkout/sessions',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    }
  );

  const session = await sessionRes.json() as {
    url: string;
    error?: { message: string };
  };
  if (!sessionRes.ok) {
    throw new Error(session.error?.message ?? 'Stripe Session error');
  }

  return { sessionUrl: session.url, taxCalculation: tax };
}
```

---

## Step 4 - VAT Invoice Generation

```typescript
// src/tax/vat-invoice.ts
import type { TaxCalculation, CustomerAddress } from './calculate';

export interface VatInvoiceInput {
  orderId: string;
  customerName: string;
  vatNumber?: string;
  customerAddress: CustomerAddress;
  tax: TaxCalculation;
  currency: string;
}

export function buildVatInvoiceText(input: VatInvoiceInput): string {
  const date = new Date().toISOString().split('T')[0];
  const subtotal = ((input.tax.amount_total - input.tax.tax_amount_exclusive) / 100).toFixed(2);
  const taxAmount = (input.tax.tax_amount_exclusive / 100).toFixed(2);
  const total = (input.tax.amount_total / 100).toFixed(2);
  const curr = input.currency.toUpperCase();

  return [
    'VAT INVOICE',
    '============',
    'Issued by:   Orchords Ltd, example.com',
    `Invoice date: ${date}`,
    `Order ID:    ${input.orderId}`,
    '',
    'Bill to:',
    `  ${input.customerName}`,
    input.vatNumber
      ? `  VAT No: ${input.vatNumber}`
      : '  (Private individual)',
    `  ${input.customerAddress.line1}, ${input.customerAddress.city}`,
    `  ${input.customerAddress.postal_code} ${input.customerAddress.country}`,
    '',
    `Subtotal (excl. VAT):  ${curr} ${subtotal}`,
    `VAT:                   ${curr} ${taxAmount}`,
    '------------------------------',
    `Total incl. VAT:       ${curr} ${total}`,
    '',
    `Stripe Tax Calculation: ${input.tax.id}`,
  ].join('\n');
}

export async function persistVatInvoice(
  db: D1Database,
  invoiceId: string,
  input: VatInvoiceInput
): Promise<void> {
  const text = buildVatInvoiceText(input);
  await db
    .prepare(
      `INSERT OR REPLACE INTO vat_invoices
       (invoice_id, order_id, calculation_id, customer_name, vat_number, invoice_text)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      invoiceId,
      input.orderId,
      input.tax.id,
      input.customerName,
      input.vatNumber ?? null,
      text
    )
    .run();
}
```

---

## Step 5 - Worker Entry Point

```typescript
// src/index.ts
import { createTaxedCheckoutSession } from './checkout/create-session';
import { persistVatInvoice } from './tax/vat-invoice';

const EU_COUNTRIES = new Set([
  'DE', 'FR', 'AT', 'NL', 'BE', 'ES', 'IT', 'PT', 'FI', 'SE', 'IE',
  'PL', 'DK', 'CZ', 'HU', 'RO', 'SK', 'BG', 'HR', 'LT', 'LV', 'EE',
  'SI', 'CY', 'LU', 'MT', 'GR',
]);

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/checkout') {
      return new Response('Not Found', { status: 404 });
    }

    const body = await request.json() as {
      orderId: string;
      currency: string;
      lineItems: Array<{ amount: number; reference: string; taxCode: string }>;
      customerAddress: CustomerAddress;
      customerName: string;
      vatNumber?: string;
    };

    const { sessionUrl, taxCalculation } = await createTaxedCheckoutSession(
      env,
      body.orderId,
      body.currency,
      body.lineItems,
      body.customerAddress,
      'https://example.com/success',
      'https://example.com/cancel'
    );

    if (EU_COUNTRIES.has(body.customerAddress.country)) {
      const invoiceId = `INV-${body.orderId}-${Date.now()}`;
      await persistVatInvoice(env.DB, invoiceId, {
        orderId: body.orderId,
        customerName: body.customerName,
        vatNumber: body.vatNumber,
        customerAddress: body.customerAddress,
        tax: taxCalculation,
        currency: body.currency,
      });
    }

    return Response.json({ sessionUrl });
  },
};
```

---

## Anti-patterns

- Do not calculate tax client-side or approximate with a flat rate - use the Stripe Tax API.
- Do not pass `automatic_tax[enabled]=true` without also collecting the customer address via `billing_address_collection=required`.
- Never store `tax_amount` as a float - always use integer minor units.
- Do not cache tax calculations beyond their `expires_at` timestamp.

## Gotchas

- Stripe Tax Calculation objects expire after 90 days; recalculate if the customer returns after abandonment.
- `tax_amount_exclusive` is the total tax; per-line taxes are in `line_items.data[n].amount_tax`.
- For B2B EU sales, collecting the customer's VAT number zero-rates the supply - this is a separate step.
- Workers CPU time limit applies across both the Tax API call and D1 write - `await` serially.

## Verification

```bash
# Apply schema
wrangler d1 migrations apply DB --env production

# Test checkout endpoint (Stripe test mode key)
curl -X POST https://my-worker.orchords.workers.dev/checkout \
  -H 'Content-Type: application/json' \
  -d '{
    "orderId": "ORD-TEST-001",
    "currency": "eur",
    "lineItems": [{"amount": 1000, "reference": "SKU-001", "taxCode": "txcd_10000000"}],
    "customerAddress": {"line1": "Musterstr. 1", "city": "Berlin", "postal_code": "10115", "country": "DE"},
    "customerName": "Max Mustermann"
  }'

# Verify tax record in D1
wrangler d1 execute DB --env production \
  --command "SELECT calculation_id, tax_amount, amount_total FROM order_taxes WHERE order_id='ORD-TEST-001'"

# Verify VAT invoice generated
wrangler d1 execute DB --env production \
  --command "SELECT invoice_id, invoice_text FROM vat_invoices WHERE order_id='ORD-TEST-001'"
```

## Related

- `documentation/docs/policies/payments/stripe-payment-link-webhook-fulfillment-workers.md`
- `documentation/docs/policies/payments/workers-subscription-dunning-retry-d1.md`

## Sources

- https://stripe.com/docs/tax/custom
- https://stripe.com/docs/api/tax/calculations/create
- https://stripe.com/docs/tax/checkout
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
