# Stripe Webhook Event Ordering with D1 and Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
Stripe delivers webhooks in a non-deterministic order — a `customer.subscription.updated` event can
arrive before its preceding `customer.subscription.created`. On example project, processing out-of-order
events causes subscription state corruption, double-grants of anonymous posting quotas, and phantom
cancellations that lock users out mid-session.

## Context
Cloudflare Workers runs stateless request handlers with no shared memory between invocations, making
it impossible to hold events in-flight while waiting for predecessors. D1 is the natural sequencing
store: serializable transactions allow atomic compare-and-swap on a `last_event_created` column,
enforcing a logical total order even when Stripe delivers events in parallel across multiple Worker
instances.

## Section 1 — D1 Schema and Sequence Tracking
Store a per-resource sequence number alongside current state. Stripe's `created` Unix timestamp plus
the event ID forms a deterministic ordering key for each subscription resource.

```typescript
// migrations/0001_webhook_ordering.sql
// CREATE TABLE webhook_events (
//   id TEXT PRIMARY KEY,
//   resource_id TEXT NOT NULL,
//   resource_type TEXT NOT NULL,
//   event_type TEXT NOT NULL,
//   stripe_created INTEGER NOT NULL,       -- Unix seconds from event.created
//   processed_at INTEGER,
//   status TEXT NOT NULL DEFAULT 'pending',
//   payload TEXT NOT NULL
// );
// CREATE INDEX idx_webhook_resource ON webhook_events(resource_id, stripe_created);
//
// CREATE TABLE subscription_state (
//   subscription_id TEXT PRIMARY KEY,
//   status TEXT NOT NULL,
//   current_period_end INTEGER NOT NULL,
//   last_event_id TEXT NOT NULL,
//   last_event_created INTEGER NOT NULL,
//   updated_at INTEGER NOT NULL
// );

interface Env {
  DB: D1Database;
  STRIPE_WEBHOOK_SECRET: string;
  RETRY_QUEUE: Queue<RetryMessage>;
}

interface StripeEvent {
  id: string;
  type: string;
  created: number; // Unix seconds
  data: { object: Record<string, unknown> };
}

interface RetryMessage {
  eventId: string;
  resourceId: string;
  retryCount: number;
}
```

## Section 2 — Webhook Ingestion with Ordering Guard
Each incoming event is first persisted to `webhook_events`, then applied only when its
`stripe_created` exceeds the current state's `last_event_created`. Stale arrivals are queued for
replay rather than dropped.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const sig = request.headers.get('stripe-signature') ?? '';
    const event = await verifyStripeWebhook(body, sig, env.STRIPE_WEBHOOK_SECRET);
    if (!event) return new Response('Invalid signature', { status: 400 });

    const sub = event.data.object as {
      id: string;
      status: string;
      current_period_end: number;
    };
    const resourceId = sub.id;

    // Idempotency gate — skip duplicate deliveries
    const dup = await env.DB
      .prepare('SELECT id FROM webhook_events WHERE id = ?')
      .bind(event.id)
      .first<{ id: string }>();
    if (dup) return new Response('Already processed', { status: 200 });

    // Persist the raw event before any state mutation
    await env.DB
      .prepare(
        `INSERT INTO webhook_events
           (id, resource_id, resource_type, event_type, stripe_created, status, payload)
         VALUES (?, ?, 'subscription', ?, ?, 'processing', ?)`
      )
      .bind(event.id, resourceId, event.type, event.created, body)
      .run();

    // Upsert subscription state only when this event is newer
    await env.DB
      .prepare(
        `INSERT INTO subscription_state
           (subscription_id, status, current_period_end,
            last_event_id, last_event_created, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(subscription_id) DO UPDATE SET
           status            = CASE WHEN excluded.last_event_created > last_event_created
                                    THEN excluded.status            ELSE status            END,
           current_period_end= CASE WHEN excluded.last_event_created > last_event_created
                                    THEN excluded.current_period_end ELSE current_period_end END,
           last_event_id     = CASE WHEN excluded.last_event_created > last_event_created
                                    THEN excluded.last_event_id     ELSE last_event_id     END,
           last_event_created= CASE WHEN excluded.last_event_created > last_event_created
                                    THEN excluded.last_event_created ELSE last_event_created END,
           updated_at        = CASE WHEN excluded.last_event_created > last_event_created
                                    THEN excluded.updated_at        ELSE updated_at        END`
      )
      .bind(
        resourceId,
        sub.status,
        sub.current_period_end,
        event.id,
        event.created,
        Date.now()
      )
      .run();

    // Read back to detect whether our update won the race
    const state = await env.DB
      .prepare(
        'SELECT last_event_id FROM subscription_state WHERE subscription_id = ?'
      )
      .bind(resourceId)
      .first<{ last_event_id: string }>();

    const applied = state?.last_event_id === event.id;
    const newStatus = applied ? 'processed' : 'skipped_stale';

    await env.DB
      .prepare('UPDATE webhook_events SET status = ?, processed_at = ? WHERE id = ?')
      .bind(newStatus, Date.now(), event.id)
      .run();

    if (!applied) {
      // Queue stale event for potential replay once state catches up
      await env.RETRY_QUEUE.send({ eventId: event.id, resourceId, retryCount: 0 });
    }

    return new Response('OK', { status: 200 });
  },
};

async function verifyStripeWebhook(
  body: string,
  sig: string,
  secret: string
): Promise<StripeEvent | null> {
  try {
    const parts = sig.split(',').reduce<Record<string, string>>((acc, part) => {
      const [k, v] = part.split('=');
      acc[k] = v;
      return acc;
    }, {});
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );
    const mac = await crypto.subtle.sign(
      'HMAC',
      key,
      new TextEncoder().encode(`${parts['t']}.${body}`)
    );
    const computed = Array.from(new Uint8Array(mac))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    return computed === parts['v1'] ? (JSON.parse(body) as StripeEvent) : null;
  } catch {
    return null;
  }
}
```

## Section 3 — Queue Consumer for Stale Event Replay
A Cloudflare Queue consumer retries skipped events with exponential backoff, applying them once the
state they depend on has been established by a later-arriving (but earlier-timestamped) event.

```typescript
export const queueHandler = {
  async queue(batch: MessageBatch<RetryMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { eventId, resourceId, retryCount } = msg.body;

      if (retryCount > 5) {
        await env.DB
          .prepare(`UPDATE webhook_events SET status = 'dead_letter' WHERE id = ?`)
          .bind(eventId)
          .run();
        msg.ack();
        continue;
      }

      const row = await env.DB
        .prepare('SELECT payload, stripe_created FROM webhook_events WHERE id = ?')
        .bind(eventId)
        .first<{ payload: string; stripe_created: number }>();
      if (!row) { msg.ack(); continue; }

      const event = JSON.parse(row.payload) as StripeEvent;
      const sub = event.data.object as {
        id: string; status: string; current_period_end: number;
      };

      const state = await env.DB
        .prepare(
          'SELECT last_event_created FROM subscription_state WHERE subscription_id = ?'
        )
        .bind(resourceId)
        .first<{ last_event_created: number }>();

      const canApply = !state || row.stripe_created > state.last_event_created;

      if (canApply) {
        await env.DB
          .prepare(
            `UPDATE subscription_state
             SET status = ?, current_period_end = ?,
                 last_event_id = ?, last_event_created = ?, updated_at = ?
             WHERE subscription_id = ?`
          )
          .bind(
            sub.status,
            sub.current_period_end,
            event.id,
            event.created,
            Date.now(),
            resourceId
          )
          .run();
        await env.DB
          .prepare(
            `UPDATE webhook_events SET status = 'processed', processed_at = ? WHERE id = ?`
          )
          .bind(Date.now(), eventId)
          .run();
        msg.ack();
      } else {
        msg.retry({ delaySeconds: Math.min(Math.pow(2, retryCount) * 30, 900) });
      }
    }
  },
};
```

## Section 4 — Monitoring Stale and Dead-Letter Events
Surface ordering anomalies via a scheduled Worker that alerts when events are stuck in `processing`
or promoted to `dead_letter`.

```typescript
export async function monitorWebhookOrdering(env: Env): Promise<void> {
  const ONE_HOUR_AGO_SECS = Math.floor(Date.now() / 1000) - 3600;

  const [stale, deadLetters] = await Promise.all([
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM webhook_events
         WHERE status = 'skipped_stale' AND stripe_created < ?`
      )
      .bind(ONE_HOUR_AGO_SECS)
      .first<{ count: number }>(),
    env.DB
      .prepare(
        `SELECT id, resource_id, event_type, stripe_created FROM webhook_events
         WHERE status = 'dead_letter' ORDER BY stripe_created DESC LIMIT 20`
      )
      .all<{ id: string; resource_id: string; event_type: string; stripe_created: number }>(),
  ]);

  if ((stale?.count ?? 0) > 0 || deadLetters.results.length > 0) {
    console.error(JSON.stringify({
      level: 'error',
      service: 'stripe-webhook-ordering',
      stale_events: stale?.count ?? 0,
      dead_letters: deadLetters.results,
      ts: new Date().toISOString(),
    }));
  }
}
```

## Anti-patterns
- Relying on the HTTP arrival order of webhook requests — Workers run in any PoP concurrently
- Comparing Stripe event IDs lexicographically to determine order (IDs are not time-sortable)
- Applying state updates outside a conditional upsert, creating race conditions between concurrent Workers
- Silently dropping stale events instead of queuing them for replay
- Using wall-clock `Date.now()` as the ordering key instead of Stripe's `event.created`

## Gotchas
- Stripe's `event.created` is Unix **seconds**, not milliseconds — normalize before comparison
- The `ON CONFLICT … DO UPDATE` CASE block must reference `excluded.*` columns for new values
- D1 batch operations are not atomic across multiple statements; use explicit `BEGIN … COMMIT` for strict isolation
- Allow a ±5 second tolerance window for Stripe clock skew when comparing event timestamps
- Dead-letter events require manual review; alert on them rather than silently archiving

## Verification
1. Run `stripe trigger customer.subscription.updated` back-to-back to simulate parallel delivery
2. Manually insert an event with an old `stripe_created` and confirm `skipped_stale` status in D1
3. Assert `subscription_state.last_event_created` advances monotonically across a replay sequence
4. Exhaust retry attempts on a queued event and confirm `dead_letter` appears in monitoring output

## Related
- /documentation/categories/payments/stripe-webhook-idempotency-d1-event-log.md
- /documentation/categories/payments/stripe-webhook-signature-verification.md
- /documentation/categories/payments/payment-retry-exponential-backoff-cloudflare-queues.md
- /documentation/categories/payments/stripe-subscription-lifecycle.md

## Sources
- https://docs.stripe.com/webhooks/best-practices#event-ordering
- https://docs.stripe.com/api/events/object#event_object-created
- https://developers.cloudflare.com/d1/platform/client-api/#dbbatch
- https://developers.cloudflare.com/queues/platform/javascript-apis/#message
