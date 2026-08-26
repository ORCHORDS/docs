# Chargebee Subscription Management on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You use Chargebee as your subscription billing engine and need a Cloudflare Workers layer
that: validates and processes Chargebee webhooks, syncs subscription state to D1 for fast
edge reads, creates or cancels subscriptions on demand via the Chargebee REST API, and
applies promotional coupons without exposing API keys to the browser.

## Context

Chargebee is a subscription management platform (SaaS billing, metered billing, multi-currency)
that emits events for every subscription and invoice lifecycle transition. Workers sit
between Chargebee and your application database, acting as a stateless event processor and
an API proxy for privileged Chargebee operations.

Key Chargebee concepts used here:

- **Subscription** — the core recurring billing entity, with states: `active`, `in_trial`,
  `cancelled`, `non_renewing`, `paused`.
- **Customer** — billing identity; 1:many with subscriptions.
- **Invoice** — generated at each billing cycle; carries line items and payment status.
- **Webhook event** — a signed POST with an `event_type` field dispatched to a registered
  endpoint.

Chargebee does not sign webhooks with HMAC; instead it uses HTTP Basic Auth
(`username:password` in the Authorization header, where the password is a webhook API key).

---

## 1. Authenticating Incoming Chargebee Webhooks

```typescript
// src/chargebee/webhook-auth.ts
export function verifyChargebeeWebhook(
  request: Request,
  webhookApiKey: string
): boolean {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader?.startsWith('Basic ')) return false;

  const encoded = authHeader.slice(6);
  const decoded = atob(encoded); // "username:apikey"
  const [, key] = decoded.split(':');
  return key === webhookApiKey;
}
```

---

## 2. Processing Subscription Events and Syncing to D1

```typescript
// src/chargebee/webhook-handler.ts
interface ChargebeeEvent {
  event_type: string;
  content: {
    subscription?: ChargebeeSubscription;
    invoice?: ChargebeeInvoice;
  };
}

interface ChargebeeSubscription {
  id: string;
  customer_id: string;
  status: string;
  plan_id: string;
  current_term_end: number; // Unix timestamp
  cancelled_at?: number;
}

interface ChargebeeInvoice {
  id: string;
  subscription_id: string;
  status: string;
  amount_due: number;
  currency_code: string;
}

export async function handleChargebeeWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  if (!verifyChargebeeWebhook(request, env.CHARGEBEE_WEBHOOK_API_KEY)) {
    return new Response('Unauthorized', { status: 401 });
  }

  const event = await request.json<ChargebeeEvent>();

  switch (event.event_type) {
    case 'subscription_created':
    case 'subscription_changed':
    case 'subscription_renewed':
    case 'subscription_cancelled':
    case 'subscription_reactivated':
    case 'subscription_paused':
    case 'subscription_resumed': {
      const sub = event.content.subscription;
      if (sub) await upsertSubscription(env.DB, sub);
      break;
    }
    case 'invoice_generated':
    case 'invoice_updated': {
      const inv = event.content.invoice;
      if (inv) await upsertInvoice(env.DB, inv);
      break;
    }
    default:
      // acknowledge and ignore unknown event types
      break;
  }

  return new Response('OK', { status: 200 });
}

async function upsertSubscription(
  db: D1Database,
  sub: ChargebeeSubscription
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO cb_subscriptions
         (id, customer_id, status, plan_id, current_term_end, cancelled_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
       ON CONFLICT(id) DO UPDATE SET
         status = excluded.status,
         plan_id = excluded.plan_id,
         current_term_end = excluded.current_term_end,
         cancelled_at = excluded.cancelled_at,
         updated_at = excluded.updated_at`
    )
    .bind(
      sub.id,
      sub.customer_id,
      sub.status,
      sub.plan_id,
      sub.current_term_end,
      sub.cancelled_at ?? null,
      new Date().toISOString()
    )
    .run();
}

async function upsertInvoice(
  db: D1Database,
  inv: ChargebeeInvoice
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO cb_invoices (id, subscription_id, status, amount_due, currency_code, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)
       ON CONFLICT(id) DO UPDATE SET
         status = excluded.status,
         amount_due = excluded.amount_due,
         updated_at = excluded.updated_at`
    )
    .bind(
      inv.id,
      inv.subscription_id,
      inv.status,
      inv.amount_due,
      inv.currency_code,
      new Date().toISOString()
    )
    .run();
}
```

---

## 3. Creating a Subscription via the Chargebee API

```typescript
// src/chargebee/subscription-create.ts
export async function createChargebeeSubscription(params: {
  customerId: string;
  planId: string;
  couponIds?: string[];
  trialEnd?: number;
  env: Env;
}): Promise<{ subscriptionId: string; status: string }> {
  const { customerId, planId, couponIds, trialEnd, env } = params;
  const site = env.CHARGEBEE_SITE;
  const apiKey = env.CHARGEBEE_API_KEY;
  const credentials = btoa(`${apiKey}:`);

  const body = new URLSearchParams({
    'subscription[plan_id]': planId,
  });
  if (trialEnd) body.set('subscription[trial_end]', String(trialEnd));
  if (couponIds?.length) body.set('coupon_ids[]', couponIds.join(','));

  const res = await fetch(
    `https://${site}.chargebee.com/api/v2/customers/${customerId}/subscriptions`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Chargebee subscription create failed: ${res.status} ${err}`);
  }

  const data = await res.json<{
    subscription: { id: string; status: string };
  }>();
  return {
    subscriptionId: data.subscription.id,
    status: data.subscription.status,
  };
}
```

---

## 4. Cancelling a Subscription at Period End

```typescript
// src/chargebee/subscription-cancel.ts
export async function cancelAtTermEnd(
  subscriptionId: string,
  env: Env
): Promise<void> {
  const credentials = btoa(`${env.CHARGEBEE_API_KEY}:`);

  const res = await fetch(
    `https://${env.CHARGEBEE_SITE}.chargebee.com/api/v2/subscriptions/${subscriptionId}/cancel_for_items`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({ end_of_term: 'true' }),
    }
  );

  if (!res.ok) throw new Error(`Chargebee cancel failed: ${res.status}`);
}
```

---

## 5. Reading Subscription State from the Edge (D1)

```typescript
// src/chargebee/subscription-read.ts
export async function getSubscriptionStatus(
  customerId: string,
  db: D1Database
): Promise<{ subscriptionId: string; status: string; planId: string } | null> {
  const row = await db
    .prepare(
      `SELECT id, status, plan_id FROM cb_subscriptions
       WHERE customer_id = ?1
       ORDER BY current_term_end DESC LIMIT 1`
    )
    .bind(customerId)
    .first<{ id: string; status: string; plan_id: string }>();

  if (!row) return null;
  return { subscriptionId: row.id, status: row.status, planId: row.plan_id };
}
```

---

## Anti-patterns

- **Trusting Chargebee webhook content without re-fetching** for high-value transitions — the
  webhook payload can arrive out of order; re-fetch via `GET /subscriptions/{id}` to confirm
  state before granting access.
- **Storing the Chargebee API key in a Worker environment variable without KV caching** — for
  high-traffic endpoints, rate limits (150 req/s on most plans) are hit quickly; cache
  subscription state in D1 rather than hitting Chargebee on every request.
- **Using `v1` API endpoints** — Chargebee's v1 API is deprecated; use v2 exclusively.
- **Ignoring `payment_source_expiring` events** — failing to prompt customers for updated
  payment methods before expiry causes involuntary churn.

## Gotchas

- Chargebee webhooks retry for up to 24 hours; ensure idempotent upserts in D1 to handle
  duplicate deliveries.
- The `subscription_changed` event fires for plan upgrades, downgrades, quantity changes,
  and coupon additions. Parse `event_type` and inspect changed fields before acting.
- `cancel_for_items` vs `cancel` — use `cancel_for_items` for item-based subscriptions;
  the legacy `cancel` endpoint works only for plan-based (v1 model) subscriptions.
- Chargebee uses form-encoded bodies (`application/x-www-form-urlencoded`) for all POST
  requests, not JSON — a common integration mistake.
- Test mode and live mode share the same API key format but use different site subdomain
  prefixes (`mysite-test` vs `mysite`).

## Verification

```bash
# Check D1 subscription state after a webhook
wrangler d1 execute DB --command \
  "SELECT id, status, plan_id, updated_at FROM cb_subscriptions ORDER BY updated_at DESC LIMIT 5"

# Replay a webhook from Chargebee dashboard or via curl (Basic Auth)
curl -X POST https://your-worker.your-subdomain.workers.dev/webhooks/chargebee \
  -u "admin:$CHARGEBEE_WEBHOOK_API_KEY" \
  -H "Content-Type: application/json" \
  -d @test-subscription-created.json
```

## Related

- `subscription-billing-lifecycle.md`
- `subscription-dunning-retry-recovery.md`
- `payment-dunning-management-cloudflare-queues.md`
- `stripe-billing-portal-workers-session-management.md`

## Sources

- https://apidocs.chargebee.com/docs/api/
- https://apidocs.chargebee.com/docs/api/subscriptions
- https://apidocs.chargebee.com/docs/api/events
- https://developers.cloudflare.com/d1/
