# Afterpay / Clearpay BNPL Integration via Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to offer Afterpay (US/AU/CA/NZ) or Clearpay (UK/EU) buy-now-pay-later directly
through the Afterpay Merchant API — not through a Stripe/Adyen abstraction — to keep fee
rates negotiated directly and receive native instalment data in your webhooks.

## Context
Afterpay and Clearpay are the same product under different brand names; their Merchant API
is unified (`global-api.afterpay.com`). The payment flow is a redirect: your Worker creates a
checkout session, sends the consumer to Afterpay's hosted page, and receives a token on
redirect back. Your Worker then captures the token to confirm the order. Webhooks notify you
of payment events asynchronously. Workers are well-suited because the API calls are
stateless HTTP and the redirect callback handling needs no persistent server.

---

## Creating an Afterpay Checkout Session

Afterpay uses HTTP Basic Auth (`merchantId:secretKey`) and an HMAC-based request signing
header for webhook verification. Session creation posts an order object and returns a
`redirectCheckoutUrl`.

```typescript
// src/afterpay.ts
export interface Env {
  AFTERPAY_MERCHANT_ID: string;
  AFTERPAY_SECRET_KEY: string;
  AFTERPAY_ENVIRONMENT: 'sandbox' | 'production';
  DB: D1Database;
}

const BASE_URL = {
  sandbox: 'https://global-api.afterpay.com',
  production: 'https://global-api.afterpay.com',
};

interface AfterpayConsumer {
  givenNames: string;
  surname: string;
  email: string;
  phoneNumber?: string;
}

interface AfterpayAddress {
  name: string;
  line1: string;
  area1: string; // city
  region: string; // state/county
  postcode: string;
  countryCode: string; // ISO 3166-1 alpha-2
  phoneNumber?: string;
}

interface AfterpayOrderItem {
  name: string;
  sku: string;
  quantity: number;
  price: { amount: string; currency: string };
}

interface AfterpayCheckoutRequest {
  amount: { amount: string; currency: string };
  consumer: AfterpayConsumer;
  billing: AfterpayAddress;
  shipping: AfterpayAddress;
  items: AfterpayOrderItem[];
  merchant: {
    redirectConfirmUrl: string;
    redirectCancelUrl: string;
  };
  merchantReference: string; // your internal order ID
}

interface AfterpayCheckoutResponse {
  token: string;
  expires: string;
  redirectCheckoutUrl: string;
}

function basicAuth(env: Env): string {
  return `Basic ${btoa(`${env.AFTERPAY_MERCHANT_ID}:${env.AFTERPAY_SECRET_KEY}`)}`;
}

export async function createCheckout(
  order: AfterpayCheckoutRequest,
  env: Env
): Promise<AfterpayCheckoutResponse> {
  const url = `${BASE_URL[env.AFTERPAY_ENVIRONMENT]}/v2/checkouts`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: basicAuth(env),
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(order),
  });

  if (!res.ok) {
    const err = await res.json<{ errorCode: string; message: string }>();
    throw new Error(`Afterpay checkout failed [${err.errorCode}]: ${err.message}`);
  }

  const data = await res.json<AfterpayCheckoutResponse>();

  // Persist the pending token for the redirect handler
  await env.DB.prepare(
    `INSERT INTO afterpay_sessions (token, merchant_reference, status, expires_at, created_at)
     VALUES (?, ?, 'pending', ?, unixepoch())`
  )
    .bind(data.token, order.merchantReference, Math.floor(new Date(data.expires).getTime() / 1000))
    .run();

  return data;
}
```

## Capturing the Payment After Redirect

Afterpay redirects back to `redirectConfirmUrl?orderToken=<token>&status=SUCCESS`. Your
Worker calls the capture endpoint to confirm the charge.

```typescript
// src/afterpay-capture.ts
interface AfterpayOrderCapture {
  token: string;
  merchantReference: string;
}

interface AfterpayCaptureResponse {
  id: string; // Afterpay payment ID
  status: 'APPROVED' | 'DECLINED' | 'PENDING';
  totalAmount: { amount: string; currency: string };
  merchantReference: string;
  created: string;
  events: Array<{ id: string; type: string; created: string }>;
  orderDetails: { orderItems: AfterpayOrderItem[] };
}

export async function capturePayment(
  token: string,
  merchantReference: string,
  env: Env
): Promise<AfterpayCaptureResponse> {
  const url = `${BASE_URL[env.AFTERPAY_ENVIRONMENT]}/v2/payments/capture`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: basicAuth(env),
      'Content-Type': 'application/json',
      // Idempotency: same token always produces same result
      'X-Payment-Idempotency-Key': token,
    },
    body: JSON.stringify({ token, merchantReference } as AfterpayOrderCapture),
  });

  if (!res.ok) {
    const err = await res.json<{ errorCode: string; message: string }>();
    throw new Error(`Afterpay capture failed [${err.errorCode}]: ${err.message}`);
  }

  const payment = await res.json<AfterpayCaptureResponse>();

  await env.DB.prepare(
    `UPDATE afterpay_sessions
     SET status = ?, afterpay_payment_id = ?, captured_at = unixepoch()
     WHERE token = ?`
  )
    .bind(payment.status === 'APPROVED' ? 'captured' : 'declined', payment.id, token)
    .run();

  return payment;
}
```

## Webhook Verification and Event Handling

Afterpay signs webhooks with HMAC-SHA256. Verify before processing.

```typescript
// src/afterpay-webhook.ts
async function verifyAfterpaySignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );
  const sigBytes = hexToUint8Array(signature);
  const bodyBytes = new TextEncoder().encode(body);
  return crypto.subtle.verify('HMAC', key, sigBytes, bodyBytes);
}

function hexToUint8Array(hex: string): Uint8Array {
  const pairs = hex.match(/.{1,2}/g) ?? [];
  return new Uint8Array(pairs.map((b) => parseInt(b, 16)));
}

export async function handleAfterpayWebhook(
  req: Request,
  env: Env
): Promise<Response> {
  const body = await req.text();
  const signature = req.headers.get('X-Afterpay-Signature') ?? '';

  const valid = await verifyAfterpaySignature(
    body,
    signature,
    env.AFTERPAY_SECRET_KEY
  );
  if (!valid) return new Response('Invalid signature', { status: 400 });

  const event = JSON.parse(body) as {
    eventType: string;
    merchantReference: string;
    paymentId: string;
  };

  if (event.eventType === 'PAYMENT_CAPTURED') {
    await env.DB.prepare(
      `UPDATE afterpay_sessions SET status = 'confirmed' WHERE afterpay_payment_id = ?`
    )
      .bind(event.paymentId)
      .run();
  }

  return new Response('ok');
}
```

## Anti-patterns
- Calling the capture endpoint before verifying the `status=SUCCESS` query parameter from
  the redirect — tokens with `status=CANCELLED` will fail capture but waste an API call.
- Using `merchantReference` as an internal order ID without enforcing uniqueness in D1 — a
  duplicate can silently match a prior order during reconciliation.
- Skipping HMAC webhook verification — event spoofing can mark orders as paid without charge.
- Not storing the session `token` and `expires_at` — expired tokens (30 min by default)
  cannot be captured and the user must restart checkout.

## Gotchas
- Afterpay requires `amount.amount` as a decimal string (`"49.95"`), not cents integer;
  mixing up the format causes `INVALID_AMOUNT` errors.
- Clearpay (UK) uses the same API base URL but consumers see Clearpay branding; the
  `countryCode` in `billing`/`shipping` drives brand selection on the hosted page.
- The capture call is idempotent on the same `token` — safe to retry on Worker timeout.
- Afterpay's BNPL instalment schedule is opaque; you receive the full order total upfront
  and Afterpay bears consumer credit risk — your reconciliation only sees a single payout.
- Sandbox merchants must allowlist redirect URLs in the Afterpay merchant portal; mismatch
  causes a silent redirect to an error page with no API error code.

## Verification
```bash
# Ping the Afterpay API configuration endpoint
curl https://global-api.afterpay.com/v2/configuration \
  -u "MERCHANT_ID:SECRET_KEY" | jq '.maximumAmount'

# Check pending sessions
wrangler d1 execute DB \
  --command "SELECT token, merchant_reference, status, expires_at FROM afterpay_sessions ORDER BY created_at DESC LIMIT 10"
```

## Related
- `affirm-bnpl-workers-integration.md`
- `klarna-direct-api-workers-integration.md`
- `zip-sezzle-bnpl-workers-integration.md`
- `stripe-afterpay-integration.md`
- `payment-provider-abstraction.md`

## Sources
- https://developers.afterpay.com/afterpay-online/reference/create-checkout-1
- https://developers.afterpay.com/afterpay-online/reference/capture-payment-by-token
- https://developers.afterpay.com/afterpay-online/reference/webhook-events
- https://developers.cloudflare.com/workers/
- https://developers.afterpay.com/afterpay-online/docs/merchant-authentication
