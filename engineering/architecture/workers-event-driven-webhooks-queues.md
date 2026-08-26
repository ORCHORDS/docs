# Event-Driven Webhook Delivery Architecture with Workers + Queues

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You emit events from your API (order created, payment completed, user updated) and need to deliver them as HTTP webhooks to multiple subscriber endpoints. Synchronous delivery blocks your API response, one slow subscriber delays all others, and a subscriber outage drops events. You need durable, fan-out, retrying webhook delivery with circuit breakers — without a dedicated webhook SaaS.

## Context

The architecture uses three Workers and two Queue bindings:

1. **Producer Worker** — your main API. Enqueues a `DomainEvent` to an *ingestion queue* after committing to D1.
2. **Fan-out Worker** (Queue consumer on the ingestion queue) — looks up subscribers in D1 and enqueues one `DeliveryJob` per subscriber to a *delivery queue*.
3. **Delivery Worker** (Queue consumer on the delivery queue) — POSTs the event to each subscriber's endpoint, logs the result, and implements exponential backoff + circuit breaker.

## Solution

### 1. Types

```typescript
// src/webhooks/types.ts

export interface DomainEvent {
  eventId: string;
  type: string;                       // e.g. 'order.created'
  payload: Record<string, unknown>;
  occurredAt: number;                 // unix ms
}

export interface Subscriber {
  id: string;
  url: string;
  secret: string;                     // HMAC signing key
  eventTypes: string[];               // glob patterns, e.g. ['order.*', 'payment.completed']
  status: 'active' | 'paused' | 'circuit_open';
}

export interface DeliveryJob {
  jobId: string;
  eventId: string;
  subscriberId: string;
  subscriberUrl: string;
  subscriberSecret: string;
  eventType: string;
  payload: Record<string, unknown>;
  occurredAt: number;
  attempt: number;                    // 1-based
}

export interface DeliveryLog {
  jobId: string;
  eventId: string;
  subscriberId: string;
  attempt: number;
  statusCode: number | null;          // null = network error
  success: boolean;
  deliveredAt: number;
  durationMs: number;
  errorMessage: string | null;
}
```

### 2. Producer Worker — enqueue on event

```typescript
// src/producer/worker.ts
import type { DomainEvent } from '../webhooks/types';

export interface Env {
  DB: D1Database;
  WEBHOOK_INGESTION: Queue<DomainEvent>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Example: create an order
    if (request.method === 'POST' && new URL(request.url).pathname === '/orders') {
      const body = await request.json<{ customerId: string; amount: number }>();
      const orderId = crypto.randomUUID();

      await env.DB
        .prepare(`INSERT INTO orders (id, customer_id, amount, created_at) VALUES (?, ?, ?, ?)`)
        .bind(orderId, body.customerId, body.amount, Date.now())
        .run();

      // Enqueue event — non-blocking from the client's perspective
      const event: DomainEvent = {
        eventId: crypto.randomUUID(),
        type: 'order.created',
        payload: { orderId, customerId: body.customerId, amount: body.amount },
        occurredAt: Date.now(),
      };
      await env.WEBHOOK_INGESTION.send(event);

      return Response.json({ orderId }, { status: 201 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

### 3. Fan-out Worker — one job per subscriber

```typescript
// src/webhooks/fanout-worker.ts
import type { DomainEvent, Subscriber, DeliveryJob } from './types';

export interface Env {
  DB: D1Database;
  WEBHOOK_DELIVERY: Queue<DeliveryJob>;
}

function matchesPattern(eventType: string, patterns: string[]): boolean {
  return patterns.some(pattern => {
    const regex = new RegExp('^' + pattern.replace('.', '\\.').replace('*', '.*') + '$');
    return regex.test(eventType);
  });
}

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      // Find active subscribers matching this event type
      const { results: subscribers } = await env.DB
        .prepare(
          `SELECT id, url, secret, event_types, status
           FROM webhook_subscribers
           WHERE status = 'active'`,
        )
        .all<{ id: string; url: string; secret: string; event_types: string; status: string }>();

      const matched = subscribers.filter(s => {
        const patterns: string[] = JSON.parse(s.event_types);
        return matchesPattern(event.type, patterns);
      });

      if (matched.length === 0) {
        msg.ack();
        continue;
      }

      // Enqueue one delivery job per subscriber
      await Promise.all(
        matched.map(sub =>
          env.WEBHOOK_DELIVERY.send({
            jobId: crypto.randomUUID(),
            eventId: event.eventId,
            subscriberId: sub.id,
            subscriberUrl: sub.url,
            subscriberSecret: sub.secret,
            eventType: event.type,
            payload: event.payload,
            occurredAt: event.occurredAt,
            attempt: 1,
          } satisfies DeliveryJob),
        ),
      );

      msg.ack();
    }
  },
};
```

### 4. Delivery Worker — HTTP delivery with retry and circuit breaker

```typescript
// src/webhooks/delivery-worker.ts
import type { DeliveryJob, DeliveryLog } from './types';

export interface Env {
  DB: D1Database;
  WEBHOOK_DELIVERY: Queue<DeliveryJob>;
}

const MAX_ATTEMPTS    = 5;
const CIRCUIT_THRESHOLD = 5;  // consecutive failures before opening circuit

async function hmacSignature(secret: string, body: string): Promise<string> {
  const key  = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig  = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  return 'sha256=' + [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function deliverWebhook(
  job: DeliveryJob,
): Promise<{ statusCode: number | null; durationMs: number; error: string | null }> {
  const bodyStr = JSON.stringify({
    id:         job.eventId,
    type:       job.eventType,
    payload:    job.payload,
    occurred_at: job.occurredAt,
  });

  const signature = await hmacSignature(job.subscriberSecret, bodyStr);
  const start     = Date.now();

  try {
    const resp = await fetch(job.subscriberUrl, {
      method:  'POST',
      headers: {
        'Content-Type':   'application/json',
        'X-Webhook-Id':   job.jobId,
        'X-Webhook-Sig':  signature,
        'X-Attempt':      String(job.attempt),
      },
      body:    bodyStr,
      signal:  AbortSignal.timeout(10_000), // 10 s per attempt
    });
    return { statusCode: resp.status, durationMs: Date.now() - start, error: null };
  } catch (err: any) {
    return { statusCode: null, durationMs: Date.now() - start, error: err.message };
  }
}

async function checkAndUpdateCircuitBreaker(
  subscriberId: string,
  success: boolean,
  db: D1Database,
): Promise<void> {
  if (success) {
    // Reset failure counter on success
    await db
      .prepare(`UPDATE webhook_subscribers SET consecutive_failures = 0 WHERE id = ?`)
      .bind(subscriberId)
      .run();
    return;
  }

  // Increment failure counter; open circuit if threshold exceeded
  await db
    .prepare(
      `UPDATE webhook_subscribers
       SET consecutive_failures = consecutive_failures + 1,
           status = CASE
             WHEN consecutive_failures + 1 >= ? THEN 'circuit_open'
             ELSE status
           END
       WHERE id = ?`,
    )
    .bind(CIRCUIT_THRESHOLD, subscriberId)
    .run();
}

export default {
  async queue(batch: MessageBatch<DeliveryJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      // Check if subscriber circuit is open (skip delivery)
      const sub = await env.DB
        .prepare(`SELECT status FROM webhook_subscribers WHERE id = ?`)
        .bind(job.subscriberId)
        .first<{ status: string }>();

      if (!sub || sub.status === 'circuit_open') {
        // Log as skipped and ack — no retry
        await logDelivery(job, null, false, 0, 'Circuit open — delivery skipped', env.DB);
        msg.ack();
        continue;
      }

      const { statusCode, durationMs, error } = await deliverWebhook(job);
      const success = statusCode !== null && statusCode >= 200 && statusCode < 300;

      await logDelivery(job, statusCode, success, durationMs, error, env.DB);
      await checkAndUpdateCircuitBreaker(job.subscriberId, success, env.DB);

      if (success) {
        msg.ack();
      } else if (job.attempt >= MAX_ATTEMPTS) {
        // Exhausted retries — ack to prevent infinite loop, alert instead
        console.error(`Webhook delivery permanently failed`, job);
        msg.ack();
      } else {
        // Retry with exponential backoff via Queue's built-in retry delay
        msg.retry({ delaySeconds: Math.pow(2, job.attempt) * 30 }); // 30s, 60s, 120s, 240s
      }
    }
  },
};

async function logDelivery(
  job: DeliveryJob,
  statusCode: number | null,
  success: boolean,
  durationMs: number,
  errorMessage: string | null,
  db: D1Database,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO webhook_delivery_log
         (job_id, event_id, subscriber_id, attempt, status_code, success, delivered_at, duration_ms, error_message)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      job.jobId,
      job.eventId,
      job.subscriberId,
      job.attempt,
      statusCode,
      success ? 1 : 0,
      Date.now(),
      durationMs,
      errorMessage,
    )
    .run();
}
```

### 5. D1 schema

```sql
CREATE TABLE webhook_subscribers (
  id                   TEXT PRIMARY KEY,
  url                  TEXT NOT NULL,
  secret               TEXT NOT NULL,
  event_types          TEXT NOT NULL DEFAULT '[]',  -- JSON array of glob patterns
  status               TEXT NOT NULL DEFAULT 'active', -- active | paused | circuit_open
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  created_at           INTEGER NOT NULL
);

CREATE TABLE webhook_delivery_log (
  job_id          TEXT PRIMARY KEY,
  event_id        TEXT NOT NULL,
  subscriber_id   TEXT NOT NULL,
  attempt         INTEGER NOT NULL,
  status_code     INTEGER,
  success         INTEGER NOT NULL DEFAULT 0,  -- SQLite boolean
  delivered_at    INTEGER NOT NULL,
  duration_ms     INTEGER NOT NULL,
  error_message   TEXT,
  INDEX idx_delivery_log_subscriber (subscriber_id, delivered_at DESC),
  INDEX idx_delivery_log_event (event_id)
);
```

### 6. wrangler.toml

```toml
[[queues.producers]]
binding = "WEBHOOK_INGESTION"
queue   = "webhook-ingestion"

[[queues.producers]]
binding = "WEBHOOK_DELIVERY"
queue   = "webhook-delivery"

[[queues.consumers]]
queue            = "webhook-ingestion"
max_batch_size   = 100
max_batch_timeout = 5
max_retries      = 3

[[queues.consumers]]
queue            = "webhook-delivery"
max_batch_size   = 10
max_batch_timeout = 1
max_retries      = 0   # We manage retries manually via msg.retry()
```

## Implementation Details

**Circuit breaker state machine**:

| State           | Condition                                    | Effect                              |
|-----------------|----------------------------------------------|-------------------------------------|
| `active`        | `consecutive_failures < CIRCUIT_THRESHOLD`   | Delivery attempted normally         |
| `circuit_open`  | `consecutive_failures >= CIRCUIT_THRESHOLD`  | Delivery skipped; no retries        |
| Reset           | Admin endpoint resets `consecutive_failures` | Status returns to `active`          |

**HMAC signature**: the `X-Webhook-Sig: sha256=<hex>` header allows subscribers to verify the payload was not tampered with. Use `timingSafeEqual` on the subscriber side.

**Retry backoff** (at `MAX_ATTEMPTS = 5`): 30 s, 60 s, 120 s, 240 s — maximum total wait ~7.5 minutes before permanent failure.

**Delivery log retention**: add a scheduled Worker (cron trigger) to purge `webhook_delivery_log` rows older than 30 days:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    await env.DB
      .prepare(`DELETE FROM webhook_delivery_log WHERE delivered_at < ?`)
      .bind(cutoff)
      .run();
  },
};
```

## Anti-patterns

- **Delivering webhooks synchronously in the producer** — one slow subscriber blocks the entire request and can cause timeouts for the API caller.
- **Using a single queue for ingestion and delivery** — fan-out logic must run before delivery; mixing them on one queue prevents independent scaling.
- **No HMAC signing** — subscribers cannot distinguish genuine events from spoofed ones.
- **Retrying indefinitely without a circuit breaker** — a permanently dead subscriber accumulates retries, consumes Queue quota, and floods logs.
- **Storing secrets in event payload** — the delivery job carries the subscriber secret separately; it must never appear in logs or the delivery log table.

## Gotchas

- `msg.retry({ delaySeconds })` requires the queue consumer's `max_retries` to be set high enough (or `0` when you manage retries manually by re-enqueueing). Setting `max_retries = 0` on the delivery queue and calling `msg.retry()` will cause the message to be dead-lettered; manage retry count in the job payload and call `msg.ack()` after max attempts instead.
- `AbortSignal.timeout()` is available in Workers runtime ≥ 2023-03-01 compatibility date.
- `Queue.send()` is best-effort. If the ingestion queue is unavailable at the moment the producer calls `send()`, the event is lost. For critical events add an outbox table in D1 and sync via a scheduled Worker.
- Fan-out to many subscribers (>100) in a single Queue consumer message may hit the 128 subrequest limit per Worker invocation. Batch fan-out or implement iterative pagination.

## Verification

```bash
# Register a subscriber
curl -X POST https://api.example.com/webhooks/subscribers \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://receiver.example.com/hook","secret":"s3cr3t","eventTypes":["order.*"]}'

# Trigger an event
curl -X POST https://api.example.com/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"c1","amount":99.99}'

# Check delivery log
curl https://api.example.com/webhooks/deliveries?subscriberId=<id>

# Reset a circuit-opened subscriber
curl -X POST https://api.example.com/webhooks/subscribers/<id>/reset-circuit
```

## Related

- `workers-cqrs-command-query-separation.md`
- `workers-hexagonal-architecture-ports-adapters.md`
- `workers-multi-tenant-isolation-durable-objects.md`

## Sources

- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare Queues retry & backoff — https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Web Crypto API (HMAC) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
