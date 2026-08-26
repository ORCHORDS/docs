# Stripe Tax Exemption Certificate Management with Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

B2B SaaS customers — nonprofits, government agencies, and resellers — frequently present tax exemption certificates to avoid sales tax on invoices. Stripe Tax does not natively store or validate exemption certificates; you must track certificate metadata yourself and apply the correct `tax_exempt` status to the Stripe Customer object before each invoice is finalized. Missing this step causes Stripe to charge and remit tax on exempt customers, triggering costly refund workflows or audit risk.

---

## Context

Stripe represents a customer's tax status via the `tax_exempt` field on the Customer object: `none` (default), `exempt` (government/nonprofit), or `reverse` (VAT reverse charge for B2B cross-border EU). When `tax_exempt` is set to `exempt`, Stripe Tax skips all tax line items on invoices for that customer.

The Workers + D1 layer handles:
1. Storing certificate metadata (certificate number, issuing state, expiry date, file path).
2. Validating expiry before each invoice finalization via a Stripe webhook.
3. Auto-revoking the `exempt` status when a certificate expires.

Certificate files are stored in R2; D1 holds structured metadata for fast queries.

---

## 1. D1 Schema

```sql
-- migrations/0001_exemption_certs.sql
CREATE TABLE IF NOT EXISTS tax_exemption_certificates (
  id              TEXT PRIMARY KEY,
  stripe_customer_id TEXT NOT NULL,
  certificate_number TEXT NOT NULL,
  issuing_state   TEXT NOT NULL,       -- ISO 3166-2 subdivision, e.g. 'US-CA'
  exemption_type  TEXT NOT NULL,       -- 'nonprofit' | 'government' | 'reseller'
  valid_from      TEXT NOT NULL,       -- ISO 8601 date
  expires_at      TEXT,               -- NULL = perpetual (rare)
  r2_object_key   TEXT NOT NULL,       -- path in R2 bucket
  status          TEXT NOT NULL DEFAULT 'active', -- 'active' | 'expired' | 'revoked'
  uploaded_at     TEXT NOT NULL,
  reviewed_by     TEXT                -- admin email
);

CREATE INDEX idx_certs_customer ON tax_exemption_certificates(stripe_customer_id);
CREATE INDEX idx_certs_expiry   ON tax_exemption_certificates(expires_at) WHERE status = 'active';
```

---

## 2. Certificate Upload and Stripe Customer Update

```typescript
// src/certificates.ts
import Stripe from 'stripe';

interface Env {
  DB: D1Database;
  CERT_BUCKET: R2Bucket;
  STRIPE_SECRET_KEY: string;
}

export async function uploadCertificate(
  env: Env,
  stripeCustomerId: string,
  file: File,
  meta: {
    certificateNumber: string;
    issuingState: string;
    exemptionType: 'nonprofit' | 'government' | 'reseller';
    validFrom: string;
    expiresAt?: string;
  }
): Promise<{ id: string }> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  const id = crypto.randomUUID();
  const key = `exemptions/${stripeCustomerId}/${id}.pdf`;

  // Store file in R2
  await env.CERT_BUCKET.put(key, file.stream(), {
    httpMetadata: { contentType: 'application/pdf' },
  });

  // Persist metadata in D1
  await env.DB.prepare(
    `INSERT INTO tax_exemption_certificates
     (id, stripe_customer_id, certificate_number, issuing_state, exemption_type,
      valid_from, expires_at, r2_object_key, status, uploaded_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)`
  )
    .bind(
      id,
      stripeCustomerId,
      meta.certificateNumber,
      meta.issuingState,
      meta.exemptionType,
      meta.validFrom,
      meta.expiresAt ?? null,
      key,
      new Date().toISOString()
    )
    .run();

  // Mark Stripe customer as exempt
  await stripe.customers.update(stripeCustomerId, { tax_exempt: 'exempt' });

  return { id };
}
```

---

## 3. Expiry Check Before Invoice Finalization

```typescript
// src/invoice-webhook.ts
import Stripe from 'stripe';

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
}

export async function handleInvoiceCreated(
  env: Env,
  invoice: Stripe.Invoice
): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
  const customerId = typeof invoice.customer === 'string'
    ? invoice.customer
    : invoice.customer?.id;

  if (!customerId) return;

  const now = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

  // Find an active, non-expired certificate for this customer
  const cert = await env.DB.prepare(
    `SELECT id, expires_at FROM tax_exemption_certificates
     WHERE stripe_customer_id = ?
       AND status = 'active'
       AND (expires_at IS NULL OR expires_at >= ?)
     ORDER BY uploaded_at DESC LIMIT 1`
  )
    .bind(customerId, now)
    .first<{ id: string; expires_at: string | null }>();

  if (!cert) {
    // No valid certificate — revoke exempt status
    await stripe.customers.update(customerId, { tax_exempt: 'none' });

    // Mark all active certs as expired
    await env.DB.prepare(
      `UPDATE tax_exemption_certificates
       SET status = 'expired'
       WHERE stripe_customer_id = ? AND status = 'active'`
    )
      .bind(customerId)
      .run();
  }
  // If cert is valid, tax_exempt is already 'exempt' — nothing to do
}
```

---

## 4. Stripe Webhook Handler

```typescript
// src/index.ts
import Stripe from 'stripe';
import { handleInvoiceCreated } from './invoice-webhook';

interface Env {
  DB: D1Database;
  CERT_BUCKET: R2Bucket;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    const body = await request.text();
    const sig  = request.headers.get('stripe-signature') ?? '';

    let event: Stripe.Event;
    try {
      event = await stripe.webhooks.constructEventAsync(body, sig, env.STRIPE_WEBHOOK_SECRET);
    } catch {
      return new Response('Invalid signature', { status: 400 });
    }

    if (event.type === 'invoice.created') {
      await handleInvoiceCreated(env, event.data.object as Stripe.Invoice);
    }

    return new Response(JSON.stringify({ received: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## 5. Scheduled Expiry Sweep (Cron Trigger)

```typescript
// src/index.ts — add to the same export default object

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const today = new Date().toISOString().split('T')[0];
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

    // Find certs that expired today
    const { results } = await env.DB.prepare(
      `SELECT id, stripe_customer_id
       FROM tax_exemption_certificates
       WHERE status = 'active' AND expires_at < ?`
    )
      .bind(today)
      .all<{ id: string; stripe_customer_id: string }>();

    for (const cert of results) {
      await env.DB.prepare(
        `UPDATE tax_exemption_certificates SET status = 'expired' WHERE id = ?`
      )
        .bind(cert.id)
        .run();

      // Only revoke if no other valid cert exists for the customer
      const activeCerts = await env.DB.prepare(
        `SELECT COUNT(*) as cnt FROM tax_exemption_certificates
         WHERE stripe_customer_id = ? AND status = 'active' AND (expires_at IS NULL OR expires_at >= ?)`
      )
        .bind(cert.stripe_customer_id, today)
        .first<{ cnt: number }>();

      if (!activeCerts || activeCerts.cnt === 0) {
        await stripe.customers.update(cert.stripe_customer_id, { tax_exempt: 'none' });
      }
    }
  },
```

```toml
# wrangler.toml
[[triggers]]
crons = ["0 6 * * *"]  # Run at 06:00 UTC daily

[[d1_databases]]
binding       = "DB"
database_name = "payments"
database_id   = "<your-d1-id>"

[[r2_buckets]]
binding     = "CERT_BUCKET"
bucket_name = "tax-certificates"
```

---

## Anti-patterns

- **Setting `tax_exempt = 'exempt'` at customer creation and never reviewing it** — certificates expire; automation must revert the flag or every lapsed certificate becomes a permanent exemption.
- **Storing PDF files in D1 BLOB columns** — R2 is the correct object store; D1 holds only the metadata key.
- **Applying exemption globally without state-level validation** — US exemption certificates are state-specific; a California certificate does not exempt sales in Texas.
- **Using `tax_exempt: 'reverse'` for US nonprofits** — `reverse` is for VAT reverse charge (EU B2B); US nonprofits require `exempt`.

---

## Gotchas

- Stripe finalizes `invoice.created` webhooks after a short settling window (typically 1 hour for subscription invoices); the webhook arrives before PDF generation, giving you time to update `tax_exempt` before tax is calculated.
- Stripe Tax only omits taxes if the customer's `tax_exempt` field is set **before** the invoice is finalized, not retroactively.
- Some states (e.g., Texas, Ohio) require the reseller to provide their own certificate number (not the buyer's); validate the `exemption_type` against state rules.
- `expires_at = NULL` should only be used for government entities that issue perpetual certificates; always prompt non-government uploaders for an expiry date.
- If you also use Stripe Tax with automatic tax enabled, ensure `customer.tax.ip_address` is set for accurate location detection — exemption only helps if the tax calculation runs first.

---

## Verification

```bash
# Check active certs for a customer
wrangler d1 execute payments \
  --command "SELECT * FROM tax_exemption_certificates WHERE stripe_customer_id = 'cus_test123' AND status = 'active'"

# Confirm Stripe customer tax_exempt field
stripe customers retrieve cus_test123 --api-key $STRIPE_SECRET_KEY | jq .tax_exempt
# Expected: "exempt" when a valid cert exists, "none" otherwise
```

---

## Related

- `stripe-tax-calculation.md`
- `stripe-tax-customer-location-evidence.md`
- `stripe-tax-registration-effective-date-controls.md`
- `avalara-tax-calculation-workers.md`
- `vat-calculation-eu.md`

---

## Sources

- https://docs.stripe.com/billing/taxes/tax-exempt-customers
- https://docs.stripe.com/tax/exempt-customers
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/r2/
- https://docs.stripe.com/api/customers/object#customer_object-tax_exempt
