# Pausing and Resuming Stripe Subscriptions from a Cloudflare Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A customer requests a temporary subscription pause (e.g. seasonal hiatus) and you need to halt billing without cancelling the subscription. The Worker must call the Stripe `pause_collection` API, track the pause state in KV, and enforce a maximum grace period before auto-resumption.

---

## Context

Stripe supports `pause_collection` on a subscription object, which stops invoice generation while keeping the subscription active. The pause is not a separate resource; it is a field on the subscription. Because Workers are stateless, KV is used as a fast read layer to check pause status on every authenticated request, avoiding a round-trip to Stripe. D1 serves as the durable source of truth and audit log. A nightly Cron Trigger inspects D1 for subscriptions whose grace period has expired and resumes them automatically. The `customer.subscription.updated` webhook keeps D1 in sync whenever Stripe's own state changes.

---

## Section 1 — wrangler.toml

```toml
name = "billing-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "SUB_STATE"
id     = "<your-kv-namespace-id>"

[[d1_databases]]
binding  = "DB"
database_name = "billing"
database_id   = "<your-d1-database-id>"

[triggers]
crons = ["0 4 * * *"]   # daily at 04:00 UTC — grace-period enforcer
```

---

## Section 2 — Worker Implementation

```typescript
import Stripe from 'stripe';

export interface Env {
  DB: D1Database;
  SUB_STATE: KVNamespace;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  PAUSE_GRACE_DAYS: string;   // e.g. "30"
}

const KV_TTL_SECONDS = 60 * 60 * 24 * 90; // 90 days max cache

function stripe(env: Env) {
  return new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
}

// POST /subscriptions/:id/pause
export async function pauseSubscription(
  subscriptionId: string,
  env: Env
): Promise<Response> {
  const graceDays = parseInt(env.PAUSE_GRACE_DAYS ?? '30', 10);
  const resumesAt = Math.floor(Date.now() / 1000) + graceDays * 86400;

  const updated = await stripe(env).subscriptions.update(subscriptionId, {
    pause_collection: {
      behavior: 'void',         // void invoices instead of drafting them
      resumes_at: resumesAt,    // Stripe will auto-resume at this unix timestamp
    },
  });

  // Write fast-read state to KV
  await env.SUB_STATE.put(
    `sub:${subscriptionId}:paused`,
    JSON.stringify({
      status: 'paused',
      resumes_at: resumesAt,
      paused_at: Math.floor(Date.now() / 1000),
    }),
    { expirationTtl: KV_TTL_SECONDS }
  );

  // Write durable record to D1
  await env.DB.prepare(
    `INSERT INTO subscription_pauses
       (subscription_id, paused_at, resumes_at, status)
     VALUES (?1, datetime('now'), datetime(?2, 'unixepoch'), 'paused')
     ON CONFLICT(subscription_id) DO UPDATE
       SET paused_at  = excluded.paused_at,
           resumes_at = excluded.resumes_at,
           status     = 'paused'`
  )
    .bind(subscriptionId, resumesAt)
    .run();

  return Response.json({ subscription_id: subscriptionId, status: 'paused', resumes_at: resumesAt });
}

// POST /subscriptions/:id/resume
export async function resumeSubscription(
  subscriptionId: string,
  env: Env
): Promise<Response> {
  await stripe(env).subscriptions.update(subscriptionId, {
    pause_collection: '',   // empty string clears the pause
  });

  // Remove KV entry so the next check reflects live state
  await env.SUB_STATE.delete(`sub:${subscriptionId}:paused`);

  await env.DB.prepare(
    `UPDATE subscription_pauses
     SET status = 'resumed', resumed_at = datetime('now')
     WHERE subscription_id = ?1`
  )
    .bind(subscriptionId)
    .run();

  return Response.json({ subscription_id: subscriptionId, status: 'resumed' });
}

// Cron handler — enforce grace period
export async function enforcePauseGracePeriod(env: Env): Promise<void> {
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ');

  // Find subscriptions whose grace period has expired
  const { results } = await env.DB.prepare(
    `SELECT subscription_id FROM subscription_pauses
     WHERE status = 'paused' AND resumes_at <= datetime(?1)`
  )
    .bind(now)
    .all<{ subscription_id: string }>();

  for (const row of results) {
    try {
      await resumeSubscription(row.subscription_id, env);
      console.log(`Auto-resumed subscription ${row.subscription_id}`);
    } catch (err) {
      console.error(`Failed to auto-resume ${row.subscription_id}:`, err);
    }
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/subscriptions\/([^/]+)\/(pause|resume)$/);
    if (request.method === 'POST' && match) {
      const [, id, action] = match;
      return action === 'pause'
        ? pauseSubscription(id, env)
        : resumeSubscription(id, env);
    }
    if (url.pathname === '/webhooks/stripe') {
      return handleWebhook(request, env);
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await enforcePauseGracePeriod(env);
  },
};
```

---

## Section 3 — Webhook Handler

```typescript
async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const sig = request.headers.get('stripe-signature') ?? '';
  const body = await request.text();

  let event: Stripe.Event;
  try {
    event = await stripe(env).webhooks.constructEventAsync(
      body,
      sig,
      env.STRIPE_WEBHOOK_SECRET
    );
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  if (event.type === 'customer.subscription.updated') {
    const sub = event.data.object as Stripe.Subscription;
    const isPaused = sub.pause_collection !== null;
    const newStatus = isPaused ? 'paused' : 'active';

    // Sync KV
    if (isPaused && sub.pause_collection) {
      await env.SUB_STATE.put(
        `sub:${sub.id}:paused`,
        JSON.stringify({
          status: 'paused',
          resumes_at: sub.pause_collection.resumes_at,
        }),
        { expirationTtl: KV_TTL_SECONDS }
      );
    } else {
      await env.SUB_STATE.delete(`sub:${sub.id}:paused`);
    }

    // Sync D1
    await env.DB.prepare(
      `INSERT INTO subscription_pauses (subscription_id, status, resumes_at)
       VALUES (?1, ?2, datetime(?3, 'unixepoch'))
       ON CONFLICT(subscription_id) DO UPDATE
         SET status = excluded.status,
             resumes_at = excluded.resumes_at,
             updated_at = datetime('now')`
    )
      .bind(
        sub.id,
        newStatus,
        sub.pause_collection?.resumes_at ?? null
      )
      .run();
  }

  return new Response('ok', { status: 200 });
}
```

---

## Anti-patterns

- **Cancelling instead of pausing** — Cancellation is irreversible through the normal billing flow; use `pause_collection` for temporary holds.
- **Using KV as the only state store** — KV has eventual consistency and can return stale data; always treat D1 as authoritative for billing decisions.
- **Not setting `resumes_at`** — Without an explicit resume timestamp Stripe pauses indefinitely; always pass a timestamp to bound the grace period.
- **Polling Stripe API on every request to check pause status** — Cache the pause state in KV to avoid rate limiting and latency spikes.

---

## Gotchas

- Passing `pause_collection: ''` (empty string) is the documented way to clear a pause; passing `null` throws a Stripe type error in TypeScript.
- The `resumes_at` field inside `pause_collection` is a Unix timestamp, not an ISO string; convert when writing to D1 `datetime` columns.
- The Cron Trigger fires in UTC; ensure your `PAUSE_GRACE_DAYS` calculation is also UTC-based.
- If a webhook arrives before the KV write completes, the next request may still show `paused`; always verify against D1 for billing-critical paths.
- Stripe may retry webhooks up to 3 days; implement idempotent D1 upserts (shown above) to handle duplicate events safely.

---

## Verification

```bash
# Pause a subscription
curl -X POST https://your-worker.workers.dev/subscriptions/sub_xxx/pause

# Confirm KV entry
npx wrangler kv key get --namespace-id=<id> "sub:sub_xxx:paused"

# Confirm D1 record
npx wrangler d1 execute billing --command \
  "SELECT * FROM subscription_pauses WHERE subscription_id = 'sub_xxx';"

# Simulate webhook
stripe listen --forward-to localhost:8787/webhooks/stripe
stripe trigger customer.subscription.updated
```

---

## Related

- `stripe-connect-platform-workers-d1.md`
- `payment-idempotency-key-workers-kv.md`

---

## Sources

- Stripe Pause Collection — https://stripe.com/docs/billing/subscriptions/pause-payment
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
