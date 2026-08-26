# Klarna Direct Orders API Integration on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You want to offer Klarna Pay Later, Pay Now, and Slice It (BNPL) directly via Klarna's own Orders API — not as a Stripe payment method — giving you control over order lines, shipping, captures, and refunds from a Cloudflare Worker, while keeping PCI scope minimal.

## Context

Klarna's Orders API (v3) is a REST interface backed by HTTP Basic Auth using your Klarna `username` (merchant ID) and `password` (API key). The integration flow is: create a Klarna session → render the Klarna Widget client-side → authorize → capture server-side from the Worker. Workers handle all server-side calls; the browser loads Klarna's JS SDK directly from Klarna's CDN (no self-hosting required). This is distinct from Stripe's Klarna support, which tunnels through Stripe's orchestration layer.

---

## 1. Creating a Klarna Session

A Klarna session provides the `client_token` the frontend JS SDK uses to render the payment widget.

```typescript
// src/klarna-session.ts
interface Env {
  KLARNA_USERNAME: string; // Merchant ID from Klarna portal
  KLARNA_PASSWORD: string; // API key from Klarna portal
  KLARNA_API_BASE: string; // https://api.playground.klarna.com (test) or https://api.klarna.com (prod)
}

interface KlarnaOrderLine {
  type: 'physical' | 'digital' | 'shipping_fee' | 'discount';
  reference: string;
  name: string;
  quantity: number;
  unit_price: number;   // in minor units (cents)
  tax_rate: number;     // in basis points (e.g. 2500 = 25%)
  total_amount: number;
  total_tax_amount: number;
}

interface SessionResponse {
  session_id: string;
  client_token: string;
  payment_method_categories: Array<{ identifier: string; name: string }>;
}

async function createKlarnaSession(
  env: Env,
  params: {
    orderId: string;
    purchaseCurrency: string;
    purchaseCountry: string;
    locale: string;
    orderAmount: number;
    orderLines: KlarnaOrderLine[];
  }
): Promise<SessionResponse> {
  const credentials = btoa(`${env.KLARNA_USERNAME}:${env.KLARNA_PASSWORD}`);

  const res = await fetch(`${env.KLARNA_API_BASE}/payments/v1/sessions`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${credentials}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      purchase_country: params.purchaseCountry,
      purchase_currency: params.purchaseCurrency,
      locale: params.locale,
      order_amount: params.orderAmount,
      order_lines: params.orderLines,
      merchant_reference1: params.orderId,
    }),
  });

  if (!res.ok) throw new Error(`Klarna session error: ${await res.text()}`);
  return res.json<SessionResponse>();
}

export { createKlarnaSession };
```

---

## 2. Worker Route — Session Endpoint

```typescript
// src/index.ts (session handler)
import { createKlarnaSession } from './klarna-session';

interface Env {
  KLARNA_USERNAME: string;
  KLARNA_PASSWORD: string;
  KLARNA_API_BASE: string;
  DB: D1Database;
}

export async function handleKlarnaSessionCreate(
  request: Request,
  env: Env
): Promise<Response> {
  const { orderId, currency, country, locale, orderAmount, orderLines } =
    await request.json<{
      orderId: string;
      currency: string;
      country: string;
      locale: string;
      orderAmount: number;
      orderLines: unknown[];
    }>();

  const session = await createKlarnaSession(env, {
    orderId,
    purchaseCurrency: currency,
    purchaseCountry: country,
    locale,
    orderAmount,
    orderLines: orderLines as any,
  });

  await env.DB.prepare(
    `INSERT INTO klarna_sessions (session_id, order_id, status, created_at)
     VALUES (?, ?, 'created', CURRENT_TIMESTAMP)
     ON CONFLICT(session_id) DO NOTHING`
  ).bind(session.session_id, orderId).run();

  return Response.json({
    clientToken: session.client_token,
    sessionId: session.session_id,
    paymentMethodCategories: session.payment_method_categories,
  });
}
```

---

## 3. Creating a Klarna Order (After Client Authorization)

After the user authorizes in the browser, Klarna returns an `authorization_token`. The Worker uses it to place the order.

```typescript
// src/klarna-order.ts
interface KlarnaOrderResponse {
  order_id: string;
  redirect_url: string;
  fraud_status: 'ACCEPTED' | 'PENDING' | 'REJECTED';
}

async function createKlarnaOrder(
  env: Env,
  authorizationToken: string,
  params: {
    orderId: string;
    purchaseCurrency: string;
    purchaseCountry: string;
    locale: string;
    orderAmount: number;
    orderLines: KlarnaOrderLine[];
    billingAddress: {
      given_name: string;
      family_name: string;
      email: string;
      street_address: string;
      postal_code: string;
      city: string;
      country: string;
    };
  }
): Promise<KlarnaOrderResponse> {
  const credentials = btoa(`${env.KLARNA_USERNAME}:${env.KLARNA_PASSWORD}`);

  const res = await fetch(
    `${env.KLARNA_API_BASE}/payments/v1/authorizations/${authorizationToken}/order`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        purchase_country: params.purchaseCountry,
        purchase_currency: params.purchaseCurrency,
        locale: params.locale,
        order_amount: params.orderAmount,
        order_lines: params.orderLines,
        billing_address: params.billingAddress,
        merchant_reference1: params.orderId,
      }),
    }
  );

  if (!res.ok) throw new Error(`Klarna order error: ${await res.text()}`);
  return res.json<KlarnaOrderResponse>();
}

export { createKlarnaOrder };
```

---

## 4. Capturing a Klarna Order

Klarna uses a separate capture call after physical/digital goods are dispatched.

```typescript
// src/klarna-capture.ts
async function captureKlarnaOrder(
  env: Env,
  klarnaOrderId: string,
  captureAmount: number,
  orderLines: KlarnaOrderLine[]
): Promise<string> {
  const credentials = btoa(`${env.KLARNA_USERNAME}:${env.KLARNA_PASSWORD}`);

  const res = await fetch(
    `${env.KLARNA_API_BASE}/ordermanagement/v1/orders/${klarnaOrderId}/captures`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/json',
        'Klarna-Idempotency-Key': `capture-${klarnaOrderId}`,
      },
      body: JSON.stringify({
        captured_amount: captureAmount,
        order_lines: orderLines,
        description: 'Order dispatched',
      }),
    }
  );

  if (!res.ok) throw new Error(`Klarna capture error: ${await res.text()}`);
  // 201 with Location header containing capture ID
  const captureId =
    res.headers.get('Location')?.split('/').pop() ?? 'unknown';
  return captureId;
}

export { captureKlarnaOrder };
```

---

## 5. Handling Klarna Push Notifications (Order Updates)

Klarna calls your `push_url` when the order management state changes (e.g., `CAPTURED`, `CANCELLED`).

```typescript
// src/klarna-push.ts
export async function handleKlarnaPush(
  request: Request,
  env: { DB: D1Database; KLARNA_USERNAME: string; KLARNA_PASSWORD: string; KLARNA_API_BASE: string }
): Promise<Response> {
  const { order_id } = await request.json<{ order_id: string }>();

  // Verify by fetching order from Klarna
  const credentials = btoa(`${env.KLARNA_USERNAME}:${env.KLARNA_PASSWORD}`);
  const res = await fetch(
    `${env.KLARNA_API_BASE}/ordermanagement/v1/orders/${order_id}`,
    { headers: { Authorization: `Basic ${credentials}` } }
  );
  if (!res.ok) return new Response('Not found', { status: 404 });

  const order = await res.json<{ order_id: string; status: string }>();

  await env.DB.prepare(
    `UPDATE klarna_sessions SET status = ?, updated_at = CURRENT_TIMESTAMP
     WHERE klarna_order_id = ?`
  ).bind(order.status, order.order_id).run();

  return new Response(null, { status: 200 });
}
```

---

## Anti-patterns

- **Rendering the Klarna widget from a Worker** — The Klarna JS SDK (`klarna.js`) must load client-side; do not attempt to proxy it through a Worker.
- **Capturing before `fraud_status === 'ACCEPTED'`** — If `fraud_status` is `PENDING`, wait for the push notification before capturing.
- **Omitting `Klarna-Idempotency-Key` on captures** — Duplicate capture calls without the header create double captures billed to the consumer.
- **Hardcoding tax rates** — Different Klarna locales and product categories have different tax obligations; calculate server-side and pass explicit `tax_rate` per line.

## Gotchas

- Klarna `order_amount` must equal the sum of all `order_lines[].total_amount` exactly; any mismatch returns a 400.
- Authorization tokens expire after 60 minutes; if the user abandons checkout, a new session must be created.
- Klarna Playground (`api.playground.klarna.com`) does not trigger real emails; switch to `api.klarna.com` for production.
- `fraud_status: 'REJECTED'` should cancel the order immediately and not retry with the same authorization token.

## Verification

```bash
# Create session
curl -X POST https://your-worker.workers.dev/klarna/session \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-001","currency":"EUR","country":"DE","locale":"de-DE","orderAmount":2999,"orderLines":[]}'

# Simulate push notification
curl -X POST https://your-worker.workers.dev/klarna/push \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"<klarna_order_id>"}'

# Check D1 for session state
wrangler d1 execute <DB> --command "SELECT * FROM klarna_sessions WHERE order_id='ORD-001'"
```

## Related

- `stripe-klarna-bnpl.md`
- `stripe-afterpay-integration.md`
- `payment-method-prioritization-ux.md`
- `psd2-sca-exemption-strategies.md`

## Sources

- https://docs.klarna.com/klarna-payments/
- https://docs.klarna.com/api/payments/
- https://docs.klarna.com/order-management/
- https://developers.cloudflare.com/workers/
