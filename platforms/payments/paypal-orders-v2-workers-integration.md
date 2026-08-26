# PayPal Orders v2 API Integration with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project needs a one-time payment path for users purchasing anonymous posting packs without a PayPal
subscription. The PayPal Orders v2 API (create → capture) is the correct primitive, but the client
credential token exchange, order creation, and capture must all happen server-side in a Cloudflare
Worker to avoid exposing secret keys or allowing client-side price manipulation.

## Context
Cloudflare Workers run at the edge with no persistent process state. PayPal's OAuth 2.0 client
credential token has a 32 400-second TTL and is safe to cache in Workers KV, eliminating the token
round-trip on every payment request. D1 stores order state so the capture endpoint can enforce
idempotency and reconcile fulfilled orders even when PayPal's webhook delivery is delayed.

## Section 1 — Token Caching and Order Creation
Cache the access token in KV and create a PayPal order with a server-authoritative price to prevent
client-side tampering.

```typescript
interface Env {
  PAYPAL_CLIENT_ID: string;
  PAYPAL_CLIENT_SECRET: string;
  PAYPAL_BASE_URL: string;        // https://api-m.paypal.com or sandbox equivalent
  TOKEN_KV: KVNamespace;
  DB: D1Database;
}

async function getPayPalToken(env: Env): Promise<string> {
  const cached = await env.TOKEN_KV.get('paypal_access_token');
  if (cached) return cached;

  const creds = btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_CLIENT_SECRET}`);
  const res = await fetch(`${env.PAYPAL_BASE_URL}/v1/oauth2/token`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${creds}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: 'grant_type=client_credentials',
  });

  if (!res.ok) throw new Error(`PayPal token error: ${res.status}`);
  const data = await res.json<{ access_token: string; expires_in: number }>();

  // Cache with a 60-second safety buffer before expiry
  await env.TOKEN_KV.put('paypal_access_token', data.access_token, {
    expirationTtl: data.expires_in - 60,
  });
  return data.access_token;
}

interface OrderRequest {
  packId: string;
  userId: string;
}

const PACK_PRICES: Record<string, { amount: string; currency: string; description: string }> = {
  pack_10: { amount: '4.99', currency: 'USD', description: '10 Anonymous Posts' },
  pack_50: { amount: '19.99', currency: 'USD', description: '50 Anonymous Posts' },
  pack_100: { amount: '34.99', currency: 'USD', description: '100 Anonymous Posts' },
};

async function createOrder(env: Env, req: OrderRequest): Promise<Response> {
  const pack = PACK_PRICES[req.packId];
  if (!pack) return new Response('Invalid pack', { status: 400 });

  const token = await getPayPalToken(env);
  const idempotencyKey = crypto.randomUUID();

  const res = await fetch(`${env.PAYPAL_BASE_URL}/v2/checkout/orders`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'PayPal-Request-Id': idempotencyKey,
    },
    body: JSON.stringify({
      intent: 'CAPTURE',
      purchase_units: [
        {
          reference_id: `${req.userId}:${req.packId}:${idempotencyKey}`,
          description: pack.description,
          amount: {
            currency_code: pack.currency,
            value: pack.amount,
          },
          custom_id: req.userId,
        },
      ],
      payment_source: {
        paypal: {
          experience_context: {
            payment_method_preference: 'IMMEDIATE_PAYMENT_REQUIRED',
            user_action: 'PAY_NOW',
            return_url: 'https://example.com/payment/success',
            cancel_url: 'https://example.com/payment/cancel',
          },
        },
      },
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error(`PayPal create order failed: ${err}`);
    return new Response('Order creation failed', { status: 502 });
  }

  const order = await res.json<{ id: string; status: string; links: Array<{ rel: string; href: string }> }>();

  // Persist pending order so capture can verify userId / amount server-side
  await env.DB
    .prepare(
      `INSERT INTO paypal_orders (order_id, user_id, pack_id, amount, currency, status, created_at)
       VALUES (?, ?, ?, ?, ?, 'CREATED', ?)`
    )
    .bind(order.id, req.userId, req.packId, pack.amount, pack.currency, Date.now())
    .run();

  const approveLink = order.links.find(l => l.rel === 'payer-action')?.href;
  return Response.json({ orderId: order.id, approveUrl: approveLink });
}
```

## Section 2 — Order Capture on Return
After the buyer approves on PayPal, capture the order using the ID returned to the `return_url`.
Verify the order belongs to the current session user before capturing.

```typescript
async function captureOrder(
  env: Env,
  orderId: string,
  userId: string
): Promise<Response> {
  // Verify order belongs to this user and is in a capturable state
  const row = await env.DB
    .prepare(
      `SELECT user_id, pack_id, status FROM paypal_orders WHERE order_id = ?`
    )
    .bind(orderId)
    .first<{ user_id: string; pack_id: string; status: string }>();

  if (!row) return new Response('Order not found', { status: 404 });
  if (row.user_id !== userId) return new Response('Forbidden', { status: 403 });
  if (row.status === 'COMPLETED') {
    return Response.json({ already: true, packId: row.pack_id });
  }
  if (row.status !== 'CREATED') {
    return new Response(`Order in unexpected state: ${row.status}`, { status: 409 });
  }

  const token = await getPayPalToken(env);
  const res = await fetch(
    `${env.PAYPAL_BASE_URL}/v2/checkout/orders/${orderId}/capture`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'PayPal-Request-Id': `capture-${orderId}`, // idempotent retry key
      },
      body: '{}',
    }
  );

  if (!res.ok) {
    const body = await res.text();
    // ORDER_ALREADY_CAPTURED is safe to treat as success
    if (body.includes('ORDER_ALREADY_CAPTURED')) {
      await markOrderComplete(env, orderId, row.pack_id, userId);
      return Response.json({ success: true, packId: row.pack_id });
    }
    console.error(`PayPal capture failed: ${res.status} ${body}`);
    return new Response('Capture failed', { status: 502 });
  }

  const capture = await res.json<{ status: string }>();
  if (capture.status !== 'COMPLETED') {
    return new Response(`Unexpected capture status: ${capture.status}`, { status: 502 });
  }

  await markOrderComplete(env, orderId, row.pack_id, userId);
  return Response.json({ success: true, packId: row.pack_id });
}

async function markOrderComplete(
  env: Env,
  orderId: string,
  packId: string,
  userId: string
): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE paypal_orders SET status = 'COMPLETED', completed_at = ? WHERE order_id = ?`
    ).bind(Date.now(), orderId),
    env.DB.prepare(
      `INSERT INTO user_post_credits (user_id, pack_id, order_id, granted_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT DO NOTHING`
    ).bind(userId, packId, orderId, Date.now()),
  ]);
}
```

## Section 3 — Webhook Verification and Reconciliation
PayPal sends `PAYMENT.CAPTURE.COMPLETED` webhooks as a backstop when the client never returns to
`return_url`. Verify the signature using PayPal's cert-based verification API.

```typescript
interface PayPalWebhookHeaders {
  'paypal-transmission-id': string;
  'paypal-transmission-time': string;
  'paypal-cert-url': string;
  'paypal-auth-algo': string;
  'paypal-transmission-sig': string;
}

async function handlePayPalWebhook(request: Request, env: Env): Promise<Response> {
  const body = await request.text();
  const headers: PayPalWebhookHeaders = {
    'paypal-transmission-id': request.headers.get('paypal-transmission-id') ?? '',
    'paypal-transmission-time': request.headers.get('paypal-transmission-time') ?? '',
    'paypal-cert-url': request.headers.get('paypal-cert-url') ?? '',
    'paypal-auth-algo': request.headers.get('paypal-auth-algo') ?? '',
    'paypal-transmission-sig': request.headers.get('paypal-transmission-sig') ?? '',
  };

  // Delegate signature verification to PayPal's verify endpoint
  const token = await getPayPalToken(env);
  const verifyRes = await fetch(
    `${env.PAYPAL_BASE_URL}/v1/notifications/verify-webhook-signature`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        auth_algo: headers['paypal-auth-algo'],
        cert_url: headers['paypal-cert-url'],
        transmission_id: headers['paypal-transmission-id'],
        transmission_sig: headers['paypal-transmission-sig'],
        transmission_time: headers['paypal-transmission-time'],
        webhook_id: env.PAYPAL_WEBHOOK_ID,
        webhook_event: JSON.parse(body),
      }),
    }
  );

  const { verification_status } = await verifyRes.json<{ verification_status: string }>();
  if (verification_status !== 'SUCCESS') {
    return new Response('Signature verification failed', { status: 400 });
  }

  const event = JSON.parse(body) as {
    event_type: string;
    resource: { id: string; custom_id: string; status: string };
  };

  if (event.event_type === 'PAYMENT.CAPTURE.COMPLETED') {
    const captureId = event.resource.id;
    const userId = event.resource.custom_id;

    // Look up the order by capture ID if possible, or re-read via API
    const order = await env.DB
      .prepare(`SELECT order_id, pack_id FROM paypal_orders WHERE order_id = ?`)
      .bind(captureId)
      .first<{ order_id: string; pack_id: string }>();

    if (order && order.pack_id) {
      await markOrderComplete(env, order.order_id, order.pack_id, userId);
    }
  }

  return new Response('OK', { status: 200 });
}
```

## Section 4 — Monitoring Dangling Orders
Scheduled Worker that identifies orders stuck in `CREATED` state beyond the PayPal order TTL
(~3 hours), alerting before credits are incorrectly assumed uncaptured.

```typescript
export async function auditDanglingOrders(env: Env): Promise<void> {
  const THREE_HOURS_AGO = Date.now() - 3 * 60 * 60 * 1000;

  const dangling = await env.DB
    .prepare(
      `SELECT order_id, user_id, pack_id, created_at
       FROM paypal_orders
       WHERE status = 'CREATED' AND created_at < ?
       ORDER BY created_at ASC LIMIT 50`
    )
    .bind(THREE_HOURS_AGO)
    .all<{ order_id: string; user_id: string; pack_id: string; created_at: number }>();

  if (dangling.results.length > 0) {
    console.warn(JSON.stringify({
      level: 'warn',
      service: 'paypal-orders-v2',
      dangling_orders: dangling.results.length,
      sample: dangling.results.slice(0, 5),
      ts: new Date().toISOString(),
    }));
  }
}
```

## Anti-patterns
- Fetching a fresh OAuth token on every request — the 32 400 s TTL means dozens of wasted token calls per minute
- Trusting the amount or currency returned from the client — always read price from a server-side lookup table
- Skipping the D1 ownership check before capture — any user who guesses an `orderId` could capture another user's order
- Using `AUTHORIZE` intent without a later capture step for simple one-time payments
- Ignoring `ORDER_ALREADY_CAPTURED` errors — they indicate a successful retry, not a failure

## Gotchas
- PayPal's `PayPal-Request-Id` header provides idempotency only within the same 72-hour window; it is not a permanent dedup key
- The `payer-action` link (not `approve`) is the correct redirect link in Orders v2
- PayPal's verify-webhook-signature API itself makes an outbound HTTP call — add a 5 s timeout
- Sandbox `paypal-cert-url` values are from `*.sandbox.paypal.com`; they will fail in production

## Verification
1. Use PayPal sandbox credentials to create and capture a test order end-to-end
2. Verify `paypal_orders.status` transitions from `CREATED` to `COMPLETED` in D1
3. Confirm `user_post_credits` row is inserted exactly once even on duplicate capture calls
4. Trigger `PAYMENT.CAPTURE.COMPLETED` webhook from PayPal sandbox simulator and trace the reconciliation path

## Related
- /documentation/categories/payments/paypal-webhooks.md
- /documentation/categories/payments/paypal-webhook-certificate-verification.md
- /documentation/categories/payments/paypal-subscriptions.md
- /documentation/categories/payments/idempotency-keys-payment-apis.md

## Sources
- https://developer.paypal.com/docs/api/orders/v2/
- https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature_post
- https://developer.paypal.com/docs/checkout/standard/integrate/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
