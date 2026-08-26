# Stripe Subscription Pause and Resume with Workers State Machine

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A user clicks "Pause my subscription" instead of cancelling outright. You need to stop billing for a defined period (e.g. 1–3 months), prevent feature access during the pause, and automatically resume billing when the pause window expires — all without losing the customer's payment method, history, or subscription object.

Stripe does not ship a native "pause" endpoint. The canonical approach combines `pause_collection` (halts invoice generation) with a Workers Durable Object or D1 record that drives the resume event at the right time.

---

## Context

Stripe's `pause_collection` field on a Subscription accepts a `behavior` of `keep_as_draft`, `mark_uncollectible`, or `void`. It also accepts `resumes_at` (Unix timestamp), after which Stripe automatically un-pauses. The catch: `resumes_at` must be set at pause time and cannot be extended without an explicit update — so if a user wants to extend their pause you must patch the subscription again.

Feature gating during a pause is not handled by Stripe. Your Workers middleware must check pause state on every privileged request and return `402 Payment Required` (or redirect to a resume screen) for paused accounts.

Key Stripe objects:
- `subscription.pause_collection` — controls invoice behaviour while paused
- `customer.invoice_settings.default_payment_method` — preserved through pause
- `subscription_schedule` — an alternative approach if you need phase-based pausing with defined billing anchors

---

## Section 1 — Pausing a Subscription via the API

```typescript
// workers/src/handlers/pause-subscription.ts
import Stripe from 'stripe';

export interface PauseRequest {
  subscriptionId: string;
  pauseDays: number;          // 7 | 30 | 60 | 90
  behavior?: 'keep_as_draft' | 'mark_uncollectible' | 'void';
}

export async function pauseSubscription(
  stripe: Stripe,
  env: Env,
  userId: string,
  req: PauseRequest,
): Promise<Stripe.Subscription> {
  const MAX_PAUSE_DAYS = 90;
  const days = Math.min(req.pauseDays, MAX_PAUSE_DAYS);
  const resumesAt = Math.floor(Date.now() / 1000) + days * 86_400;

  // Validate ownership before touching Stripe
  const row = await env.DB.prepare(
    'SELECT stripe_subscription_id FROM subscriptions WHERE user_id = ?1 AND stripe_subscription_id = ?2',
  )
    .bind(userId, req.subscriptionId)
    .first<{ stripe_subscription_id: string }>();

  if (!row) throw new Response('Subscription not found', { status: 404 });

  const sub = await stripe.subscriptions.update(req.subscriptionId, {
    pause_collection: {
      behavior: req.behavior ?? 'keep_as_draft',
      resumes_at: resumesAt,
    },
  });

  // Mirror pause state into D1 so Workers can gate features without a Stripe round-trip
  await env.DB.prepare(
    `UPDATE subscriptions
        SET status           = 'paused',
            paused_at        = ?1,
            resumes_at       = ?2,
            updated_at       = ?1
      WHERE stripe_subscription_id = ?3`,
  )
    .bind(Math.floor(Date.now() / 1000), resumesAt, req.subscriptionId)
    .run();

  return sub;
}
```

---

## Section 2 — Resuming Early (User-Initiated)

```typescript
// workers/src/handlers/resume-subscription.ts
import Stripe from 'stripe';

export async function resumeSubscription(
  stripe: Stripe,
  env: Env,
  userId: string,
  subscriptionId: string,
): Promise<Stripe.Subscription> {
  // Confirm ownership
  const row = await env.DB.prepare(
    `SELECT stripe_subscription_id, status
       FROM subscriptions
      WHERE user_id = ?1 AND stripe_subscription_id = ?2`,
  )
    .bind(userId, subscriptionId)
    .first<{ stripe_subscription_id: string; status: string }>();

  if (!row || row.status !== 'paused') {
    throw new Response('Subscription is not paused', { status: 409 });
  }

  // Clear pause_collection entirely to resume billing immediately
  const sub = await stripe.subscriptions.update(subscriptionId, {
    pause_collection: '',   // empty string clears the field
  });

  await env.DB.prepare(
    `UPDATE subscriptions
        SET status      = 'active',
            paused_at   = NULL,
            resumes_at  = NULL,
            updated_at  = ?1
      WHERE stripe_subscription_id = ?2`,
  )
    .bind(Math.floor(Date.now() / 1000), subscriptionId)
    .run();

  return sub;
}
```

---

## Section 3 — Feature-Gating Middleware in Workers

```typescript
// workers/src/middleware/subscription-guard.ts
import type { MiddlewareHandler } from 'hono';

export const subscriptionGuard: MiddlewareHandler = async (c, next) => {
  const userId: string = c.get('userId');   // set by auth middleware

  const sub = await c.env.DB.prepare(
    `SELECT status, resumes_at FROM subscriptions WHERE user_id = ?1 LIMIT 1`,
  )
    .bind(userId)
    .first<{ status: string; resumes_at: number | null }>();

  if (!sub) {
    return c.json({ error: 'no_subscription' }, 402);
  }

  if (sub.status === 'paused') {
    const resumeDate = sub.resumes_at
      ? new Date(sub.resumes_at * 1000).toISOString()
      : null;
    return c.json(
      { error: 'subscription_paused', resumes_at: resumeDate },
      402,
    );
  }

  await next();
};
```

---

## Section 4 — Stripe Webhook Sync for Automatic Resume

Stripe fires `customer.subscription.updated` when `resumes_at` passes and auto-unpauses. You must listen and update D1 accordingly.

```typescript
// workers/src/webhooks/stripe.ts  (excerpt for pause events)
import Stripe from 'stripe';

export async function handleSubscriptionUpdated(
  env: Env,
  sub: Stripe.Subscription,
): Promise<void> {
  const isPaused = sub.pause_collection !== null;
  const newStatus = isPaused ? 'paused' : sub.status;   // 'active', 'canceled', etc.

  await env.DB.prepare(
    `UPDATE subscriptions
        SET status      = ?1,
            paused_at   = ?2,
            resumes_at  = ?3,
            updated_at  = unixepoch()
      WHERE stripe_subscription_id = ?4`,
  )
    .bind(
      newStatus,
      sub.pause_collection ? sub.current_period_start : null,
      sub.pause_collection?.resumes_at ?? null,
      sub.id,
    )
    .run();

  // If auto-resume just fired, restore feature access log entry
  if (!isPaused && newStatus === 'active') {
    await env.DB.prepare(
      `INSERT INTO subscription_events (user_id, event, created_at)
         SELECT user_id, 'auto_resumed', unixepoch()
           FROM subscriptions WHERE stripe_subscription_id = ?1`,
    )
      .bind(sub.id)
      .run();
  }
}

// In your main webhook router:
// case 'customer.subscription.updated':
//   await handleSubscriptionUpdated(env, event.data.object as Stripe.Subscription);
```

---

## Anti-patterns

- **Setting `resumes_at` far in the future as a pseudo-cancel**: Stripe still holds the subscription open and will eventually attempt billing. Use `cancel_at` or `cancel_at_period_end` for true cancellations.
- **Relying solely on `resumes_at` for feature gating**: The `resumes_at` field only controls when Stripe un-pauses billing. You must gate features independently in Workers.
- **Clearing `pause_collection` with `null`**: Pass an empty string `''` to the Stripe API, not `null`. Using `null` does not clear the field in some SDK versions.
- **Not syncing pause state to D1**: If you only call the Stripe API without updating your local DB, cold-start Workers will hit Stripe on every request to check pause state — adding latency and burning API quota.
- **Allowing unlimited pause extensions**: Always enforce a maximum cumulative pause window (e.g. 90 days per calendar year) tracked in D1 to prevent indefinite non-payment.

---

## Gotchas

- `keep_as_draft` is the safest behavior: invoices accumulate as drafts and auto-void when the pause lifts. `void` discards them permanently — lost revenue if a user pauses in error.
- Stripe does NOT prorate or credit the paused period unless you issue an explicit credit note or adjust the next invoice manually.
- If the subscription has add-ons or metered items, `pause_collection` pauses the invoice but Stripe may still ingest usage events. Meter those to zero or stop reporting usage while paused.
- `subscription_schedule` phases are an alternative if you need a defined billing cadence after pause — but schedules add complexity and their own webhook surface.
- The `customer.subscription.updated` event fires for all subscription changes; always check `pause_collection` to distinguish a pause update from a plan change.

---

## Verification

```bash
# 1. Pause via your API
curl -X POST https://api.yourapp.com/subscriptions/pause \
  -H "Authorization: Bearer $JWT" \
  -d '{"subscriptionId":"sub_xxx","pauseDays":30}'

# 2. Confirm Stripe field is set
stripe subscriptions retrieve sub_xxx \
  | jq '.pause_collection'
# Expected: { "behavior": "keep_as_draft", "resumes_at": <timestamp> }

# 3. Confirm D1 mirror
wrangler d1 execute DB --command \
  "SELECT status, paused_at, resumes_at FROM subscriptions WHERE stripe_subscription_id='sub_xxx';"

# 4. Confirm feature gate blocks access
curl https://api.yourapp.com/protected-resource \
  -H "Authorization: Bearer $JWT"
# Expected: 402 { "error": "subscription_paused", "resumes_at": "..." }

# 5. Resume and verify
curl -X POST https://api.yourapp.com/subscriptions/resume \
  -H "Authorization: Bearer $JWT" \
  -d '{"subscriptionId":"sub_xxx"}'
stripe subscriptions retrieve sub_xxx | jq '.pause_collection'
# Expected: null
```

---

## Related

- `stripe-cancellation-flow.md` — hard cancel vs pause decision tree
- `stripe-dunning-management.md` — involuntary pause via failed payment
- `stripe-subscription-lifecycle.md` — full state machine reference
- `stripe-webhook-idempotency-workers.md` — safe webhook processing
- `payment-state-machine-design.md` — D1 state machine patterns

---

## Sources

- Stripe Docs — Pause a subscription: https://stripe.com/docs/billing/subscriptions/pause-payment
- Stripe API Reference — Subscription pause_collection: https://stripe.com/docs/api/subscriptions/object#subscription_object-pause_collection
- Cloudflare Workers D1: https://developers.cloudflare.com/d1/
