# Affirm Buy Now Pay Later: Direct API on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want to offer Affirm installment financing at checkout without routing through Stripe.
The direct Affirm API gives control over checkout flow, promotional messaging, and settlement
timing. Workers create and authorize Affirm checkout objects, handle the post-approval redirect,
and capture charges; D1 records loan state for reconciliation.

## Context

Affirm's direct integration uses a two-step model: (1) create a `checkout` server-side, (2)
redirect the user to Affirm's hosted UI where they select a payment plan, and (3) receive a
one-time `checkout_token` on redirect-back which your Worker exchanges for a charge. All
server-side API calls use HTTP Basic auth (public key + private key). HMAC-SHA256 signing is
required on the checkout object to prevent tampering. Affirm is US-only and requires USD amounts
in cents (integer).

## HMAC-SHA256 Checkout Signing

```typescript
// src/lib/affirm-sign.ts
// Affirm requires the merchant to sign the checkout object to prevent replay attacks

export async function signAffirmCheckout(
  checkoutObject: Record<string, unknown>,
  financialProductKey: string
): Promise<string> {
  // Affirm signing: HMAC-SHA256 over the serialized checkout, keyed by the financial product key
  const message = JSON.stringify(checkoutObject);
  const keyBytes = new TextEncoder().encode(financialProductKey);
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Create Affirm Checkout Object

```typescript
// src/handlers/affirm-create-checkout.ts
interface Env {
  AFFIRM_PUBLIC_KEY: string;
  AFFIRM_PRIVATE_KEY: string;
  AFFIRM_FINANCIAL_PRODUCT_KEY: string;
  AFFIRM_BASE_URL: string; // https://api.affirm.com (prod) or https://sandbox.affirm.com
  DB: D1Database;
}

interface AffirmCheckoutItem {
  display_name: string;
  sku: string;
  unit_price: number;   // cents
  qty: number;
  item_image_url?: string;
  item_url?: string;
}

interface AffirmCheckoutResponse {
  redirect_url: string;
  token: string;
}

export async function createAffirmCheckout(
  env: Env,
  orderId: string,
  items: AffirmCheckoutItem[],
  shippingAmountCents: number,
  taxAmountCents: number,
  customer: { name: string; email: string; phone?: string },
  shippingAddress: { line1: string; city: string; state: string; zipcode: string; country: string }
): Promise<AffirmCheckoutResponse> {
  const itemsTotal = items.reduce((sum, i) => sum + i.unit_price * i.qty, 0);
  const total = itemsTotal + shippingAmountCents + taxAmountCents;

  const checkoutBody = {
    merchant: {
      public_api_key: env.AFFIRM_PUBLIC_KEY,
      user_cancel_url: `https://yourdomain.com/checkout/cancel?order=${orderId}`,
      user_confirmation_url: `https://yourdomain.com/checkout/confirm?order=${orderId}`,
      user_confirmation_url_action: 'GET',
    },
    shipping: {
      name: { full: customer.name },
      address: shippingAddress,
      email: customer.email,
      phone_number: customer.phone,
    },
    billing: {
      name: { full: customer.name },
      address: shippingAddress,
      email: customer.email,
    },
    items: items.map(item => ({
      display_name: item.display_name,
      sku: item.sku,
      unit_price: item.unit_price,
      qty: item.qty,
      item_image_url: item.item_image_url,
      item_url: item.item_url,
    })),
    discounts: {},
    metadata: { order_id: orderId, platform_type: 'cloudflare_workers' },
    order_id: orderId,
    shipping_amount: shippingAmountCents,
    tax_amount: taxAmountCents,
    total: total,
    currency: 'USD',
  };

  // Sign checkout to prevent tampering
  const signature = await signAffirmCheckout(checkoutBody, env.AFFIRM_FINANCIAL_PRODUCT_KEY);

  const res = await fetch(`${env.AFFIRM_BASE_URL}/api/v2/checkout`, {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(`${env.AFFIRM_PUBLIC_KEY}:${env.AFFIRM_PRIVATE_KEY}`)}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...checkoutBody, merchant_external_reference: signature }),
  });

  if (!res.ok) throw new Error(`Affirm checkout creation failed: ${await res.text()}`);

  const result = await res.json<AffirmCheckoutResponse>();

  await env.DB.prepare(
    `INSERT INTO affirm_checkouts (order_id, affirm_token, total_cents, status, created_at)
     VALUES (?, ?, ?, 'pending', ?)`
  ).bind(orderId, result.token, total, Date.now()).run();

  return result;
}
```

## Authorize and Capture

```typescript
// src/handlers/affirm-authorize.ts
// Affirm sends checkout_token via redirect to user_confirmation_url

export async function authorizeAffirmCharge(
  env: Env,
  checkoutToken: string,
  orderId: string
): Promise<{ chargeId: string; amount: number }> {
  const res = await fetch(`${env.AFFIRM_BASE_URL}/api/v2/charges`, {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(`${env.AFFIRM_PUBLIC_KEY}:${env.AFFIRM_PRIVATE_KEY}`)}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ checkout_token: checkoutToken, order_id: orderId }),
  });

  if (!res.ok) {
    const err = await res.json<{ field: string; message: string; code: string }>();
    throw new Error(`Affirm authorize failed: ${err.message} (${err.code})`);
  }

  const charge = await res.json<{ id: string; amount: number; status: string }>();

  await env.DB.prepare(
    `UPDATE affirm_checkouts SET charge_id = ?, status = ?, authorized_at = ? WHERE order_id = ?`
  ).bind(charge.id, charge.status, Date.now(), orderId).run();

  return { chargeId: charge.id, amount: charge.amount };
}

async function captureAffirmCharge(
  env: Env,
  chargeId: string,
  orderId: string,
  shippingCarrier?: string,
  trackingNumber?: string
): Promise<void> {
  const body: Record<string, unknown> = { order_id: orderId };
  if (shippingCarrier && trackingNumber) {
    body.shipping_carrier = shippingCarrier;
    body.shipping_confirmation = trackingNumber;
  }

  const res = await fetch(`${env.AFFIRM_BASE_URL}/api/v2/charges/${chargeId}/capture`, {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(`${env.AFFIRM_PUBLIC_KEY}:${env.AFFIRM_PRIVATE_KEY}`)}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`Affirm capture failed: ${await res.text()}`);

  await env.DB.prepare(
    `UPDATE affirm_checkouts SET status = 'captured', captured_at = ? WHERE charge_id = ?`
  ).bind(Date.now(), chargeId).run();
}
```

## Void and Refund

```typescript
async function voidAffirmCharge(env: Env, chargeId: string): Promise<void> {
  const res = await fetch(`${env.AFFIRM_BASE_URL}/api/v2/charges/${chargeId}/void`, {
    method: 'POST',
    headers: { 'Authorization': `Basic ${btoa(`${env.AFFIRM_PUBLIC_KEY}:${env.AFFIRM_PRIVATE_KEY}`)}` },
  });
  if (!res.ok) throw new Error(`Affirm void failed: ${await res.text()}`);
  await env.DB.prepare(
    `UPDATE affirm_checkouts SET status = 'voided', voided_at = ? WHERE charge_id = ?`
  ).bind(Date.now(), chargeId).run();
}

async function refundAffirmCharge(env: Env, chargeId: string, amountCents: number): Promise<void> {
  const res = await fetch(`${env.AFFIRM_BASE_URL}/api/v2/charges/${chargeId}/refund`, {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(`${env.AFFIRM_PUBLIC_KEY}:${env.AFFIRM_PRIVATE_KEY}`)}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ amount: amountCents }),
  });
  if (!res.ok) throw new Error(`Affirm refund failed: ${await res.text()}`);
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS affirm_checkouts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id      TEXT NOT NULL UNIQUE,
  affirm_token  TEXT,
  charge_id     TEXT,
  total_cents   INTEGER NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  created_at    INTEGER NOT NULL,
  authorized_at INTEGER,
  captured_at   INTEGER,
  voided_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_affirm_charge ON affirm_checkouts(charge_id);
CREATE INDEX IF NOT EXISTS idx_affirm_order  ON affirm_checkouts(order_id);
```

## Anti-patterns

- **Capturing before shipping** — Affirm's merchant agreement typically requires capture within
  30 days of authorization and may mandate capture only after shipping. Capture in the shipment
  webhook, not at order creation.
- **Skipping the HMAC signature on the checkout object** — the signature prevents cart-price
  manipulation between the client and Affirm's hosted page. Never omit it.
- **Using `checkout_token` more than once** — tokens are single-use. Attempting to authorize a
  previously-used token returns a 400 `checkout-token-already-used` error.
- **Passing item totals that don't sum to `total`** — Affirm validates that
  `items total + shipping_amount + tax_amount == total`. Mismatches cause checkout rejection.

## Gotchas

- Affirm charges a merchant fee per transaction (typically 5–6% + fixed fee). This is deducted
  from settlement, not billed separately. Account for it in reconciliation.
- The `checkout_token` arrives as a query parameter on `user_confirmation_url`. Your Worker
  redirect handler must extract it from `?checkout_token=` before calling authorize.
- Affirm is US-only and USD-only as of 2026. For Canadian users, Affirm operates separately
  under the Affirm Canada entity with different credentials.
- The Affirm promotional messaging widget (`Affirm.ui.refresh()`) is a client-side JS snippet
  that renders monthly payment estimates. It requires the public key only — no server call needed.
- Sandbox environment: `https://sandbox.affirm.com`; test card: any real-format card number is
  accepted in sandbox without real charges.

## Verification

```bash
# Create a sandbox checkout and get redirect_url
curl -s -X POST https://sandbox.affirm.com/api/v2/checkout \
  -H "Authorization: Basic $(echo -n 'SANDBOX_PUB_KEY:SANDBOX_PRIV_KEY' | base64)" \
  -H 'Content-Type: application/json' \
  -d '{"merchant":{"public_api_key":"SANDBOX_PUB_KEY","user_cancel_url":"https://example.com/cancel","user_confirmation_url":"https://example.com/confirm","user_confirmation_url_action":"GET"},"items":[{"display_name":"Widget","sku":"SKU1","unit_price":5000,"qty":1}],"total":5000,"currency":"USD","order_id":"test_001"}' | jq '.redirect_url'

# Check D1 for affirm checkout rows
wrangler d1 execute YOUR_DB --command "SELECT order_id, status, total_cents FROM affirm_checkouts ORDER BY created_at DESC LIMIT 5;"
```

## Related

- `stripe-klarna-bnpl.md`
- `stripe-afterpay-integration.md`
- `payment-state-machine-design.md`
- `payment-audit-logging.md`
- `partial-refund-handling.md`
- `chargeback-prevention.md`

## Sources

- https://docs.affirm.com/affirm-developers/docs/direct-api-overview
- https://docs.affirm.com/affirm-developers/reference/create-checkout
- https://docs.affirm.com/affirm-developers/reference/create-charge
- https://docs.affirm.com/affirm-developers/reference/capture-charge
- https://docs.affirm.com/affirm-developers/docs/testing
