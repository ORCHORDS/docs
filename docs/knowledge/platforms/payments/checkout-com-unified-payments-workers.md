# Checkout.com Unified Payments API on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to accept card payments (and local payment methods) via Checkout.com's Unified
Payments API from a Cloudflare Workers edge backend — including server-side payment
request creation, webhook signature verification, 3DS handling, and settlement
reconciliation in D1 — without spinning up a dedicated server.

## Context

Checkout.com's Unified Payments API (`/payments`) is a single endpoint that handles cards,
wallets, bank transfers, and local payment methods (iDEAL, Klarna, etc.) through a common
request shape. Key objects:

- **Payment request** — initiates authorisation or full capture.
- **Payment action** — returned for 3DS redirect or APM redirect flows.
- **Webhook notification** — signed with `Cko-Signature` (HMAC-SHA256 of the raw body with
  the webhook secret as key).

Workers sit between your frontend (which uses Checkout.com's Frames.js to tokenise the
card) and the Checkout.com backend, keeping the processing secret key server-side.

---

## 1. Creating a Payment Request

```typescript
// src/checkout/payment-request.ts
interface CheckoutPaymentRequest {
  source: {
    type: 'token';
    token: string;
  };
  amount: number; // minor currency units (e.g. cents)
  currency: string;
  capture: boolean;
  customer?: { email: string; name?: string };
  '3ds'?: { enabled: boolean };
  metadata?: Record<string, string>;
  reference?: string;
}

interface CheckoutPaymentResponse {
  id: string;
  status: string;
  approved: boolean;
  _links?: {
    redirect?: { href: string };
  };
}

export async function requestPayment(
  params: {
    token: string;
    amountMinorUnits: number;
    currency: string;
    email: string;
    orderId: string;
    enable3ds?: boolean;
  },
  env: Env
): Promise<CheckoutPaymentResponse> {
  const body: CheckoutPaymentRequest = {
    source: { type: 'token', token: params.token },
    amount: params.amountMinorUnits,
    currency: params.currency,
    capture: true,
    customer: { email: params.email },
    reference: params.orderId,
    '3ds': { enabled: params.enable3ds ?? true },
    metadata: { order_id: params.orderId },
  };

  const res = await fetch('https://api.checkout.com/payments', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CHECKOUT_SECRET_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Checkout.com payment failed: ${res.status} ${err}`);
  }

  return res.json<CheckoutPaymentResponse>();
}
```

---

## 2. Handling 3DS Redirect Flow

```typescript
// src/checkout/three-ds-handler.ts
export async function handlePaymentResult(
  request: Request,
  env: Env
): Promise<Response> {
  const { paymentToken, orderId } = await request.json<{
    paymentToken: string;
    orderId: string;
  }>();

  const result = await requestPayment(
    {
      token: paymentToken,
      amountMinorUnits: await getOrderAmount(orderId, env.DB),
      currency: 'USD',
      email: await getOrderEmail(orderId, env.DB),
      orderId,
      enable3ds: true,
    },
    env
  );

  // 3DS pending — return redirect URL to the client
  if (result.status === 'Pending' && result._links?.redirect?.href) {
    return Response.json({
      requiresAction: true,
      redirectUrl: result._links.redirect.href,
      paymentId: result.id,
    });
  }

  // Synchronous approval (frictionless)
  if (result.approved && result.status === 'Authorized') {
    await markOrderPaid(orderId, result.id, env.DB);
    return Response.json({ success: true, paymentId: result.id });
  }

  return Response.json({ success: false, status: result.status }, { status: 402 });
}

async function getOrderAmount(orderId: string, db: D1Database): Promise<number> {
  const row = await db
    .prepare('SELECT amount_minor FROM orders WHERE id = ?1')
    .bind(orderId)
    .first<{ amount_minor: number }>();
  if (!row) throw new Error(`Order not found: ${orderId}`);
  return row.amount_minor;
}

async function getOrderEmail(orderId: string, db: D1Database): Promise<string> {
  const row = await db
    .prepare('SELECT email FROM orders WHERE id = ?1')
    .bind(orderId)
    .first<{ email: string }>();
  if (!row) throw new Error(`Order not found: ${orderId}`);
  return row.email;
}

async function markOrderPaid(
  orderId: string,
  paymentId: string,
  db: D1Database
): Promise<void> {
  await db
    .prepare(
      `UPDATE orders SET status = 'paid', checkout_payment_id = ?1, paid_at = ?2
       WHERE id = ?3`
    )
    .bind(paymentId, new Date().toISOString(), orderId)
    .run();
}
```

---

## 3. Verifying Checkout.com Webhooks

```typescript
// src/checkout/webhook-verify.ts
export async function verifyCheckoutWebhook(
  rawBody: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(rawBody));
  const computed = Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return computed === signature.toLowerCase();
}

export async function handleCheckoutWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const rawBody = await request.text();
  const sig = request.headers.get('Cko-Signature') ?? '';

  if (!(await verifyCheckoutWebhook(rawBody, sig, env.CHECKOUT_WEBHOOK_SECRET))) {
    return new Response('Unauthorized', { status: 401 });
  }

  const event = JSON.parse(rawBody) as {
    type: string;
    data: { id: string; reference?: string; status?: string; amount?: number };
  };

  await env.DB.prepare(
    `INSERT INTO checkout_events (id, type, payment_id, reference, status, received_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6)
     ON CONFLICT(id) DO NOTHING`
  )
    .bind(
      crypto.randomUUID(),
      event.type,
      event.data.id,
      event.data.reference ?? null,
      event.data.status ?? null,
      new Date().toISOString()
    )
    .run();

  if (event.type === 'payment_approved' && event.data.reference) {
    await markOrderPaid(event.data.reference, event.data.id, env.DB);
  }

  return new Response('OK', { status: 200 });
}
```

---

## 4. Issuing a Partial Refund

```typescript
// src/checkout/refund.ts
export async function refundPayment(
  paymentId: string,
  amountMinorUnits: number,
  reference: string,
  env: Env
): Promise<string> {
  const res = await fetch(
    `https://api.checkout.com/payments/${paymentId}/refunds`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CHECKOUT_SECRET_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        amount: amountMinorUnits,
        reference,
      }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Checkout.com refund failed: ${res.status} ${err}`);
  }

  const data = await res.json<{ action_id: string }>();
  return data.action_id;
}
```

---

## Anti-patterns

- **Using the public key server-side** — `CHECKOUT_PUBLIC_KEY` is for Frames.js tokenisation
  in the browser only; the secret key (`sk_*`) must never reach the client.
- **Granting access after a `payment_approved` webhook without checking `approved: true`
  on the API response** — webhook delivery can be delayed; poll `GET /payments/{id}` to
  confirm before fulfilling.
- **Not storing `Cko-Signature` for audit** — logging webhook payloads without the signature
  makes replay-attack forensics impossible.
- **Sending card details directly** instead of using Checkout.com Frames.js or their mobile
  SDKs — Workers cannot store or forward raw PANs without full PCI DSS compliance scope.

## Gotchas

- Checkout.com uses `Bearer` auth for the new Unified Payments API but `Basic` auth for
  some legacy endpoints; confirm the endpoint version before setting `Authorization`.
- The `Cko-Signature` header is lowercase hex of HMAC-SHA256; some Checkout.com docs show
  it as base64 — it is hex.
- Sandbox (`api.sandbox.checkout.com`) uses separate API keys from production; they are not
  interchangeable.
- `capture: false` creates an authorisation hold only; you must call
  `POST /payments/{id}/captures` separately within the authorisation window (typically 7
  days for cards).
- Response HTTP status 202 (Accepted, pending 3DS) is not an error; check `status` in the
  body, not just the HTTP code.

## Verification

```bash
# Confirm a payment was recorded in D1
wrangler d1 execute DB --command \
  "SELECT id, status, checkout_payment_id, paid_at FROM orders ORDER BY paid_at DESC LIMIT 5"

# Simulate a webhook locally with signature
BODY='{"type":"payment_approved","data":{"id":"pay_abc","reference":"order_123"}}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$CHECKOUT_WEBHOOK_SECRET" -hex | awk '{print $2}')
curl -X POST http://localhost:8787/webhooks/checkout \
  -H "Content-Type: application/json" \
  -H "Cko-Signature: $SIG" \
  -d "$BODY"
```

## Related

- `stripe-3ds-authentication.md`
- `sca-3d-secure-2-psd2-authentication.md`
- `partial-refund-handling.md`
- `pci-dss-saq-a-compliance.md`

## Sources

- https://www.checkout.com/docs/payments/accept-payments/accept-a-payment-via-the-api
- https://www.checkout.com/docs/payments/3d-secure
- https://www.checkout.com/docs/workflows-and-events/webhooks
- https://developers.cloudflare.com/workers/
