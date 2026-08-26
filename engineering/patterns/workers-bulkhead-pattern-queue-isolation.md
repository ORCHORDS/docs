# Bulkhead Pattern: Fault Isolation with Queue-per-Tenant in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A single Cloudflare Queue shared across tenants or service tiers means one noisy tenant can exhaust the queue's throughput, delaying or dropping messages from every other tenant. A non-critical background job — bulk email export, analytics aggregation — can crowd out a critical real-time payment notification sitting in the same queue.

You need a hard isolation boundary so that a flood in one lane cannot spill into another.

---

## Context

Cloudflare Queues deliver at-least-once semantics and apply back-pressure via per-queue throughput limits. When a consumer Worker is overloaded, the queue accumulates a backlog. If all tenants share one queue, backlog from tenant A delays tenant B even though tenant B's load is nominal.

The Bulkhead pattern (from ship hull design) partitions capacity into independent compartments. A breach in one compartment does not sink the ship.

Applicable when:
- Multi-tenant SaaS where SLA tiers differ (enterprise vs. free).
- Mixed criticality workloads (payment events vs. analytics pings).
- Regulated environments requiring data isolation at the transport layer.

---

## Solution

Provision a dedicated Queue binding per bulkhead. Route incoming work to the correct queue at the edge, before any processing occurs. Each queue has its own consumer Worker with independent concurrency and retry settings.

```toml
# wrangler.toml
name = "router"

[[queues.producers]]
binding = "QUEUE_CRITICAL"
queue = "tenant-critical-events"

[[queues.producers]]
binding = "QUEUE_STANDARD"
queue = "tenant-standard-events"

[[queues.producers]]
binding = "QUEUE_BULK"
queue = "tenant-bulk-events"
```

```typescript
// router/src/index.ts
import { Env } from './types';

export interface Env {
  QUEUE_CRITICAL: Queue;
  QUEUE_STANDARD: Queue;
  QUEUE_BULK: Queue;
  KV_QUOTA: KVNamespace;
}

type BulkheadTier = 'critical' | 'standard' | 'bulk';

interface IncomingEvent {
  tenantId: string;
  eventType: string;
  payload: unknown;
}

function resolveTier(event: IncomingEvent): BulkheadTier {
  // Billing tier stored in event metadata — set by the API layer
  if (event.eventType.startsWith('payment.') || event.eventType.startsWith('auth.')) {
    return 'critical';
  }
  if (event.eventType.startsWith('notification.')) {
    return 'standard';
  }
  return 'bulk';
}

const QUOTA_WINDOW_SECONDS = 60;
const TIER_QUOTAS: Record<BulkheadTier, number> = {
  critical: 10_000,
  standard: 2_000,
  bulk: 500,
};

async function checkQuota(
  kv: KVNamespace,
  tenantId: string,
  tier: BulkheadTier,
): Promise<{ allowed: boolean; remaining: number }> {
  const key = `quota:${tenantId}:${tier}:${Math.floor(Date.now() / 1000 / QUOTA_WINDOW_SECONDS)}`;
  const raw = await kv.get(key);
  const current = raw ? parseInt(raw, 10) : 0;
  const limit = TIER_QUOTAS[tier];

  if (current >= limit) {
    return { allowed: false, remaining: 0 };
  }

  // Increment — fire-and-forget, best-effort quota (strong consistency not needed here)
  kv.put(key, String(current + 1), { expirationTtl: QUOTA_WINDOW_SECONDS * 2 });
  return { allowed: true, remaining: limit - current - 1 };
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let event: IncomingEvent;
    try {
      event = await request.json();
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    const tier = resolveTier(event);
    const { allowed, remaining } = await checkQuota(env.KV_QUOTA, event.tenantId, tier);

    if (!allowed) {
      // Bulkhead breach — reject fast, do not enqueue
      console.error(JSON.stringify({
        type: 'bulkhead_breach',
        tenantId: event.tenantId,
        tier,
        eventType: event.eventType,
      }));

      return new Response(
        JSON.stringify({ error: 'quota_exceeded', tier }),
        { status: 429, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const queueMap: Record<BulkheadTier, Queue> = {
      critical: env.QUEUE_CRITICAL,
      standard: env.QUEUE_STANDARD,
      bulk: env.QUEUE_BULK,
    };

    await queueMap[tier].send(event, { contentType: 'json' });

    return new Response(
      JSON.stringify({ queued: true, tier, remaining }),
      { status: 202, headers: { 'Content-Type': 'application/json' } },
    );
  },
};
```

### Consumer Worker (one per bulkhead)

```typescript
// consumer-critical/src/index.ts
export interface Env {
  DB: D1Database;
}

interface QueuedEvent {
  tenantId: string;
  eventType: string;
  payload: unknown;
}

export default {
  async queue(batch: MessageBatch<QueuedEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processEvent(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error(JSON.stringify({
          type: 'consumer_error',
          bulkhead: 'critical',
          tenantId: msg.body.tenantId,
          error: String(err),
        }));
        // Explicit nack — message returns to queue for retry
        msg.retry();
      }
    }
  },
};

async function processEvent(event: QueuedEvent, env: Env): Promise<void> {
  // Domain-specific processing per event type
  await env.DB.prepare(
    'INSERT INTO processed_events (tenant_id, event_type, processed_at) VALUES (?, ?, ?)',
  ).bind(event.tenantId, event.eventType, new Date().toISOString()).run();
}
```

---

## Implementation Details

**Queue provisioning:** Provision queues via Wrangler or the Cloudflare API before deployment. Each queue is independently configurable for delivery delay, max retries, and dead-letter routing.

**Tier resolution logic:** Keep it deterministic and side-effect free. Avoid async lookups in the hot path of `resolveTier`; denormalise the tier into the event at ingestion time if needed.

**Quota window granularity:** A 60-second sliding window approximated via KV key per minute is cheap. For strict sliding windows, use Durable Objects with an in-memory ring buffer.

**Dead-letter queues:** Configure a DLQ for each bulkhead queue. Critical tier DLQ should page on-call; bulk tier DLQ can drain silently with daily alerting.

**Consumer concurrency:** Set `max_concurrency` independently per consumer Worker binding. Critical consumers run more instances; bulk consumers are intentionally throttled.

```toml
# consumer-critical/wrangler.toml
[[queues.consumers]]
queue = "tenant-critical-events"
max_batch_size = 10
max_batch_timeout = 1
max_retries = 5
dead_letter_queue = "tenant-critical-dlq"

# consumer-bulk/wrangler.toml
[[queues.consumers]]
queue = "tenant-bulk-events"
max_batch_size = 100
max_batch_timeout = 30
max_retries = 2
dead_letter_queue = "tenant-bulk-dlq"
```

---

## Anti-patterns

- **Single queue with priority field:** Cloudflare Queues do not support per-message priority ordering. A priority field in the message body is invisible to the queue scheduler.
- **Dynamic queue creation at runtime:** Queues must be pre-provisioned. Do not attempt to create queues on the fly per tenant; use a fixed set of tier queues.
- **Quota enforcement inside the consumer:** By the time a message is dequeued, the resource is already consumed. Enforce quotas at the router/producer boundary.
- **Sharing a DLQ across bulkheads:** A shared DLQ defeats the isolation purpose. Bulkhead breaches in one tier should not mix failure signals with another.

---

## Gotchas

- KV quota counters are eventually consistent across regions. A burst can briefly exceed the quota by the number of concurrent router instances before KV replicates. Accept this ~1–2% overage or use a Durable Object for strict counting.
- Wrangler requires all queue bindings to be declared in `wrangler.toml` before `wrangler deploy`. You cannot bind to a queue that does not exist yet.
- `msg.retry()` without a delay returns the message immediately, potentially causing a tight retry loop. Configure `retry_delay` in the consumer binding.
- Each queue counts against your account's queue limit. Plan your bulkhead count accordingly.

---

## Verification

1. Send 1,000 bulk events and 10 critical events simultaneously to the router.
2. Throttle the bulk consumer to zero throughput.
3. Confirm critical events are processed within SLA; bulk events accumulate in their own queue without affecting critical latency.
4. Trigger quota breach on a bulk tenant and confirm the 429 is returned without any message entering the critical or standard queues.
5. Inspect DLQ message counts in the Cloudflare Dashboard queues view.

---

## Related

- `workers-outbox-pattern-d1-queues.md` — reliable event emission before enqueuing
- `workers-compensating-transaction-pattern.md` — rollback when consumer processing fails
- Cloudflare Queues documentation: consumers, retries, DLQ configuration

---

## Sources

- Release It! — Michael Nygard, Chapter 4: Stability Patterns (Bulkhead)
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Cloudflare Queues consumer configuration: https://developers.cloudflare.com/queues/reference/configuration/
