# PCI DSS Scope Reduction with Cloudflare Workers as a Proxy

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your origin server is included in PCI DSS scope because checkout requests route through it, even though you use a third-party payment processor. You want to prove to a QSA (Qualified Security Assessor) that raw card data never reaches your infrastructure, reducing your compliance surface to SAQ A.

## Context

PCI DSS scope is determined by data flow, not by processing intent. If a network packet containing a PAN (Primary Account Number) traverses a system — even in transit — that system is in scope. The goal is to architect the flow so card data travels only from the browser directly to the payment processor (Stripe.js / hosted fields), and your Workers handle only non-card request fields.

Cloudflare is a PCI DSS Level 1 Service Provider. Its network and the Workers runtime are within Cloudflare's compliance boundary, which means Workers can validly sit in the data path for card-present (CP) tokenisation without expanding your *own* PCI scope — provided your Workers never read, log, or forward the raw PAN.

## Solution

### 1. Architecture Overview

```
Browser
  ├─ Stripe.js (hosted fields) ──► Stripe API (card data stays here)
  │                                 └─ returns: paymentMethod.id (pm_xxx)
  │
  └─ POST /checkout  (non-card fields only)
       { pm_xxx, amount, currency, customerId, shippingAddress }
            │
            ▼
      Cloudflare Worker  ──► validates non-card fields
            │               ──► logs audit event (no PAN)
            ▼
      Origin API server  ──► calls Stripe with pm_xxx
            │
            ▼
        Stripe
```

The Worker's role:
1. Accept the checkout payload (which contains a Stripe token/pm ID, not raw card data).
2. Validate non-card fields (amount, currency, customer ID).
3. Enforce rate limiting and fraud signals.
4. Log an audit event noting the transaction type (card-not-present).
5. Forward the sanitised request to the origin.

### 2. Checkout Payload Validation (Worker)

```typescript
// src/handlers/checkout/proxy.ts
import { Env } from '../../types';

// Fields that are NEVER allowed in the payload routed through our Worker
const FORBIDDEN_FIELD_PATTERNS = [
  /card_?number/i,
  /cvv|cvc|csc/i,
  /expir/i,
  /pan\b/i,
];

export interface CheckoutPayload {
  paymentMethodId: string;   // pm_xxx — Stripe tokenised reference
  amountCents: number;
  currency: string;
  customerId: string;
  orderId: string;
  shippingAddress?: ShippingAddress;
}

interface ShippingAddress {
  line1: string;
  city: string;
  country: string;
  postalCode: string;
}

export async function handleCheckoutProxy(
  request: Request,
  env: Env
): Promise<Response> {
  // 1. Read and parse body
  const rawBody = await request.text();
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return new Response('Invalid JSON', { status: 400 });
  }

  // 2. Scan for forbidden card-data fields
  const flatKeys = Object.keys(flattenObject(payload));
  for (const key of flatKeys) {
    for (const pattern of FORBIDDEN_FIELD_PATTERNS) {
      if (pattern.test(key)) {
        await logAuditEvent(env, {
          type: 'pci_violation_attempt',
          offendingKey: key,
          ip: request.headers.get('CF-Connecting-IP') ?? 'unknown',
          country: (request as any).cf?.country ?? 'unknown',
          timestamp: new Date().toISOString(),
        });
        return new Response(
          JSON.stringify({ error: 'Card data must not be sent to this endpoint' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }
    }
  }

  // 3. Validate required non-card fields
  const checkout = payload as Partial<CheckoutPayload>;
  if (
    !checkout.paymentMethodId?.startsWith('pm_') ||
    typeof checkout.amountCents !== 'number' ||
    checkout.amountCents <= 0 ||
    !checkout.currency ||
    !checkout.customerId ||
    !checkout.orderId
  ) {
    return new Response(
      JSON.stringify({ error: 'Missing or invalid required fields' }),
      { status: 422, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // 4. Log clean audit event
  await logAuditEvent(env, {
    type: 'checkout_proxied',
    transactionType: 'card_not_present',
    orderId: checkout.orderId,
    customerId: checkout.customerId,
    amountCents: checkout.amountCents,
    currency: checkout.currency,
    paymentMethodPrefix: checkout.paymentMethodId.slice(0, 8), // pm_xxxx — safe to log
    ip: request.headers.get('CF-Connecting-IP') ?? 'unknown',
    country: (request as any).cf?.country ?? 'unknown',
    timestamp: new Date().toISOString(),
  });

  // 5. Forward sanitised request to origin — no card data ever written here
  const originUrl = new URL(request.url);
  originUrl.hostname = env.ORIGIN_HOSTNAME;

  const originResponse = await fetch(originUrl.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Forwarded-For': request.headers.get('CF-Connecting-IP') ?? '',
      'X-PCI-Proxy': '1',  // Signal to origin that Worker has validated
      Authorization: `Bearer ${env.ORIGIN_API_KEY}`,
    },
    body: JSON.stringify({
      paymentMethodId: checkout.paymentMethodId,
      amountCents: checkout.amountCents,
      currency: checkout.currency,
      customerId: checkout.customerId,
      orderId: checkout.orderId,
      shippingAddress: checkout.shippingAddress,
    }),
  });

  return new Response(originResponse.body, {
    status: originResponse.status,
    headers: originResponse.headers,
  });
}

function flattenObject(
  obj: Record<string, unknown>,
  prefix = ''
): Record<string, unknown> {
  return Object.entries(obj).reduce((acc, [key, val]) => {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
      Object.assign(acc, flattenObject(val as Record<string, unknown>, fullKey));
    } else {
      acc[fullKey] = val;
    }
    return acc;
  }, {} as Record<string, unknown>);
}
```

### 3. Audit Logging to D1

```typescript
// src/services/auditLog.ts
import { Env } from '../types';

export interface AuditEvent {
  type: string;
  transactionType?: 'card_present' | 'card_not_present';
  orderId?: string;
  customerId?: string;
  amountCents?: number;
  currency?: string;
  paymentMethodPrefix?: string;
  offendingKey?: string;
  ip: string;
  country: string;
  timestamp: string;
}

export async function logAuditEvent(
  env: Env,
  event: AuditEvent
): Promise<void> {
  // Log to D1 for queryable audit trail
  await env.DB.prepare(`
    INSERT INTO pci_audit_log
      (event_type, transaction_type, order_id, customer_id,
       amount_cents, currency, payment_method_prefix,
       offending_key, ip_address, country_code, event_timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)
    .bind(
      event.type,
      event.transactionType ?? null,
      event.orderId ?? null,
      event.customerId ?? null,
      event.amountCents ?? null,
      event.currency ?? null,
      event.paymentMethodPrefix ?? null,
      event.offendingKey ?? null,
      event.ip,
      event.country,
      event.timestamp
    )
    .run();
}
```

### 4. Audit Log D1 Schema

```sql
-- migrations/005_pci_audit.sql
CREATE TABLE IF NOT EXISTS pci_audit_log (
  id                    TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  event_type            TEXT NOT NULL,  -- checkout_proxied | pci_violation_attempt
  transaction_type      TEXT,           -- card_present | card_not_present
  order_id              TEXT,
  customer_id           TEXT,
  amount_cents          INTEGER,
  currency              TEXT,
  payment_method_prefix TEXT,           -- first 8 chars of pm_xxx — not a PAN
  offending_key         TEXT,           -- for violation attempts
  ip_address            TEXT NOT NULL,
  country_code          TEXT NOT NULL,
  event_timestamp       TEXT NOT NULL,
  created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Retain for 13 months (PCI DSS requirement 10.7)
CREATE INDEX idx_pci_audit_ts ON pci_audit_log (event_timestamp);
CREATE INDEX idx_pci_audit_type ON pci_audit_log (event_type, event_timestamp);
```

### 5. Network Segmentation — wrangler.toml Route

```toml
# wrangler.toml
name = "checkout-pci-proxy"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# Only route the checkout endpoint through the Worker
# All other traffic goes directly to origin
[[routes]]
pattern = "checkout.yourplatform.com/checkout"
zone_name = "yourplatform.com"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id = "<your-d1-id>"

[vars]
ORIGIN_HOSTNAME = "api-internal.yourplatform.com"

# Secrets (wrangler secret put):
# ORIGIN_API_KEY
# ADMIN_TOKEN
```

### 6. Stripe.js Integration (Frontend)

```typescript
// frontend/checkout.ts — runs in the browser, NEVER in a Worker
import { loadStripe } from '@stripe/stripe-js';

const stripe = await loadStripe('pk_live_xxx');
const elements = stripe.elements();
const cardElement = elements.create('card');
cardElement.mount('#card-element');

document.getElementById('checkout-form')!.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Tokenise in the browser — raw PAN goes Stripe ↔ browser only
  const { paymentMethod, error } = await stripe.createPaymentMethod({
    type: 'card',
    card: cardElement,
  });

  if (error || !paymentMethod) {
    console.error(error);
    return;
  }

  // POST only the token to your Worker — zero card data in this payload
  const response = await fetch('/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      paymentMethodId: paymentMethod.id,  // pm_xxx
      amountCents: 4999,
      currency: 'usd',
      customerId: 'cus_xxx',
      orderId: 'ord_xxx',
    }),
  });

  const result = await response.json();
  console.log('Checkout result:', result);
});
```

### 7. Card-Present vs Card-Not-Present Audit Query

```sql
-- Transaction type breakdown for QSA evidence
SELECT
  date(event_timestamp)  AS audit_date,
  transaction_type,
  COUNT(*)               AS transaction_count,
  SUM(amount_cents)      AS total_amount_cents
FROM pci_audit_log
WHERE event_type = 'checkout_proxied'
  AND event_timestamp >= datetime('now', '-30 days')
GROUP BY audit_date, transaction_type
ORDER BY audit_date DESC, transaction_type;

-- Violation attempts (evidence of active controls)
SELECT
  date(event_timestamp) AS violation_date,
  offending_key,
  ip_address,
  country_code,
  COUNT(*) AS attempts
FROM pci_audit_log
WHERE event_type = 'pci_violation_attempt'
  AND event_timestamp >= datetime('now', '-30 days')
GROUP BY violation_date, offending_key, ip_address
ORDER BY violation_date DESC;
```

## Implementation Details

**SAQ A eligibility**: PCI DSS SAQ A applies when all cardholder data functions are outsourced to a PCI-compliant third party and your systems do not store, process, or transmit cardholder data. Stripe + Stripe.js (hosted fields) satisfies the processor requirement. This Worker architecture satisfies the network isolation requirement by ensuring no card data transits your Worker, origin, or network.

**`X-PCI-Proxy` header**: This header signals to the origin that the Worker has already validated and sanitised the request. The origin should verify this header comes from a known Cloudflare IP range (use Cloudflare's published IP list) and reject requests without it to prevent direct bypass.

**Flat-object scan**: The `flattenObject` utility recursively flattens nested JSON so a payload like `{ "card": { "number": "..." } }` still triggers the forbidden-field check.

**Audit log retention**: PCI DSS Requirement 10.7 mandates 12 months of audit log retention with 3 months immediately available. D1's storage is durable; implement a scheduled job to archive rows older than 90 days to R2.

## Anti-patterns

- **Logging `request.body` verbatim**: Even if you believe the body contains no card data, a misconfigured client might send a PAN. The Worker must parse and scan before logging — never log raw bodies.
- **Routing all traffic through the PCI proxy Worker**: Scope creep. Only the `/checkout` endpoint needs this treatment. Other endpoints (product listings, account management) should bypass the Worker to keep latency low.
- **Accepting card data as a fallback**: Some implementations fall back to accepting raw card data if the tokenisation step fails. This immediately expands PCI scope. Reject non-tokenised submissions unconditionally.
- **Trusting `X-PCI-Proxy` from any source**: If the origin blindly trusts this header, an attacker can set it on a direct request and bypass origin-side validation.

## Gotchas

- Workers cannot read `request.body` twice. Call `request.text()` once, then `JSON.parse` — never call both `request.text()` and `request.json()`.
- `CF-Connecting-IP` is the original client IP even behind Cloudflare's proxy. Do not log `X-Forwarded-For` which can be spoofed by the client.
- Cloudflare's PCI DSS attestation covers the network and runtime — it does not cover your Worker *code*. Your Worker code is your PCI scope.
- The `pm_xxx` payment method token is not a PAN and is safe to log. However, do not log the full token — `pm_xxx` prefixes are sufficient for tracing. The first 8 characters identify the payment method type without exposing sensitive data.
- D1 is not yet certified as a PCI DSS Level 1 data store. For PAN storage (e.g. storing tokenised card references) with strict PCI requirements, prefer Stripe's Customer API or a certified vault.

## Verification

```bash
# Verify clean payload passes through
curl -X POST https://checkout.yourplatform.com/checkout \
  -H 'Content-Type: application/json' \
  -d '{"paymentMethodId":"pm_1abc","amountCents":1000,\
"currency":"usd","customerId":"cus_1","orderId":"ord_1"}'
# Expect: 200 from origin

# Verify card data is rejected
curl -X POST https://checkout.yourplatform.com/checkout \
  -H 'Content-Type: application/json' \
  -d '{"card_number":"4242424242424242","paymentMethodId":"pm_1abc"}'
# Expect: 400 with error 'Card data must not be sent to this endpoint'

# Check audit log
wrangler d1 execute payments \
  --command "SELECT event_type, transaction_type, COUNT(*) FROM pci_audit_log GROUP BY 1,2;"
```

## Related

- `documentation/docs/policies/payments/workers-stripe-connect-oauth-flow.md`
- `documentation/docs/policies/payments/workers-tax-rate-lookup-kv-cache.md`

## Sources

- https://www.pcisecuritystandards.org/document_library/
- https://stripe.com/guides/pci-compliance
- https://developers.cloudflare.com/workers/
- https://www.cloudflare.com/trust-hub/compliance-resources/pci-dss/
- https://stripe.com/docs/js
