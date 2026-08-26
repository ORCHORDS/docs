# Paddle Subscription Billing with Cloudflare Workers and Webhooks

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project offers optional anonymous identity badges sold as recurring subscriptions. Paddle handles EU
VAT collection and PSD2 compliance automatically, making it attractive over Stripe for European
users. The challenge is wiring Paddle Billing's subscription lifecycle events — `subscription.created`,
`subscription.updated`, `subscription.canceled` — into Workers and D1 without double-granting or
double-revoking badge access during concurrent webhook deliveries.

## Context
Cloudflare Workers receives Paddle webhooks as standard HTTPS POSTs signed with an HMAC-SHA-256
key. Paddle Billing (the current API, replacing Paddle Classic) uses a distinct webhook schema and
verification method. D1 stores subscription state; Workers KV caches active badge entitlements at
the edge to avoid a D1 read on every anonymous post request.

## Section 1 — Paddle Webhook Signature Verification
Paddle signs all Billing webhooks with `H=SHA256`, placing the signature in the
`Paddle-Signature` header. The signing secret is set in the Paddle dashboard under
Notifications → Notification settings.

```typescript
interface Env {
  DB: D1Database;
  BADGE_KV: KVNamespace;
  PADDLE_WEBHOOK_SECRET: string;
}

interface PaddleWebhookEvent<T = Record<string, unknown>> {
  notification_id: string;
  event_id: string;
  event_type: string;
  occurred_at: string; // ISO 8601
  data: T;
}

interface PaddleSubscription {
  id: string;
  customer_id: string;
  status: 'active' | 'canceled' | 'past_due' | 'paused' | 'trialing';
  current_billing_period: {
    starts_at: string;
    ends_at: string;
  } | null;
  items: Array<{ price: { product_id: string } }>;
  custom_data: Record<string, string> | null;
}

async function verifyPaddleSignature(
  body: string,
  header: string,
  secret: string
): Promise<boolean> {
  // header format: ts=<timestamp>;h1=<hex-hmac>
  const parts = Object.fromEntries(
    header.split(';').map(p => p.split('=') as [string, string])
  );
  const ts = parts['ts'];
  const h1 = parts['h1'];
  if (!ts || !h1) return false;

  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const payload = `${ts}:${body}`;
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const computed = Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Reject events older than 5 minutes to prevent replay attacks
  const age = Math.abs(Date.now() / 1000 - parseInt(ts, 10));
  if (age > 300) return false;

  return computed === h1;
}
```

## Section 2 — Subscription State Machine in D1
Model Paddle subscriptions as a state machine in D1. Badge access is derived from `status = 'active'
OR status = 'trialing'`, cached in KV with a TTL aligned to the period end.

```typescript
// migrations/0002_paddle_subscriptions.sql
// CREATE TABLE paddle_subscriptions (
//   subscription_id TEXT PRIMARY KEY,
//   customer_id TEXT NOT NULL,
//   user_id TEXT NOT NULL,           -- from custom_data.user_id set at checkout
//   product_id TEXT NOT NULL,
//   status TEXT NOT NULL,
//   period_start TEXT,
//   period_end TEXT,
//   last_event_id TEXT NOT NULL,
//   last_event_at TEXT NOT NULL,
//   updated_at INTEGER NOT NULL
// );
// CREATE INDEX idx_paddle_subs_user ON paddle_subscriptions(user_id, status);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const header = request.headers.get('Paddle-Signature') ?? '';

    const valid = await verifyPaddleSignature(body, header, env.PADDLE_WEBHOOK_SECRET);
    if (!valid) return new Response('Invalid signature', { status: 400 });

    const event = JSON.parse(body) as PaddleWebhookEvent<PaddleSubscription>;

    // Idempotency: event_id is stable across retries
    const dup = await env.DB
      .prepare('SELECT subscription_id FROM paddle_subscriptions WHERE last_event_id = ?')
      .bind(event.event_id)
      .first();
    if (dup) return new Response('Already processed', { status: 200 });

    const sub = event.data;
    const userId = sub.custom_data?.user_id;
    if (!userId) {
      console.error(`Paddle subscription ${sub.id} missing custom_data.user_id`);
      return new Response('Missing user_id', { status: 422 });
    }

    const productId = sub.items[0]?.price?.product_id ?? 'unknown';

    await env.DB
      .prepare(
        `INSERT INTO paddle_subscriptions
           (subscription_id, customer_id, user_id, product_id, status,
            period_start, period_end, last_event_id, last_event_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(subscription_id) DO UPDATE SET
           status         = excluded.status,
           period_start   = excluded.period_start,
           period_end     = excluded.period_end,
           last_event_id  = excluded.last_event_id,
           last_event_at  = excluded.last_event_at,
           updated_at     = excluded.updated_at`
      )
      .bind(
        sub.id,
        sub.customer_id,
        userId,
        productId,
        sub.status,
        sub.current_billing_period?.starts_at ?? null,
        sub.current_billing_period?.ends_at ?? null,
        event.event_id,
        event.occurred_at,
        Date.now()
      )
      .run();

    await syncBadgeKv(env, userId, sub);

    return new Response('OK', { status: 200 });
  },
};

async function syncBadgeKv(
  env: Env,
  userId: string,
  sub: PaddleSubscription
): Promise<void> {
  const isActive = sub.status === 'active' || sub.status === 'trialing';
  const kvKey = `badge:${userId}`;

  if (isActive && sub.current_billing_period?.ends_at) {
    const expiresAt = new Date(sub.current_billing_period.ends_at);
    const ttlSeconds = Math.max(
      Math.floor((expiresAt.getTime() - Date.now()) / 1000),
      0
    );
    await env.BADGE_KV.put(
      kvKey,
      JSON.stringify({ active: true, subscriptionId: sub.id, productId: sub.items[0]?.price?.product_id }),
      { expirationTtl: ttlSeconds + 86400 } // 1-day grace for late renewals
    );
  } else {
    await env.BADGE_KV.delete(kvKey);
  }
}
```

## Section 3 — Past-Due Grace Period and Cancellation
`subscription.past_due` should not immediately revoke badge access — Paddle retries payment up to
the dunning schedule configured in the dashboard. Only `subscription.canceled` triggers hard revocation.

```typescript
type PaddleSubscriptionStatus =
  | 'subscription.created'
  | 'subscription.updated'
  | 'subscription.canceled'
  | 'subscription.paused'
  | 'subscription.resumed'
  | 'subscription.past_due';

async function handleSubscriptionEvent(
  env: Env,
  event: PaddleWebhookEvent<PaddleSubscription>
): Promise<void> {
  const sub = event.data;
  const userId = sub.custom_data?.user_id;
  if (!userId) return;

  switch (event.event_type as PaddleSubscriptionStatus) {
    case 'subscription.created':
    case 'subscription.updated':
    case 'subscription.resumed':
      // Handled by upsert + KV sync above
      break;

    case 'subscription.past_due':
      // Keep badge active during dunning; update status only
      await env.DB
        .prepare(
          `UPDATE paddle_subscriptions SET status = 'past_due', last_event_id = ?,
           last_event_at = ?, updated_at = ?
           WHERE subscription_id = ?`
        )
        .bind(event.event_id, event.occurred_at, Date.now(), sub.id)
        .run();
      // Do NOT delete KV — badge persists through dunning
      break;

    case 'subscription.paused':
      await env.DB
        .prepare(
          `UPDATE paddle_subscriptions SET status = 'paused', last_event_id = ?,
           last_event_at = ?, updated_at = ?
           WHERE subscription_id = ?`
        )
        .bind(event.event_id, event.occurred_at, Date.now(), sub.id)
        .run();
      await env.BADGE_KV.delete(`badge:${userId}`);
      break;

    case 'subscription.canceled':
      await env.DB
        .prepare(
          `UPDATE paddle_subscriptions SET status = 'canceled', last_event_id = ?,
           last_event_at = ?, updated_at = ?
           WHERE subscription_id = ?`
        )
        .bind(event.event_id, event.occurred_at, Date.now(), sub.id)
        .run();
      await env.BADGE_KV.delete(`badge:${userId}`);
      break;
  }
}
```

## Section 4 — Monitoring Subscription Health
Expose D1 aggregate queries via a scheduled Worker to detect churned badges and past-due spikes.

```typescript
export async function monitorPaddleSubscriptions(env: Env): Promise<void> {
  const [active, pastDue, canceled] = await Promise.all([
    env.DB
      .prepare(`SELECT COUNT(*) AS count FROM paddle_subscriptions WHERE status = 'active'`)
      .first<{ count: number }>(),
    env.DB
      .prepare(`SELECT COUNT(*) AS count FROM paddle_subscriptions WHERE status = 'past_due'`)
      .first<{ count: number }>(),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM paddle_subscriptions
         WHERE status = 'canceled' AND updated_at > ?`
      )
      .bind(Date.now() - 86_400_000)
      .first<{ count: number }>(),
  ]);

  console.log(JSON.stringify({
    level: 'info',
    service: 'paddle-subscriptions',
    active: active?.count ?? 0,
    past_due: pastDue?.count ?? 0,
    canceled_24h: canceled?.count ?? 0,
    ts: new Date().toISOString(),
  }));

  if ((pastDue?.count ?? 0) > 10) {
    console.error(JSON.stringify({
      level: 'error',
      service: 'paddle-subscriptions',
      alert: 'high past_due count',
      count: pastDue?.count,
    }));
  }
}
```

## Anti-patterns
- Using Paddle Classic webhook schema for Paddle Billing events — the two APIs differ significantly
- Revoking badge access immediately on `subscription.past_due` — Paddle retries before canceling
- Storing `custom_data` only client-side at checkout — always pass `custom_data.user_id` in the server-side subscription creation call
- Relying on `notification_id` for idempotency — use `event_id`, which is stable across retry deliveries
- Skipping the timestamp check in signature verification — opens replay attack surface

## Gotchas
- Paddle Billing webhook signatures use `ts=<ts>;h1=<hex>` format, not the `t=<ts>,v1=<hex>` format Stripe uses
- The `custom_data` field on a subscription is set at subscription creation and does not update automatically if the price changes
- KV `expirationTtl` must be at least 60 seconds — add grace days, not just the exact period end
- Paddle's dunning duration is configurable per product; hardcoding a revocation window will conflict with dashboard settings

## Verification
1. Use Paddle's test environment and webhook simulator to deliver each event type in sequence
2. Confirm `paddle_subscriptions.status` transitions match the event sequence in D1
3. Assert `BADGE_KV.get('badge:<userId>')` returns a value during `active` and `trialing`, and null after `canceled`
4. Simulate a `past_due` event and confirm the badge KV key is NOT deleted

## Related
- /documentation/categories/payments/paddle-integration.md
- /documentation/categories/payments/payment-dunning-management-cloudflare-queues.md
- /documentation/categories/payments/subscription-billing-lifecycle.md
- /documentation/categories/payments/idempotency-keys-payment-apis.md

## Sources
- https://developer.paddle.com/webhooks/overview
- https://developer.paddle.com/api-reference/subscriptions/overview
- https://developer.paddle.com/webhooks/signature-verification
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
