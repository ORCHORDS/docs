# Stripe Webhook Handler in Workers with D1-Based Event Deduplication

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Stripe retries webhook delivery up to 3 days when your endpoint returns a non-2xx response or times out. Without deduplication, slow downstream processing or transient failures cause the same event (e.g., `charge.succeeded`) to be processed multiple times, resulting in duplicate orders, double emails, or double credits. This article shows how to verify the Stripe signature with Web Crypto and deduplicate events atomically using D1's `INSERT OR IGNORE` constraint.

---

## Context

Stripe signs every webhook payload with an HMAC-SHA256 signature computed over a timestamp and the raw body, delivered in the `Stripe-Signature` header. Validating this signature in a Worker requires the raw request body as an `ArrayBuffer` before any JSON parsing. D1 is Cloudflare's serverless SQLite offering, which supports standard SQL constraints including `UNIQUE` and `ON CONFLICT IGNORE` semantics. Storing the Stripe `event.id` (e.g., `evt_1234`) as a primary key and using `INSERT OR IGNORE` provides an atomic, single-query deduplication guard that works correctly under concurrent retry storms. The Worker must return HTTP 200 immediately after inserting the event record; actual processing can be offloaded to a Queue to keep webhook latency low.

---

## Section 1 — D1 Schema

```sql
-- migrations/0001_stripe_events.sql
CREATE TABLE IF NOT EXISTS stripe_events (
  id              TEXT PRIMARY KEY,          -- Stripe event ID: evt_xxx
  type            TEXT NOT NULL,
  livemode        INTEGER NOT NULL DEFAULT 0,
  created_at      INTEGER NOT NULL,          -- Unix timestamp from Stripe
  processed_at    INTEGER,                   -- NULL = pending, set after processing
  payload         TEXT NOT NULL,             -- Raw JSON blob
  inserted_epoch  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_stripe_events_type ON stripe_events (type);
CREATE INDEX IF NOT EXISTS idx_stripe_events_processed ON stripe_events (processed_at)
  WHERE processed_at IS NULL;
```

---

## Section 2 — Worker Implementation

```typescript
// src/stripe-webhook.ts
import { D1Database, Queue } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  STRIPE_WEBHOOK_SECRET: string;  // whsec_...
  PAYMENT_EVENTS_QUEUE: Queue<StripeQueueMessage>;
}

interface StripeQueueMessage {
  eventId: string;
  eventType: string;
  payload: string;
}

const STRIPE_SIGNATURE_HEADER = 'stripe-signature';
const TOLERANCE_SECONDS = 300; // 5 minutes

async function verifyStripeSignature(
  rawBody: ArrayBuffer,
  sigHeader: string,
  secret: string,
): Promise<boolean> {
  const params = Object.fromEntries(
    sigHeader.split(',').map((part) => {
      const [k, v] = part.split('=');
      return [k.trim(), v.trim()];
    }),
  );

  const timestamp = parseInt(params['t'], 10);
  const signatures: string[] = sigHeader
    .split(',')
    .filter((p) => p.trimStart().startsWith('v1='))
    .map((p) => p.trim().slice(3));

  if (isNaN(timestamp) || signatures.length === 0) return false;

  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > TOLERANCE_SECONDS) return false;

  const encoder = new TextEncoder();
  const bodyText = new TextDecoder().decode(rawBody);
  const signedPayload = `${timestamp}.${bodyText}`;

  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const signatureBytes = await crypto.subtle.sign(
    'HMAC',
    keyMaterial,
    encoder.encode(signedPayload),
  );

  const expectedSig = Array.from(new Uint8Array(signatureBytes))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  return signatures.some((sig) => sig === expectedSig);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const sigHeader = request.headers.get(STRIPE_SIGNATURE_HEADER);
    if (!sigHeader) {
      return new Response('Missing signature', { status: 400 });
    }

    const rawBody = await request.arrayBuffer();

    const valid = await verifyStripeSignature(
      rawBody,
      sigHeader,
      env.STRIPE_WEBHOOK_SECRET,
    );
    if (!valid) {
      return new Response('Invalid signature', { status: 400 });
    }

    let event: {
      id: string;
      type: string;
      livemode: boolean;
      created: number;
    };
    try {
      const bodyText = new TextDecoder().decode(rawBody);
      event = JSON.parse(bodyText);
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    const bodyText = new TextDecoder().decode(rawBody);

    // Atomic deduplication — silently ignores duplicate event IDs
    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO stripe_events (id, type, livemode, created_at, payload)
       VALUES (?, ?, ?, ?, ?)`,
    )
      .bind(
        event.id,
        event.type,
        event.livemode ? 1 : 0,
        event.created,
        bodyText,
      )
      .run();

    if (result.meta.rows_written === 0) {
      // Duplicate — already seen this event, acknowledge immediately
      return new Response('OK (duplicate)', { status: 200 });
    }

    // Enqueue for async processing to avoid timeout on slow handlers
    await env.PAYMENT_EVENTS_QUEUE.send({
      eventId: event.id,
      eventType: event.type,
      payload: bodyText,
    });

    return new Response('OK', { status: 200 });
  },
};
```

---

## Section 3 — Queue Consumer

```typescript
// src/stripe-event-consumer.ts
import { D1Database } from '@cloudflare/workers-types';
import type { StripeQueueMessage } from './stripe-webhook';

export interface ConsumerEnv {
  DB: D1Database;
}

const HANDLERS: Record<string, (payload: unknown, env: ConsumerEnv) => Promise<void>> = {
  'charge.succeeded': handleChargeSucceeded,
  'customer.subscription.deleted': handleSubscriptionDeleted,
  // add more handlers here
};

async function handleChargeSucceeded(payload: unknown, env: ConsumerEnv): Promise<void> {
  const charge = (payload as { data: { object: { id: string; amount: number } } }).data.object;
  await env.DB.prepare(
    `UPDATE stripe_events SET processed_at = unixepoch() WHERE id = ?`,
  ).bind(charge.id).run();
  // business logic: fulfill order, send receipt, etc.
}

async function handleSubscriptionDeleted(payload: unknown, _env: ConsumerEnv): Promise<void> {
  const sub = (payload as { data: { object: { id: string } } }).data.object;
  console.log('Subscription deleted:', sub.id);
  // business logic: revoke access, send churn email, etc.
}

export default {
  async queue(
    batch: MessageBatch<{ eventId: string; eventType: string; payload: string }>,
    env: ConsumerEnv,
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { eventId, eventType, payload } = msg.body;
      const handler = HANDLERS[eventType];
      if (handler) {
        try {
          await handler(JSON.parse(payload), env);
          await env.DB.prepare(
            `UPDATE stripe_events SET processed_at = unixepoch() WHERE id = ?`,
          ).bind(eventId).run();
        } catch (err) {
          console.error(`Failed to process ${eventId}:`, err);
          msg.retry();
          continue;
        }
      } else {
        // Mark unhandled events as processed so they don't block the queue
        await env.DB.prepare(
          `UPDATE stripe_events SET processed_at = unixepoch() WHERE id = ?`,
        ).bind(eventId).run();
      }
      msg.ack();
    }
  },
};
```

---

## Anti-patterns

- **Parsing body before signature verification** — Always read the raw `ArrayBuffer` first. Parsing JSON before verifying the HMAC opens the door to payload tampering.
- **Using `INSERT OR REPLACE`** — This deletes and re-inserts the row, resetting `processed_at` and losing processing state. Use `INSERT OR IGNORE` instead.
- **Synchronous processing inside the webhook handler** — If your handler takes >30s, Stripe marks the delivery failed and retries. Always enqueue and return 200 immediately.
- **Comparing HMAC signatures with `===` without constant-time check** — For signatures derived from user-controlled input, use a timing-safe comparison. Stripe signatures are from the header, so direct string comparison is acceptable here, but be aware of the tradeoff.

---

## Gotchas

- Stripe includes multiple `v1=` signature entries when you roll your webhook secret; validate against ALL of them.
- The tolerance window (`300s`) must account for clock drift between your Worker and Stripe's servers.
- `result.meta.rows_written` is `0` when `INSERT OR IGNORE` skips a duplicate row — check this field, not `changes`.
- D1 `unixepoch()` is SQLite built-in; works in D1 without extension loading.
- Workers Queues `send()` is not transactional with D1 — if the queue send fails after a successful insert, the event stays in D1 with `processed_at = NULL` and will be re-sent on the next Stripe retry (which is fine, since the insert will be ignored on retry).

---

## Verification

```bash
# Apply migration
npx wrangler d1 execute example project-db --file migrations/0001_stripe_events.sql

# Send a test webhook via Stripe CLI
stripe listen --forward-to https://your-worker.workers.dev/webhooks/stripe
stripe trigger payment_intent.succeeded

# Confirm event inserted once (rows = 1)
npx wrangler d1 execute example project-db --command \
  "SELECT id, type, processed_at FROM stripe_events ORDER BY inserted_epoch DESC LIMIT 5;"

# Trigger same event again to confirm deduplication (rows still = 1)
stripe trigger payment_intent.succeeded --stripe-event-id evt_TEST_REPLACE_WITH_REAL_ID
```

---

## Related

- `stripe-subscription-lifecycle-workers-kv.md`
- `workers-payment-retry-exponential-backoff-queues.md`

---

## Sources

- Stripe Webhook Signatures — https://stripe.com/docs/webhooks/signatures
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Workers Queues — https://developers.cloudflare.com/queues/
- Web Crypto API — https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
