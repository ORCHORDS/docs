# Stripe Webhook Idempotency with Cloudflare D1 — Storing Event IDs to Deduplicate Replays

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Stripe guarantees at-least-once delivery for webhooks. In practice this means an event like `customer.subscription.deleted` or `invoice.payment_succeeded` can arrive two, three, or more times within seconds of each other when Stripe retries a delivery that timed out. Without deduplication, your Worker might cancel a subscription twice, double-credit an account, or send duplicate confirmation emails. You need a lightweight, durable event log in Cloudflare D1 that rejects duplicate Stripe event IDs before any business logic runs.

---

## Context

Stripe assigns each webhook event a globally unique `evt_` ID. The Stripe documentation explicitly recommends storing processed event IDs and ignoring duplicates. The challenge at the edge is:

1. **Race conditions.** Two simultaneous webhook deliveries of the same event can both pass a `SELECT` check before either has committed an `INSERT`. A `UNIQUE` constraint on the event ID column converts this race into a caught exception rather than a double-process.
2. **D1 transaction semantics.** D1 supports `BEGIN`/`COMMIT`/`ROLLBACK` within a single Worker request but not cross-request distributed transactions. The UNIQUE-constraint-as-lock pattern fits this constraint perfectly.
3. **Billing event ordering.** `billing.subscription.*` events carry a `created` timestamp. Even with deduplication, events can arrive out of order. The event log should record arrival order and creation time separately.

---

## Section 1 — D1 Schema for the Event Log

```sql
-- migrations/0010_stripe_event_log.sql
CREATE TABLE IF NOT EXISTS stripe_event_log (
  id            TEXT    PRIMARY KEY,          -- evt_... (Stripe event ID)
  type          TEXT    NOT NULL,             -- e.g. "invoice.payment_succeeded"
  livemode      INTEGER NOT NULL DEFAULT 0,   -- 0 = test, 1 = live
  stripe_created_at INTEGER NOT NULL,         -- Unix timestamp from Stripe event object
  received_at   INTEGER NOT NULL,             -- Unix timestamp when Worker received it
  processed_at  INTEGER,                      -- NULL until processing completes
  status        TEXT    NOT NULL DEFAULT 'pending',  -- pending | processed | failed | skipped
  error_message TEXT                          -- populated on status = failed
);

CREATE INDEX IF NOT EXISTS idx_sel_type_created
  ON stripe_event_log (type, stripe_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sel_status
  ON stripe_event_log (status)
  WHERE status != 'processed';
```

Apply with:

```bash
wrangler d1 migrations apply STRIPE_DB --remote
```

The `PRIMARY KEY` on `id` creates a B-tree unique index in SQLite (D1's engine). Any attempt to insert a duplicate `evt_` value raises `UNIQUE constraint failed: stripe_event_log.id`, which the Worker catches and treats as "already processed".

---

## Section 2 — Signature Verification Before Deduplication

Always verify the Stripe-Signature header before touching D1. An unauthenticated event with a fabricated `evt_` ID could otherwise poison the log and prevent legitimate events from processing.

```typescript
// worker/src/handlers/stripe-webhook.ts
import Stripe from "stripe";

export interface Env {
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_SECRET_KEY: string;
  STRIPE_DB: D1Database;
}

export async function handleStripeWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get("stripe-signature");

  if (!sig) {
    return new Response("Missing stripe-signature", { status: 400 });
  }

  let event: Stripe.Event;
  try {
    // constructEventAsync is the Workers-compatible variant (no Node crypto)
    event = await new Stripe(env.STRIPE_SECRET_KEY, {
      apiVersion: "2024-11-20.acacia",
      httpClient: Stripe.createFetchHttpClient(),
    }).webhooks.constructEventAsync(body, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response(`Webhook signature verification failed: ${err}`, {
      status: 400,
    });
  }

  // Deduplication + processing
  return processEvent(event, env);
}
```

---

## Section 3 — Idempotent Insert Pattern with UNIQUE Constraint

The core pattern: attempt to insert the event ID into the log. If D1 raises a UNIQUE constraint error, the event was already received — return 200 immediately. If the insert succeeds, process the event, then update the row to `processed` or `failed`.

```typescript
// worker/src/handlers/stripe-webhook.ts (continued)
async function processEvent(
  event: Stripe.Event,
  env: Env
): Promise<Response> {
  const now = Math.floor(Date.now() / 1000);

  // Attempt to claim the event. D1 raises SQLITE_CONSTRAINT_PRIMARYKEY
  // (error code 1555) on duplicate. We catch it and return 200.
  try {
    await env.STRIPE_DB.prepare(
      `INSERT INTO stripe_event_log
         (id, type, livemode, stripe_created_at, received_at, status)
       VALUES (?, ?, ?, ?, ?, 'pending')`
    )
      .bind(
        event.id,
        event.type,
        event.livemode ? 1 : 0,
        event.created,
        now
      )
      .run();
  } catch (err: unknown) {
    // D1 wraps SQLite errors; check message for UNIQUE constraint violation
    const msg = err instanceof Error ? err.message : String(err);
    if (
      msg.includes("UNIQUE constraint failed") ||
      msg.includes("SQLITE_CONSTRAINT")
    ) {
      // Duplicate event — acknowledge to Stripe and stop
      return new Response(
        JSON.stringify({ received: true, duplicate: true }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    // Unexpected D1 error — return 500 so Stripe retries
    console.error("D1 insert error:", err);
    return new Response("Internal error", { status: 500 });
  }

  // Event is now claimed. Run business logic.
  let status: "processed" | "failed" | "skipped" = "skipped";
  let errorMessage: string | null = null;

  try {
    status = await dispatchEvent(event, env);
  } catch (err) {
    status = "failed";
    errorMessage = err instanceof Error ? err.message : String(err);
    console.error(`Failed to process ${event.id}:`, err);
  }

  // Update the log row regardless of outcome
  await env.STRIPE_DB.prepare(
    `UPDATE stripe_event_log
     SET status = ?, processed_at = ?, error_message = ?
     WHERE id = ?`
  )
    .bind(status, Math.floor(Date.now() / 1000), errorMessage, event.id)
    .run();

  // Return 200 even on processing failure — Stripe should NOT retry
  // a syntactically valid event that we have recorded. Retrying a failed
  // billing event can cause double-charges. Handle failures via internal
  // alerting, not Stripe retries.
  return new Response(
    JSON.stringify({ received: true, status }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}
```

---

## Section 4 — Dispatching `billing.subscription.*` Events Safely

Subscription lifecycle events require special care: they can arrive out of order, and they carry embedded subscription objects that may be stale by the time you read them.

```typescript
// worker/src/handlers/stripe-webhook.ts (continued)
async function dispatchEvent(
  event: Stripe.Event,
  env: Env
): Promise<"processed" | "skipped"> {
  switch (event.type) {
    case "customer.subscription.created":
    case "customer.subscription.updated":
      return handleSubscriptionUpsert(event, env);

    case "customer.subscription.deleted":
      return handleSubscriptionDeleted(event, env);

    case "invoice.payment_succeeded":
      return handleInvoicePaymentSucceeded(event, env);

    case "invoice.payment_failed":
      return handleInvoicePaymentFailed(event, env);

    default:
      return "skipped";
  }
}

async function handleSubscriptionUpsert(
  event: Stripe.Event,
  env: Env
): Promise<"processed"> {
  const sub = event.data.object as Stripe.Subscription;

  // IMPORTANT: The subscription object embedded in the event may be
  // up to a few seconds stale when events arrive out of order.
  // For critical fields (status, current_period_end), re-fetch from
  // the Stripe API to get the current state.
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-11-20.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });
  const freshSub = await stripe.subscriptions.retrieve(sub.id);

  await env.STRIPE_DB.prepare(
    `INSERT INTO subscriptions (id, customer_id, status, plan_id, current_period_end, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       status             = excluded.status,
       plan_id            = excluded.plan_id,
       current_period_end = excluded.current_period_end,
       updated_at         = excluded.updated_at
     WHERE excluded.updated_at > subscriptions.updated_at`
  )
    .bind(
      freshSub.id,
      freshSub.customer as string,
      freshSub.status,
      (freshSub.items.data[0]?.price.id) ?? null,
      freshSub.current_period_end,
      Math.floor(Date.now() / 1000)
    )
    .run();

  return "processed";
}

async function handleSubscriptionDeleted(
  event: Stripe.Event,
  env: Env
): Promise<"processed"> {
  const sub = event.data.object as Stripe.Subscription;

  // Mark as canceled — do NOT delete the row (audit trail)
  await env.STRIPE_DB.prepare(
    `UPDATE subscriptions SET status = 'canceled', updated_at = ? WHERE id = ?`
  )
    .bind(Math.floor(Date.now() / 1000), sub.id)
    .run();

  // Revoke access — idempotent because we check current status first
  const current = await env.STRIPE_DB.prepare(
    `SELECT status FROM subscriptions WHERE id = ?`
  )
    .bind(sub.id)
    .first<{ status: string }>();

  if (current?.status === "canceled") {
    await revokeUserAccess(sub.customer as string, env);
  }

  return "processed";
}
```

The `ON CONFLICT … WHERE excluded.updated_at > subscriptions.updated_at` clause in the upsert ensures that an older out-of-order event cannot overwrite a newer state already stored in D1.

---

## Section 5 — Handling Race Conditions in Detail

Two concurrent deliveries of the same Stripe event create a race window between the deduplication check and the insert. The UNIQUE constraint eliminates this window entirely because SQLite serializes writes within D1:

```
Request A (arrives t=0ms):   INSERT evt_123 → succeeds → processes
Request B (arrives t=1ms):   INSERT evt_123 → UNIQUE constraint → returns 200 immediately
```

Even if both requests arrive within the same millisecond, D1 serializes the inserts. One wins; the other gets a constraint error. No double-processing occurs.

There is one edge case: if Request A's Worker isolate is killed after the `INSERT` but before the `UPDATE` to `processed`, the row stays in `pending` state forever. Implement a cleanup job:

```typescript
// worker/src/cron/cleanup-pending-events.ts
export async function cleanupStuckEvents(env: Env): Promise<void> {
  const cutoff = Math.floor(Date.now() / 1000) - 300; // 5 minutes ago

  const stuck = await env.STRIPE_DB.prepare(
    `SELECT id, type FROM stripe_event_log
     WHERE status = 'pending' AND received_at < ?
     LIMIT 20`
  )
    .bind(cutoff)
    .all<{ id: string; type: string }>();

  for (const row of stuck.results) {
    // Re-fetch from Stripe to determine actual outcome
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
      apiVersion: "2024-11-20.acacia",
      httpClient: Stripe.createFetchHttpClient(),
    });
    try {
      const event = await stripe.events.retrieve(row.id);
      // If Stripe still has it, the event was likely not processed
      // Mark as failed so alerting fires
      await env.STRIPE_DB.prepare(
        `UPDATE stripe_event_log SET status = 'failed',
         error_message = 'Stuck in pending — isolate likely crashed'
         WHERE id = ? AND status = 'pending'`
      )
        .bind(row.id)
        .run();
      console.warn(`Marked stuck event ${row.id} (${row.type}) as failed`);
    } catch {
      // Stripe returned 404 — event ID invalid or deleted; mark skipped
      await env.STRIPE_DB.prepare(
        `UPDATE stripe_event_log SET status = 'skipped' WHERE id = ?`
      )
        .bind(row.id)
        .run();
    }
  }
}
```

Wire it to a Cron Trigger in `wrangler.toml`:

```toml
[triggers]
  crons = ["*/5 * * * *"]
```

---

## Section 6 — Querying the Event Log for Debugging and Reconciliation

```sql
-- Recent failed events
SELECT id, type, stripe_created_at, error_message
FROM stripe_event_log
WHERE status = 'failed'
ORDER BY received_at DESC
LIMIT 50;

-- Duplicate attempts over the last hour
SELECT e1.id, e1.type, COUNT(*) as attempt_count
FROM stripe_event_log e1
WHERE e1.received_at > unixepoch() - 3600
GROUP BY e1.id
HAVING attempt_count > 1;

-- Subscription events received out of order
-- (received_at earlier than a later event's stripe_created_at for same sub)
SELECT a.id, a.type, a.stripe_created_at, a.received_at,
       b.id as later_id, b.stripe_created_at as later_stripe_ts
FROM stripe_event_log a
JOIN stripe_event_log b
  ON  a.type LIKE 'customer.subscription.%'
  AND b.type LIKE 'customer.subscription.%'
  AND a.stripe_created_at > b.stripe_created_at
  AND a.received_at < b.received_at
LIMIT 20;
```

---

## Anti-Patterns

- **SELECT-then-INSERT deduplication.** A `SELECT COUNT(*) FROM stripe_event_log WHERE id = ?` check before `INSERT` has a race window. Two concurrent requests both see `0`, both proceed to insert, one fails. The UNIQUE constraint alone is sufficient — skip the SELECT.
- **Returning 500 on duplicate detection.** Returning 5xx tells Stripe to retry. Return 200 to acknowledge receipt even when the event is a duplicate.
- **Returning 500 on business-logic failure.** If your billing logic fails (e.g., a downstream API is down), do not return 500 — Stripe will retry. Record the failure in D1, return 200, and alert internally. Stripe retries are not a substitute for your own retry/dead-letter queue.
- **Trusting the embedded subscription object for critical fields.** The `event.data.object` snapshot can be seconds old. Always re-fetch from Stripe API when the action depends on current subscription status.
- **Deleting processed event rows.** Keep event log rows for at least 90 days for reconciliation and chargebacks. Use the `status` column to distinguish processed from pending/failed.

---

## Gotchas

1. **D1 error message format.** D1 wraps SQLite errors in a generic `Error`. The message string contains `"UNIQUE constraint failed"` but the exact format can vary. Check for both `"UNIQUE constraint failed"` and `"SQLITE_CONSTRAINT"` in the catch block.
2. **`constructEventAsync` vs `constructEvent`.** Cloudflare Workers do not ship Node's `crypto` module. Use `stripe.webhooks.constructEventAsync()` which uses the Web Crypto API instead.
3. **Clock skew in `stripe_created_at`.** Stripe's `event.created` is a Unix timestamp in seconds. D1's `unixepoch()` is also seconds. Mixing milliseconds and seconds in comparisons is a common bug — always normalize to seconds.
4. **`billing.subscription.updated` frequency.** This event fires on nearly every subscription change, including Stripe's automatic proration recalculations. Expect high volume; ensure your D1 insert throughput is sufficient (D1 handles ~1,000 writes/sec per database in most regions).
5. **Idempotency of the cleanup cron.** The `UPDATE … WHERE status = 'pending'` in the cleanup job is itself idempotent — running it twice on the same row only changes `pending` → `failed` once.

---

## Verification

```bash
# 1. Send a real test event twice with the same event ID
stripe trigger invoice.payment_succeeded --stripe-account acct_test123
# Then replay the same event using the Stripe Dashboard "Resend" button

# 2. Check the D1 log — should show exactly one row
wrangler d1 execute STRIPE_DB --remote \
  --command "SELECT id, status, received_at FROM stripe_event_log ORDER BY received_at DESC LIMIT 5;"

# 3. Confirm no duplicate subscription records were created
wrangler d1 execute STRIPE_DB --remote \
  --command "SELECT id, status, COUNT(*) as n FROM subscriptions GROUP BY id HAVING n > 1;"

# 4. Simulate a race condition locally with wrk or k6
# Fire 10 concurrent requests with the same synthetic evt_ ID
k6 run --vus 10 --iterations 10 stripe-webhook-race-test.js
# Expected: exactly one "processed" row in stripe_event_log
```

---

## Related Articles

- `documentation/docs/policies/payments/stripe-webhook-idempotency-workers.md`
- `documentation/docs/policies/payments/stripe-webhook-signature-verification.md`
- `documentation/docs/policies/payments/stripe-subscription-lifecycle.md`
- `documentation/docs/policies/payments/idempotency-keys-payment-apis.md`
- `documentation/docs/policies/payments/payment-retry-exponential-backoff-cloudflare-queues.md`
- `documentation/docs/policies/security/race-condition-toctou-web.md`

---

## Sources

- Stripe webhook best practices — https://stripe.com/docs/webhooks/best-practices
- Stripe event object reference — https://stripe.com/docs/api/events
- D1 SQL API — https://developers.cloudflare.com/d1/worker-api/
- SQLite UNIQUE constraint — https://www.sqlite.org/lang_createtable.html#unique_constraints
- `stripe-node` constructEventAsync — https://github.com/stripe/stripe-node#webhook-signing
