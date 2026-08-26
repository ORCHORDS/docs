# Stripe Checkout Session Creation from Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Creating Hosted Checkout Sessions from an Edge Worker

Stripe Checkout is the fastest path to a conversion-ready payment page, but
orchestrating it from a Cloudflare Worker requires careful ordering: the D1
order record must exist before the redirect so that the success webhook has
something to fulfil, and every session creation call must carry an idempotency
key so that network retries never double-charge the customer.

## Context

Workers run at the edge with no persistent memory between requests. A Checkout
Session is a Stripe-hosted page, so the Worker's job is to (1) pre-create an
order row in D1, (2) mint a session on Stripe, (3) redirect the browser. Post-
checkout fulfilment is decoupled: the `checkout.session.completed` webhook
enqueues a Queues message that a consumer Worker processes asynchronously.

## D1 Order Pre-Creation

Write the order before touching Stripe so the row is always the source of
truth regardless of whether the redirect succeeds.

```typescript
// src/lib/orders.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Order {
  id: string;
  userId: string;
  amountCents: number;
  currency: string;
  status: 'pending' | 'paid' | 'failed' | 'refunded';
  stripeSessionId: string | null;
  createdAt: number;
}

export async function createPendingOrder(
  db: D1Database,
  userId: string,
  amountCents: number,
  currency: string,
): Promise<Order> {
  const id = crypto.randomUUID();
  const now = Date.now();
  await db
    .prepare(
      `INSERT INTO orders (id, user_id, amount_cents, currency, status, stripe_session_id, created_at)
       VALUES (?, ?, ?, ?, 'pending', NULL, ?)`,
    )
    .bind(id, userId, amountCents, currency, now)
    .run();
  return { id, userId, amountCents, currency, status: 'pending', stripeSessionId: null, createdAt: now };
}

export async function attachSessionId(
  db: D1Database,
  orderId: string,
  sessionId: string,
): Promise<void> {
  await db
    .prepare(`UPDATE orders SET stripe_session_id = ? WHERE id = ?`)
    .bind(sessionId, orderId)
    .run();
}
```

## Checkout Session Creation with Idempotency

```typescript
// src/handlers/checkout.ts
import Stripe from 'stripe';
import { createPendingOrder, attachSessionId } from '../lib/orders';

interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
  SITE_ORIGIN: string;
}

export async function handleCheckout(request: Request, env: Env): Promise<Response> {
  const { userId, items } = await request.json<{ userId: string; items: Array<{ priceId: string; qty: number }> }>();

  const amountCents = items.reduce((sum, i) => sum + i.qty * 100, 0); // simplified
  const order = await createPendingOrder(env.DB, userId, amountCents, 'usd');

  // Idempotency key ties the Stripe call to the D1 order so retries are safe.
  const idempotencyKey = `checkout-${order.id}`;

  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  const session = await stripe.checkout.sessions.create(
    {
      mode: 'payment',
      line_items: items.map((i) => ({ price: i.priceId, quantity: i.qty })),
      success_url: `${env.SITE_ORIGIN}/order/${order.id}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${env.SITE_ORIGIN}/order/${order.id}/cancel`,
      metadata: { orderId: order.id, userId },
      payment_intent_data: { metadata: { orderId: order.id } },
      expires_at: Math.floor(Date.now() / 1000) + 1800, // 30 min
    },
    { idempotencyKey },
  );

  await attachSessionId(env.DB, order.id, session.id);

  return Response.redirect(session.url!, 303);
}
```

## Post-Checkout Fulfilment via Queues

```typescript
// src/handlers/webhook.ts  — receives checkout.session.completed
import Stripe from 'stripe';

interface Env {
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
  FULFILMENT_QUEUE: Queue;
}

export async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(body, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;
    const orderId = session.metadata?.orderId;
    if (!orderId) return new Response('Missing orderId', { status: 400 });

    // Idempotent status update — D1 write before queue enqueue
    await env.DB.prepare(`UPDATE orders SET status = 'paid' WHERE id = ? AND status = 'pending'`)
      .bind(orderId)
      .run();

    await env.FULFILMENT_QUEUE.send({ orderId, sessionId: session.id });
  }

  return new Response('ok');
}
```

```typescript
// src/consumers/fulfilment.ts
export default {
  async queue(batch: MessageBatch<{ orderId: string; sessionId: string }>, env: Env) {
    for (const msg of batch.messages) {
      const { orderId } = msg.body;
      // provision licence / send email / call downstream APIs
      await provisionLicence(orderId, env);
      msg.ack();
    }
  },
};
```

## Anti-patterns

- Do NOT redirect directly to Stripe without pre-creating the D1 order. If the
  Worker crashes after the Stripe call, you have a session with no local record.
- Do NOT use `Date.now()` as an idempotency key. It changes on retries.
- Do NOT fulfil inside the webhook handler synchronously; it will time out on
  large orders. Always enqueue to Queues.
- Do NOT skip `expires_at`; abandoned sessions held open indefinitely skew
  analytics and occupancy quotas.

## Gotchas

- `stripe.webhooks.constructEventAsync` is required in Workers (no sync crypto).
- `success_url` must include `{CHECKOUT_SESSION_ID}` as a literal placeholder;
  Stripe replaces it server-side before redirect.
- The idempotency key scope is per Stripe API key — the same key reused on a
  different endpoint will return an error, not the original response.
- D1 `run()` does not throw on UPDATE that matches zero rows; check
  `meta.changes` if you need to detect a race.

## Verification

```bash
# Create a checkout session via curl against the Worker dev server
curl -X POST http://localhost:8787/checkout \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_test","items":[{"priceId":"price_xxx","qty":1}]}'

# Trigger the webhook locally with Stripe CLI
stripe listen --forward-to http://localhost:8787/webhook
stripe trigger checkout.session.completed
```

## Related

- `stripe-webhook-idempotency-d1-event-log.md`
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `stripe-payment-element-cloudflare-pages-csp.md`
- `stripe-checkout-session.md`

## Sources

- https://stripe.com/docs/api/checkout/sessions/create
- https://stripe.com/docs/checkout/fulfillment
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
