# Priority Inversion Prevention — Workers Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers Queues consumer processes messages from a single queue.  High-
priority messages (e.g., payment confirmations, security alerts) are published alongside
low-priority messages (e.g., bulk exports, analytics ingestion).  Under load, the queue
grows faster than the consumer can drain it.  Low-priority messages that arrived earlier
block high-priority messages that arrived later, causing **priority inversion**: the
system appears to honour FIFO order while violating the intended business priority.

Payment confirmations are delayed behind bulk CSV exports.  Security alert notifications
arrive minutes after the triggering event.  SLA penalties follow.

---

## Context

Cloudflare Queues does not expose per-message priority natively (as of 2026) — it is a
standard FIFO queue per queue name.  The standard remedy is **queue-per-priority**:
dedicate one queue per priority tier and give each its own consumer.  The consumer
Worker is bound to all queues; Cloudflare invokes it once per batch per queue.  Rate
controls and concurrency limits per queue provide the isolation.

Key design decisions:
- **Number of priority tiers** — two (high/low) is almost always sufficient; three tiers
  add operational complexity for marginal gain.
- **Separate consumer Workers vs one multi-queue Worker** — one Worker with multiple
  queue bindings is simpler; separate Workers allow independent scaling limits.
- **Starvation prevention** — the high-priority queue drains unlimited; the low-priority
  queue is consumed only when the high-priority queue is empty or below a depth
  threshold.  Implement this at the producer or via a coordinator DO.

---

## Queue-Per-Priority Wrangler Configuration

```toml
# wrangler.toml

[[queues.producers]]
queue = "notifications-high"
binding = "QUEUE_HIGH"

[[queues.producers]]
queue = "notifications-low"
binding = "QUEUE_LOW"

[[queues.consumers]]
queue = "notifications-high"
max_batch_size = 10
max_batch_timeout = 1   # low latency for high priority
max_retries = 3
dead_letter_queue = "notifications-dlq"

[[queues.consumers]]
queue = "notifications-low"
max_batch_size = 100
max_batch_timeout = 30  # allow larger batches for efficiency
max_retries = 2
dead_letter_queue = "notifications-dlq"
```

---

## Priority Routing at Publish Time

```typescript
// src/lib/priority-publisher.ts

export type Priority = 'high' | 'low';

export interface NotificationJob {
  userId: string;
  type: 'payment_confirmed' | 'security_alert' | 'newsletter' | 'bulk_export';
  payload: unknown;
}

export interface PublisherEnv {
  QUEUE_HIGH: Queue<NotificationJob>;
  QUEUE_LOW: Queue<NotificationJob>;
}

/** Business-rule mapping: which job types are high priority? */
const HIGH_PRIORITY_TYPES = new Set<NotificationJob['type']>([
  'payment_confirmed',
  'security_alert',
]);

export function classifyPriority(job: NotificationJob): Priority {
  return HIGH_PRIORITY_TYPES.has(job.type) ? 'high' : 'low';
}

/**
 * Routes a job to the correct priority queue.
 * Returns the queue tier selected — useful for logging.
 */
export async function publishWithPriority(
  job: NotificationJob,
  env: PublisherEnv,
  opts?: QueueSendOptions,
): Promise<Priority> {
  const tier = classifyPriority(job);
  const queue = tier === 'high' ? env.QUEUE_HIGH : env.QUEUE_LOW;
  await queue.send(job, opts);
  return tier;
}

/** Batch publish — groups by priority tier and sends in two batch calls */
export async function publishBatchWithPriority(
  jobs: NotificationJob[],
  env: PublisherEnv,
): Promise<Record<Priority, number>> {
  const high = jobs.filter(j => classifyPriority(j) === 'high');
  const low  = jobs.filter(j => classifyPriority(j) === 'low');

  await Promise.all([
    high.length > 0 ? env.QUEUE_HIGH.sendBatch(high.map(body => ({ body }))) : undefined,
    low.length  > 0 ? env.QUEUE_LOW.sendBatch(low.map(body => ({ body })))  : undefined,
  ]);

  return { high: high.length, low: low.length };
}
```

---

## Consumer Worker (single Worker, multi-queue binding)

```typescript
// src/workers/notification-consumer.ts

export interface Env {
  DB: D1Database;
}

export interface NotificationJob {
  userId: string;
  type: string;
  payload: unknown;
}

export default {
  /**
   * `queue.name` tells us which queue this batch is from.
   * High-priority batches must complete in < 10 s; low-priority in < 30 s.
   */
  async queue(
    batch: MessageBatch<NotificationJob>,
    env: Env,
  ): Promise<void> {
    const isHighPriority = batch.queue === 'notifications-high';
    const batchDeadlineMs = Date.now() + (isHighPriority ? 10_000 : 28_000);

    console.info('Processing batch', {
      queue: batch.queue,
      count: batch.messages.length,
      priority: isHighPriority ? 'high' : 'low',
    });

    for (const msg of batch.messages) {
      if (Date.now() > batchDeadlineMs) {
        // Requeue remaining messages — do not ACK
        console.warn('Batch deadline reached; deferring remaining messages');
        break;
      }

      try {
        await processNotification(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Failed to process notification', {
          type: msg.body.type,
          error: String(err),
        });
        msg.retry({ delaySeconds: isHighPriority ? 5 : 30 });
      }
    }
  },
};

async function processNotification(
  job: NotificationJob,
  env: Env,
): Promise<void> {
  await env.DB
    .prepare('INSERT INTO notification_log (user_id, type, processed_at) VALUES (?, ?, ?)')
    .bind(job.userId, job.type, new Date().toISOString())
    .run();
  // actual dispatch logic omitted
}
```

---

## Starvation Prevention via Coordinator Durable Object

```typescript
// src/do/priority-coordinator.ts
// Tracks high-queue depth; pauses low-priority consumer when high queue is backlogged.

export interface CoordinatorState {
  highQueueDepth: number;
  lastUpdated: string;
}

export class PriorityCoordinator implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/report-depth' && req.method === 'POST') {
      const { depth } = await req.json() as { depth: number };
      await this.state.storage.put<CoordinatorState>('state', {
        highQueueDepth: depth,
        lastUpdated: new Date().toISOString(),
      });
      return new Response('ok');
    }

    if (url.pathname === '/should-low-run' && req.method === 'GET') {
      const s = await this.state.storage.get<CoordinatorState>('state');
      const depth = s?.highQueueDepth ?? 0;
      // Pause low-priority processing when high queue has > 50 messages
      const allowed = depth < 50;
      return new Response(JSON.stringify({ allowed, highQueueDepth: depth }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

```typescript
// Low-priority consumer polls coordinator before processing
export default {
  async queue(batch: MessageBatch<NotificationJob>, env: Env & { COORDINATOR: DurableObjectNamespace }): Promise<void> {
    const id = env.COORDINATOR.idFromName('global');
    const stub = env.COORDINATOR.get(id);
    const check = await stub.fetch(new Request('https://do/should-low-run'));
    const { allowed } = await check.json() as { allowed: boolean };

    if (!allowed) {
      console.info('Low-priority processing paused: high queue is backlogged');
      // Returning without acking causes Queues to redeliver; use retry with delay
      for (const msg of batch.messages) {
        msg.retry({ delaySeconds: 60 });
      }
      return;
    }

    // Normal processing
    for (const msg of batch.messages) {
      try {
        await processNotification(msg.body, env as Env);
        msg.ack();
      } catch {
        msg.retry();
      }
    }
  },
};
```

---

## Monitoring Queue Depths with Analytics Engine

```typescript
// src/lib/queue-depth-reporter.ts
// Call from a scheduled Worker (cron trigger) to record queue depth metrics

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}

export async function reportQueueDepths(env: Env): Promise<void> {
  const queues = ['notifications-high', 'notifications-low'];

  for (const queueName of queues) {
    // Cloudflare does not expose queue depth via a simple API in 2026;
    // use the number of messages acknowledged vs produced from Logpush
    // as a proxy, or emit depth as part of each consumer batch run.
    env.ANALYTICS.writeDataPoint({
      blobs: [queueName],
      doubles: [0], // replace with actual depth when API is available
      indexes: [queueName],
    });
  }
}
```

---

## Anti-patterns

- **Single queue, priority in the message body** — the consumer must read every message
  to know its priority; under load, low-priority messages still block high-priority ones
  because Queues delivers in FIFO order per queue.
- **Priority field with post-pull reordering** — pulling a full batch, sorting in
  memory, then processing does not help: the next batch may contain higher-priority
  messages that have not been delivered yet.
- **Too many priority tiers** — four or more tiers multiply operational overhead
  (DLQ per queue, consumer per queue, monitoring per queue) for minimal gain; two tiers
  cover 95% of real-world use cases.
- **Not setting DLQ on the high-priority queue** — failed high-priority messages that
  exhaust retries are silently dropped without a DLQ; always configure one.
- **Ignoring starvation** — if the high-priority queue never empties, low-priority
  messages age out or pile up indefinitely; always implement a starvation guard.

---

## Gotchas

- **Cloudflare Queues consumer concurrency** — as of 2026, consumer concurrency is
  controlled at the account level, not per-queue; a spike in high-priority messages
  shares the concurrency pool with low-priority consumers.  Use separate consumer
  Workers bound to separate queues to leverage independent scaling.
- **`batch.queue`** is the queue name string — use it to branch logic in a single
  consumer Worker rather than duplicating the whole Worker.
- **`msg.retry({ delaySeconds })` minimum delay** — the minimum retry delay is 0 s
  and maximum is 43_200 (12 h); for starvation prevention delays < 60 s are typical.
- **Queue depth visibility** — Cloudflare does not currently expose a real-time queue
  depth API; instrument your consumers to emit depth estimates via Analytics Engine.
- **DLQ is also a queue** — a dead-letter queue on the high-priority queue is itself
  a Cloudflare Queue and needs its own consumer and monitoring.

---

## Verification

```bash
# 1. Publish 100 low-priority messages, then 10 high-priority messages
# 2. Observe consumer logs — high-priority batch must start before low-priority
#    batch is fully drained.
# 3. Kill the consumer, publish 200 low + 10 high, restart.
#    High messages must appear first in processed_at order in DB.

# Query D1 to verify ordering:
# SELECT type, processed_at FROM notification_log ORDER BY processed_at ASC LIMIT 20;
# Expect: security_alert / payment_confirmed rows appear before newsletter / bulk_export rows.
```

---

## Related

- `priority-queue-workers-queues.md` — priority queue implementation patterns
- `dead-letter-queue-pattern.md` — handling exhausted retries across all tiers
- `fan-out-queues-workers.md` — routing messages to multiple downstream consumers
- `adaptive-backpressure-workers-queues.md` — flow control under sustained load

---

## Sources

- Cloudflare Queues documentation — consumer configuration
  https://developers.cloudflare.com/queues/
- "Priority Inversion" — Wikipedia
  https://en.wikipedia.org/wiki/Priority_inversion
- "Release It!" ch. 9 — bulkheads and backpressure under load
  Michael T. Nygard, 2nd ed.
