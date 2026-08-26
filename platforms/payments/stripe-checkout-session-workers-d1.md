# Stripe Checkout Session Creation with D1 Order Pre-creation in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your storefront needs a reliable order record that exists before the user reaches Stripe's hosted checkout page. If Stripe's session creation fails or the user closes the tab before payment, you still need a traceable order row for support and analytics. A Cloudflare Worker handles `POST /checkout`, writes a `pending` order to D1, then creates the Stripe session with the order ID in metadata so the webhook can reconcile.

---

## Context

The pattern is write-then-redirect: create the D1 order row first (with `status: pending`), pass `orderId` as Stripe session metadata, and rely on the `checkout.session.completed` webhook to flip the status to `paid`. A Cron Trigger runs hourly to tombstone orders stuck in `pending` for over an hour—these represent abandoned sessions that Stripe expired. The Stripe client library is imported via npm and bundled by Wrangler; the `stripe` package works in Workers as long as `httpClient` is set to a fetch-compatible adapter. All Stripe API calls use `fetch` under the hood via `Stripe.createFetchHttpClient()`.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS orders (
  id              TEXT PRIMARY KEY,          -- UUID v4
  stripe_session_id TEXT,                    -- filled after Stripe call
  customer_email  TEXT,
  amount_cents    INTEGER NOT NULL,
  currency        TEXT    NOT NULL DEFAULT 'usd',
  status          TEXT    NOT NULL DEFAULT 'pending',
  created_at      TEXT    NOT NULL,
  completed_at    TEXT,
  abandoned_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_stripe_session
  ON orders(stripe_session_id);

CREATE INDEX IF NOT EXISTS idx_orders_status_created
  ON orders(status, created_at);
```

```bash
wrangler d1 create orders-db
wrangler d1 execute orders-db --file schema.sql
```

---

## Section 2 — Worker Implementation

```typescript
import Stripe from "stripe";

export interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  STORE_DOMAIN: string;
}

function makeStripe(env: Env): Stripe {
  return new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-06-20",
    httpClient: Stripe.createFetchHttpClient(),
  });
}

function generateOrderId(): string {
  // crypto.randomUUID() is available in Workers
  return crypto.randomUUID();
}

// ----- POST /checkout -----

async function handleCheckout(request: Request, env: Env): Promise<Response> {
  const { lineItems, customerEmail } = await request.json<{
    lineItems: Array<{ priceId: string; quantity: number }>;
    customerEmail?: string;
  }>();

  if (!lineItems?.length) {
    return new Response(JSON.stringify({ error: "lineItems required" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const orderId = generateOrderId();
  const now = new Date().toISOString();

  // 1. Pre-create order in D1
  await env.DB.prepare(
    `INSERT INTO orders (id, customer_email, amount_cents, currency, status, created_at)
     VALUES (?, ?, 0, 'usd', 'pending', ?)`
  )
    .bind(orderId, customerEmail ?? null, now)
    .run();

  // 2. Create Stripe Checkout session
  const stripe = makeStripe(env);
  let session: Stripe.Checkout.Session;
  try {
    session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: lineItems.map((li) => ({
        price: li.priceId,
        quantity: li.quantity,
      })),
      customer_email: customerEmail,
      metadata: { orderId },
      success_url: `https://${env.STORE_DOMAIN}/order/success?orderId=${orderId}`,
      cancel_url: `https://${env.STORE_DOMAIN}/cart`,
      expires_at: Math.floor(Date.now() / 1000) + 3600, // 1 hour
    });
  } catch (err) {
    // Roll back D1 row if Stripe call fails
    await env.DB.prepare("DELETE FROM orders WHERE id = ?").bind(orderId).run();
    const msg = err instanceof Error ? err.message : "Stripe error";
    return new Response(JSON.stringify({ error: msg }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  // 3. Update order with Stripe session ID and computed amount
  await env.DB.prepare(
    `UPDATE orders SET stripe_session_id = ?, amount_cents = ? WHERE id = ?`
  )
    .bind(session.id, session.amount_total ?? 0, orderId)
    .run();

  return new Response(
    JSON.stringify({ checkoutUrl: session.url, orderId }),
    { headers: { "Content-Type": "application/json" } }
  );
}

// ----- POST /stripe/webhook -----

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get("stripe-signature") ?? "";
  const stripe = makeStripe(env);

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      body,
      sig,
      env.STRIPE_WEBHOOK_SECRET
    );
  } catch {
    return new Response("Webhook signature invalid", { status: 400 });
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;
    const orderId = session.metadata?.orderId;
    if (orderId) {
      await env.DB.prepare(
        `UPDATE orders
         SET status = 'paid', completed_at = ?, stripe_session_id = ?
         WHERE id = ? AND status = 'pending'`
      )
        .bind(new Date().toISOString(), session.id, orderId)
        .run();
    }
  }

  return new Response("ok");
}

// ----- Cron: orphan cleanup -----

async function handleScheduled(env: Env): Promise<void> {
  const cutoff = new Date(Date.now() - 60 * 60 * 1000).toISOString(); // 1 hour ago
  await env.DB.prepare(
    `UPDATE orders
     SET status = 'abandoned', abandoned_at = ?
     WHERE status = 'pending' AND created_at < ?`
  )
    .bind(new Date().toISOString(), cutoff)
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/checkout") {
      return handleCheckout(request, env);
    }
    if (request.method === "POST" && url.pathname === "/stripe/webhook") {
      return handleWebhook(request, env);
    }
    return new Response("Not Found", { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await handleScheduled(env);
  },
};
```

---

## Section 3 — wrangler.toml Cron & Bindings

```toml
name = "stripe-checkout"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "orders-db"
database_id = "<your-d1-database-id>"

[triggers]
crons = ["0 * * * *"]  # Every hour
```

```bash
# Set secrets
wrangler secret put STRIPE_SECRET_KEY
wrangler secret put STRIPE_WEBHOOK_SECRET
wrangler secret put STORE_DOMAIN

# Deploy
wrangler deploy

# Register Stripe webhook endpoint (Stripe CLI)
stripe listen --forward-to https://<worker>.workers.dev/stripe/webhook
```

---

## Anti-patterns

- **Creating Stripe session before D1 row** — If D1 is temporarily unavailable after the Stripe session is live, you have a Stripe session with no order record. Always write D1 first.
- **Not passing `orderId` in Stripe metadata** — Without metadata, the webhook has no way to correlate `checkout.session.completed` to your internal order. The Stripe session ID alone is insufficient if your D1 index is not up yet.
- **Using `stripe.webhooks.constructEvent` instead of `constructEventAsync`** — The synchronous version relies on Node.js `Buffer`; Workers require the async variant that uses `crypto.subtle` under the hood.
- **Forgetting to expire Stripe sessions** — Without `expires_at`, Stripe sessions live 24 hours by default. Align the expiry with your Cron cleanup window to avoid `pending` rows accumulating.

---

## Gotchas

- `stripe.checkout.sessions.create` is not idempotent by default. If the Worker retries after a timeout, you may create duplicate Stripe sessions. Consider passing an idempotency key derived from `orderId`.
- D1 `UPDATE ... WHERE status = 'pending'` in the webhook handler is the idempotency guard: a second webhook delivery for the same session is a no-op.
- Workers Cron Triggers fire at most once per invocation; if the scheduled handler throws, it will not retry automatically. Wrap `handleScheduled` in try/catch and log errors.
- The `stripe` npm package bundles `node-fetch` internally but respects `httpClient` override. Always pass `Stripe.createFetchHttpClient()` or you will get a runtime error about `XMLHttpRequest not defined`.
- `amount_total` on a Stripe session is in the smallest currency unit (cents for USD). Store it as `amount_cents` to avoid decimal precision issues.

---

## Verification

```bash
# Create a test checkout session
curl -X POST https://<worker>.workers.dev/checkout \
  -H "Content-Type: application/json" \
  -d '{"lineItems":[{"priceId":"price_test_xxx","quantity":1}],"customerEmail":"test@example.com"}'

# Confirm D1 row is pending
wrangler d1 execute orders-db \
  --command "SELECT * FROM orders ORDER BY created_at DESC LIMIT 1"

# Simulate Stripe webhook
stripe trigger checkout.session.completed

# Confirm order status flipped to paid
wrangler d1 execute orders-db \
  --command "SELECT id, status, completed_at FROM orders ORDER BY completed_at DESC LIMIT 1"

# Test orphan cleanup by invoking the cron manually
wrangler d1 execute orders-db \
  --command "UPDATE orders SET created_at = datetime('now','-2 hours') WHERE status='pending' LIMIT 1"
wrangler trigger schedule --name stripe-checkout
```

---

## Related

- `workers-paypal-webhook-verification.md`
- `workers-invoice-pdf-r2.md`
- `workers-apple-pay-payment-session.md`

---

## Sources

- Stripe Checkout Sessions API — https://stripe.com/docs/api/checkout/sessions
- Stripe Webhooks — https://stripe.com/docs/webhooks
- Cloudflare Workers D1 — https://developers.cloudflare.com/d1/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
