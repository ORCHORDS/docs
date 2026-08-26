# Fan-Out Pattern: Cloudflare Queues → Multiple Consumer Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A single event (order placed, user signed up, file uploaded) must trigger multiple independent downstream actions: send a confirmation email, update analytics, provision a resource, notify a webhook subscriber. Running all of these synchronously in the originating Worker inflates response time, couples unrelated concerns, and means one slow consumer blocks others. You need reliable, parallel, independently-scalable processing of a single event by multiple consumers.

## Context

**Fan-out** (also called pub/sub broadcast) disperses one message to N independent processing paths. Cloudflare Queues are point-to-point by default — one queue has one consumer Worker. Fan-out is achieved by having a **dispatcher Worker** consume the primary queue and republish the event to N **topic queues**, each bound to its own specialised consumer Worker.

```
                          ┌──────────────────────────────────────────────────────┐
  Producer Worker         │              Dispatcher Worker                        │
  (API handler) ──────►  EVENTS queue ──► read batch ──┬──► EMAIL queue ──► EmailWorker
                          │                              ├──► ANALYTICS queue ──► AnalyticsWorker
                          │                              ├──► WEBHOOK queue ──► WebhookWorker
                          │                              └──► AUDIT queue ──► AuditWorker
                          └──────────────────────────────────────────────────────┘
```

Each leaf consumer is independently retried, independently scaled, and independently monitored. A failure in `EmailWorker` does not block `AnalyticsWorker`.

## Section 1 — Defining the Message Schema

Use a discriminated union so consumers can ignore event types they do not handle:

```typescript
// schema.ts
export type EventType = 'order.placed' | 'user.signed_up' | 'file.uploaded';

export interface BaseEvent {
  eventId:   string; // UUID for deduplication
  eventType: EventType;
  timestamp: string; // ISO-8601
  version:   number; // schema version
}

export interface OrderPlacedEvent extends BaseEvent {
  eventType: 'order.placed';
  payload: {
    orderId:    string;
    userId:     string;
    totalCents: number;
    currency:   string;
    lineItems:  Array<{ sku: string; qty: number; unitCents: number }>;
  };
}

export interface UserSignedUpEvent extends BaseEvent {
  eventType: 'user.signed_up';
  payload: {
    userId:   string;
    email:    string;
    planId:   string;
  };
}

export type AppEvent = OrderPlacedEvent | UserSignedUpEvent;
```

## Section 2 — Producer: Enqueue from an API Worker

```typescript
// api-worker.ts
import type { AppEvent } from './schema';

export interface Env {
  EVENTS: Queue<AppEvent>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{ userId: string; email: string; planId: string }>();

    const event: AppEvent = {
      eventId:   crypto.randomUUID(),
      eventType: 'user.signed_up',
      timestamp: new Date().toISOString(),
      version:   1,
      payload: {
        userId:  body.userId,
        email:   body.email,
        planId:  body.planId,
      },
    };

    // Non-blocking — the response returns immediately
    await env.EVENTS.send(event, { contentType: 'json' });

    return Response.json({ status: 'accepted', eventId: event.eventId }, { status: 202 });
  },
};
```

## Section 3 — Dispatcher: Fan-Out Worker

```typescript
// dispatcher.ts
import type { AppEvent }         from './schema';

export interface Env {
  EMAIL_QUEUE:     Queue<AppEvent>;
  ANALYTICS_QUEUE: Queue<AppEvent>;
  WEBHOOK_QUEUE:   Queue<AppEvent>;
  AUDIT_QUEUE:     Queue<AppEvent>;
}

// Routing table: event type → which queues should receive it
const FANOUT_MAP: Record<string, Array<keyof Env>> = {
  'user.signed_up': ['EMAIL_QUEUE', 'ANALYTICS_QUEUE', 'WEBHOOK_QUEUE', 'AUDIT_QUEUE'],
  'order.placed':   ['EMAIL_QUEUE', 'ANALYTICS_QUEUE', 'AUDIT_QUEUE'],
  'file.uploaded':  ['ANALYTICS_QUEUE', 'AUDIT_QUEUE'],
};

export default {
  async queue(batch: MessageBatch<AppEvent>, env: Env): Promise<void> {
    // Group by event type for batch fanout
    const byType = new Map<string, AppEvent[]>();
    for (const msg of batch.messages) {
      const eventType = msg.body.eventType;
      if (!byType.has(eventType)) byType.set(eventType, []);
      byType.get(eventType)!.push(msg.body);
    }

    const sends: Promise<void>[] = [];

    for (const [eventType, events] of byType) {
      const targets = FANOUT_MAP[eventType] ?? [];
      for (const queueKey of targets) {
        const targetQueue = env[queueKey] as Queue<AppEvent>;
        // sendBatch is more efficient than individual sends
        sends.push(
          targetQueue.sendBatch(
            events.map(e => ({ body: e, contentType: 'json' }))
          )
        );
      }
    }

    // Wait for all fan-out sends; if any fail, the batch is retried
    await Promise.all(sends);

    // Acknowledge all messages — dispatcher's job is only routing
    batch.ackAll();
  },
};
```

## Section 4 — Consumer Workers

Each consumer only handles its concern:

```typescript
// email-consumer.ts
import type { AppEvent, UserSignedUpEvent } from './schema';

export interface Env {
  RESEND_API_KEY: string; // wrangler secret
}

export default {
  async queue(batch: MessageBatch<AppEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await handleEmail(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error(JSON.stringify({ event: 'email_send_failed', error: String(err), body: msg.body }));
        // nack causes Queues to retry with backoff
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function handleEmail(event: AppEvent, env: Env): Promise<void> {
  if (event.eventType !== 'user.signed_up') return; // ignore unrelated types

  const e = event as UserSignedUpEvent;

  const res = await fetch('https://api.resend.com/emails', {
    method:  'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type':  'application/json',
    },
    body: JSON.stringify({
      from:    'welcome@example.com',
      to:      e.payload.email,
      subject: 'Welcome!',
      html:    `<p>Hi, your account on plan ${e.payload.planId} is ready.</p>`,
    }),
  });

  if (!res.ok) throw new Error(`Resend API error: ${res.status} ${await res.text()}`);
}
```

```typescript
// analytics-consumer.ts
import type { AppEvent } from './schema';

export interface Env {
  ANALYTICS_DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<AppEvent>, env: Env): Promise<void> {
    // Batch insert for efficiency
    const rows = batch.messages.map(m => m.body);

    const stmt = env.ANALYTICS_DB.prepare(
      `INSERT OR IGNORE INTO events (event_id, event_type, payload, created_at)
       VALUES (?, ?, ?, ?)`
    );

    const inserts = rows.map(e =>
      stmt.bind(e.eventId, e.eventType, JSON.stringify(e.payload), e.timestamp)
    );

    await env.ANALYTICS_DB.batch(inserts);
    batch.ackAll();
  },
};
```

## wrangler.toml (Abridged)

```toml
# wrangler.toml

# Primary ingest queue
[[queues.producers]]
queue   = "events"
binding = "EVENTS"

# Dispatcher consumer
[[queues.consumers]]
queue           = "events"
max_batch_size  = 100
max_batch_timeout = 5
max_retries     = 3

# Topic queues (producers side, for the dispatcher)
[[queues.producers]]
queue   = "email-queue"
binding = "EMAIL_QUEUE"

[[queues.producers]]
queue   = "analytics-queue"
binding = "ANALYTICS_QUEUE"

# Consumer bindings live in each consumer worker's wrangler.toml
```

## Anti-patterns

**Fan-out inside the producer Worker synchronously.** Sending to 4 queues inside the API request handler before returning adds latency proportional to the slowest queue send and couples the API response to routing success.

**Single shared queue with consumer-side filtering.** If all consumers read from one queue, each consumer processes every message and must filter most out. This wastes compute and can cause consumers to block each other's retry policies.

**Unbounded fan-out targets.** Adding 50 topic queues from a single dispatcher creates 50 concurrent `sendBatch` calls. Cap fan-out depth at ~10 and use a two-level hierarchy (dispatcher → category dispatchers → leaf consumers) for larger topologies.

**Ignoring `sendBatch` errors silently.** If any fan-out send fails and you call `batch.ackAll()` anyway, the event is permanently lost. Let `Promise.all` throw; Queues will redeliver the original batch to the dispatcher.

## Gotchas

- **Cloudflare Queues does not support native pub/sub fan-out** — the dispatcher pattern is the approved workaround as of 2026.
- **`msg.retry({ delaySeconds })` requires** `compatibility_date` ≥ `2023-03-01`.
- **`sendBatch` has a 256 KB total body limit** per call. For events with large payloads, store the payload in R2 and send only the reference in the queue message.
- **Queue ordering is best-effort** — do not rely on per-user ordering across fan-out legs. If ordered processing matters (e.g., audit trail must be sequential), use the event's `timestamp` and re-order on read.
- **Dead-letter queues are separate** — configure `dead_letter_queue` on each consumer so messages that exhaust retries are captured. See `dead-letter-queue-pattern.md`.

## Verification

```bash
# Trigger a test event
curl -X POST https://api.example.com/signup \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","email":"test@example.com","planId":"pro"}'

# Tail logs from all workers
wrangler tail api-worker     --format pretty
wrangler tail dispatcher     --format pretty
wrangler tail email-consumer --format pretty

# Check analytics D1 table
wrangler d1 execute my-db --command "SELECT * FROM events ORDER BY created_at DESC LIMIT 5;"
```

## Related

- `dead-letter-queue-pattern.md` — capturing exhausted-retry messages
- `feature-cookbook-queues.md` — general queue usage patterns
- `queue-system-design.md` — queue depth, throughput, and sizing
- `event-driven-architecture.md` — broader event-driven design
- `idempotency-key-pattern-workers-d1.md` — deduplicating redelivered fan-out messages

## Sources

- Cloudflare Queues documentation — developers.cloudflare.com/queues/
- Enterprise Integration Patterns, Hohpe & Woolf — "Publish-Subscribe Channel"
- Cloudflare blog, "Announcing Cloudflare Queues" — blog.cloudflare.com
