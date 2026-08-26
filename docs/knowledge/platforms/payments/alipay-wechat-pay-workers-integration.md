# Alipay and WeChat Pay via Aggregators on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want to accept Alipay and WeChat Pay from Chinese shoppers on your international platform.
Direct integration with Alipay Global and WeChat Pay Global requires a Chinese business entity;
international merchants go through aggregators (Stripe, Adyen, Airwallex, 2C2P, PingPong).
Workers manage QR-code polling, redirect flows, and webhook state transitions in D1.

## Context

Alipay Global and WeChat Pay export two checkout patterns: (a) **redirect / hosted** — user is
sent to a payment page, returns via redirect; (b) **QR code** — a `code_url` is rendered as a QR
on desktop; mobile users scan with their app and pay. Both flows are asynchronous: a webhook
confirms payment. This article covers Stripe (Alipay + WeChat Pay objects) and Airwallex as
examples; the polling/webhook pattern applies equally to Adyen, 2C2P, and PingPong.

## Stripe: Create an Alipay Payment Intent

```typescript
// src/handlers/stripe-alipay.ts
interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
}

async function createAlipayPaymentIntent(
  env: Env,
  orderId: string,
  amountCNY: number   // smallest unit (fen); 100 fen = 1 CNY
): Promise<{ clientSecret: string; paymentIntentId: string }> {
  const params = new URLSearchParams({
    amount: String(amountCNY),
    currency: 'cny',
    'payment_method_types[]': 'alipay',
    'metadata[order_id]': orderId,
    'return_url': `https://yourdomain.com/checkout/return?order=${orderId}`,
  });

  const res = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });

  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(`Stripe Alipay error: ${err.error.message}`);
  }

  const pi = await res.json<{ id: string; client_secret: string }>();

  await env.DB.prepare(
    `INSERT INTO chinese_wallet_payments (order_id, provider_id, method, status, created_at)
     VALUES (?, ?, 'alipay', 'pending', ?)`
  ).bind(orderId, pi.id, Date.now()).run();

  return { clientSecret: <redacted-secret> paymentIntentId: pi.id };
}
```

## Stripe: WeChat Pay with QR Code Polling

```typescript
// WeChat Pay on desktop: render QR from code_url; poll for completion
async function createWeChatPayQR(
  env: Env,
  orderId: string,
  amountCNY: number
): Promise<{ qrCodeUrl: string; paymentIntentId: string }> {
  const params = new URLSearchParams({
    amount: String(amountCNY),
    currency: 'cny',
    'payment_method_types[]': 'wechat_pay',
    'payment_method_options[wechat_pay][client]': 'web',
    'metadata[order_id]': orderId,
    confirm: 'true',
    'payment_method_data[type]': 'wechat_pay',
  });

  const res = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });

  if (!res.ok) throw new Error(`WeChat Pay creation failed: ${await res.text()}`);

  const pi = await res.json<{
    id: string;
    next_action?: { wechat_pay_display_qr_code?: { data: string } };
  }>();

  const qrCodeUrl = pi.next_action?.wechat_pay_display_qr_code?.data ?? '';

  await env.DB.prepare(
    `INSERT INTO chinese_wallet_payments (order_id, provider_id, method, status, qr_code_url, created_at)
     VALUES (?, ?, 'wechat_pay', 'pending', ?, ?)`
  ).bind(orderId, pi.id, qrCodeUrl, Date.now()).run();

  return { qrCodeUrl, paymentIntentId: pi.id };
}

// Client-side polling endpoint — called every 3s until status changes
export async function pollPaymentStatus(
  request: Request,
  env: Env
): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const piId = searchParams.get('pi_id');
  if (!piId) return Response.json({ error: 'Missing pi_id' }, { status: 400 });

  const res = await fetch(`https://api.stripe.com/v1/payment_intents/${piId}`, {
    headers: { 'Authorization': `Bearer ${env.STRIPE_SECRET_KEY}` },
  });
  const pi = await res.json<{ status: string; id: string }>();

  if (pi.status === 'succeeded') {
    await env.DB.prepare(
      `UPDATE chinese_wallet_payments SET status = 'succeeded' WHERE provider_id = ?`
    ).bind(pi.id).run();
  }

  return Response.json({ status: pi.status });
}
```

## Airwallex: Alipay + WeChat Pay (International Merchants)

```typescript
// Airwallex is the preferred aggregator for non-China merchants
interface AirwallexEnv {
  AIRWALLEX_CLIENT_ID: string;
  AIRWALLEX_API_KEY: string;
  AIRWALLEX_BASE_URL: string; // https://api.airwallex.com
}

async function getAirwallexToken(env: AirwallexEnv): Promise<string> {
  const res = await fetch(`${env.AIRWALLEX_BASE_URL}/api/v1/authentication/login`, {
    method: 'POST',
    headers: {
      'x-client-id': env.AIRWALLEX_CLIENT_ID,
      'x-api-key': env.AIRWALLEX_API_KEY,
    },
  });
  const data = await res.json<{ token: string }>();
  return data.token;
}

async function createAirwallexPaymentIntent(
  env: AirwallexEnv & { DB: D1Database },
  orderId: string,
  amountUSD: number, // Airwallex international Alipay settles in USD/EUR/etc.
  currency: string,
  returnUrl: string
): Promise<{ id: string; client_secret: string }> {
  const token = await getAirwallexToken(env);

  const res = await fetch(`${env.AIRWALLEX_BASE_URL}/api/v1/pa/payment_intents/create`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      request_id: orderId,           // idempotency key
      amount: amountUSD,
      currency,
      merchant_order_id: orderId,
      return_url: returnUrl,
      payment_method_options: {
        type: 'alipaycn',            // 'alipaycn' (mainland) or 'alipayhk' (HK)
        alipaycn: { flow: 'webqr' }, // 'webqr' | 'mweb' | 'app' | 'jsapi'
      },
    }),
  });

  if (!res.ok) throw new Error(`Airwallex PI failed: ${await res.text()}`);
  return res.json();
}
```

## Webhook Handler (Stripe — Alipay / WeChat Pay events)

```typescript
import { verifyStripeWebhook } from './stripe-webhook-util'; // HMAC-SHA256

export async function handleChineseWalletWebhook(
  request: Request,
  env: Env & { STRIPE_WEBHOOK_SECRET: string }
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';

  const event = await verifyStripeWebhook(body, sig, env.STRIPE_WEBHOOK_SECRET);

  if (event.type === 'payment_intent.succeeded') {
    const pi = event.data.object as { id: string; metadata: { order_id: string } };
    await env.DB.prepare(
      `UPDATE chinese_wallet_payments SET status = 'succeeded' WHERE provider_id = ?`
    ).bind(pi.id).run();
    await fulfillOrder(env, pi.metadata.order_id);
  }

  if (event.type === 'payment_intent.payment_failed') {
    const pi = event.data.object as { id: string };
    await env.DB.prepare(
      `UPDATE chinese_wallet_payments SET status = 'failed' WHERE provider_id = ?`
    ).bind(pi.id).run();
  }

  return new Response('OK');
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS chinese_wallet_payments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id     TEXT NOT NULL UNIQUE,
  provider_id  TEXT NOT NULL,
  method       TEXT NOT NULL,      -- 'alipay' | 'wechat_pay'
  status       TEXT NOT NULL DEFAULT 'pending',
  qr_code_url  TEXT,
  created_at   INTEGER NOT NULL,
  settled_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cwp_provider ON chinese_wallet_payments(provider_id);
```

## Anti-patterns

- **Attempting direct Alipay/WeChat Pay integration without a Chinese business license** — direct
  merchant accounts require registration with AMPE/Tenpay; international merchants must use an
  approved aggregator.
- **Rendering the WeChat Pay QR on mobile** — mobile browsers cannot scan a QR with the same
  device. Detect `User-Agent` and use the `mweb` flow (redirect) on mobile, `webqr` on desktop.
- **Polling payment status from the Worker on every request** — poll from the client-side browser
  every 3–5 s and confirm server-side on success callback, keeping Worker calls minimal.
- **Assuming CNY is the only settlement currency** — Alipay Global/WeChat Pay Global can settle
  in USD, EUR, GBP, HKD. Match the currency to the aggregator's settlement agreement.

## Gotchas

- Alipay CNY (`alipaycn`) QR codes expire after 2 minutes. Provide a "refresh QR" button.
- WeChat Pay requires the merchant's `appid` to be whitelisted for JSAPI payments; web QR
  (`native`) flow does not require this and is simpler for non-mini-program merchants.
- Stripe only supports WeChat Pay and Alipay for CNY; cross-currency presentment requires Adyen
  or Airwallex.
- Airwallex `alipayhk` (Hong Kong Alipay) and `alipaycn` are distinct payment methods with
  separate flow configurations and settlement timelines.

## Verification

```bash
# Stripe: list Alipay payment methods on a test PaymentIntent
curl -s https://api.stripe.com/v1/payment_intents \
  -H "Authorization: Bearer sk_test_..." \
  -d "amount=1000" -d "currency=cny" -d "payment_method_types[]=alipay" | jq '.id,.status'

# Poll status via Worker
curl -s "https://your-worker.workers.dev/api/poll?pi_id=pi_xxx" | jq '.status'
```

## Related

- `apple-pay-google-pay-workers-merchant-validation.md`
- `multi-currency-handling.md`
- `payment-state-machine-design.md`
- `payment-error-handling.md`
- `cross-border-payment-routing.md`

## Sources

- https://stripe.com/docs/payments/alipay
- https://stripe.com/docs/payments/wechat-pay
- https://www.airwallex.com/docs/payments__alipay-cn
- https://www.airwallex.com/docs/payments__wechat-pay
- https://global.alipay.com/docs/ac/globalwalletreference/overview
