# Workers Queue Consumer Backpressure Incidents — Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Our order-processing pipeline uses a Cloudflare Queue to decouple the API Worker (producer) from
the fulfilment Worker (consumer). During a Black Friday sale, the queue depth climbed from 200 to
120 000 messages in 11 minutes. The consumer auto-scaled unexpectedly, hammering a third-party
fulfilment API that had a 10 req/s rate limit. Retries on 429 responses caused the queue depth to
grow faster than the consumer could drain it. Two hours later, a DLQ we had never monitored
contained 8 400 permanently failed messages.

---

## Context

Cloudflare Queues delivers messages in batches to a consumer Worker. The consumer has:

- A **batch size** (max messages per invocation, default 10, max 100)
- A **concurrency limit** (max parallel consumer invocations, default unbounded up to Workers
  platform limits)
- A **visibility timeout** after which unacknowledged messages are redelivered
- A **retry limit** after which messages go to the Dead Letter Queue (DLQ)

The failure modes we encountered:

```
Producer (API Worker)
  │  ↑↑↑ traffic spike
  ▼
Queue (120 000 messages)
  │
  ├─ Consumer auto-scales to N workers
  │     │
  │     └─► Fulfilment API (10 req/s limit)
  │           │
  │           └─ HTTP 429  ──► message retried
  │                           ──► retry amplification
  │
  └─ After max_retries: message → DLQ (never monitored)
```

---

## Solution

### 1. Explicit consumer concurrency limit

```toml
# wrangler.toml
[[queues.consumers]]
queue = "order-fulfilment"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "order-fulfilment-dlq"

# Critical: cap consumer parallelism
max_concurrency = 5   # 5 workers × 10 msg/batch = 50 in-flight max
```

With a 10 req/s limit on the fulfilment API and ~200 ms per call, 5 concurrent consumers sending
batches of 10 give roughly 5 × 5 req/s = 25 req/s sustained — comfortably under the limit.

### 2. Per-message error handling with selective retry

Do not let one bad message block the whole batch:

```typescript
import type { MessageBatch, Message, Queue } from '@cloudflare/workers-types';

interface OrderMessage {
  orderId: string;
  customerId: string;
  items: Array<{ sku: string; qty: number }>;
}

export const queueConsumer = {
  async queue(
    batch: MessageBatch<OrderMessage>,
    env: Env
  ): Promise<void> {
    const results = await Promise.allSettled(
      batch.messages.map((msg) => processOrder(msg, env))
    );

    for (let i = 0; i < batch.messages.length; i++) {
      const msg = batch.messages[i];
      const result = results[i];

      if (result.status === 'fulfilled') {
        msg.ack();
      } else {
        const err = result.reason as Error;
        if (isRateLimitError(err)) {
          // Retry later — do NOT ack
          msg.retry({ delaySeconds: 30 });
        } else if (isPermanentError(err)) {
          // Bad data — ack to prevent infinite retry; log for investigation
          console.error(`Permanent failure for order ${msg.body.orderId}:`, err);
          msg.ack(); // or send to a custom error store before acking
        } else {
          msg.retry(); // transient error — retry immediately
        }
      }
    }
  },
};

async function processOrder(
  msg: Message<OrderMessage>,
  env: Env
): Promise<void> {
  const resp = await fetch(env.FULFILMENT_API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.FULFILMENT_KEY}` },
    body: JSON.stringify(msg.body),
  });

  if (resp.status === 429) {
    const retryAfter = parseInt(resp.headers.get('Retry-After') ?? '30', 10);
    throw new RateLimitError(`Rate limited — retry after ${retryAfter}s`, retryAfter);
  }

  if (!resp.ok) {
    const body = await resp.text();
    if (resp.status >= 400 && resp.status < 500) {
      throw new PermanentError(`Bad request: ${resp.status} ${body}`);
    }
    throw new Error(`Upstream error: ${resp.status}`);
  }
}

class RateLimitError extends Error {
  constructor(message: string, public readonly retryAfterSeconds: number) {
    super(message);
    this.name = 'RateLimitError';
  }
}

class PermanentError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PermanentError';
  }
}

function isRateLimitError(err: unknown): err is RateLimitError {
  return err instanceof RateLimitError;
}

function isPermanentError(err: unknown): err is PermanentError {
  return err instanceof PermanentError;
}
```

### 3. DLQ monitoring

A DLQ that nobody watches is worse than no DLQ — it gives false confidence.

```typescript
// DLQ consumer — alerts and stores failures
export const dlqConsumer = {
  async queue(
    batch: MessageBatch<OrderMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      // Store for manual review
      await env.DB.prepare(
        `INSERT INTO failed_orders
           (order_id, customer_id, payload, failed_at)
         VALUES (?, ?, ?, ?)`
      )
        .bind(
          msg.body.orderId,
          msg.body.customerId,
          JSON.stringify(msg.body),
          new Date().toISOString()
        )
        .run();

      // Alert — push to PagerDuty or similar
      await notifyOncall(env, {
        severity: 'high',
        summary: `Order ${msg.body.orderId} permanently failed`,
        details: JSON.stringify(msg.body),
      });

      msg.ack();
    }
  },
};

async function notifyOncall(
  env: Env,
  alert: { severity: string; summary: string; details: string }
): Promise<void> {
  await fetch(env.PAGERDUTY_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: env.PAGERDUTY_KEY,
      event_action: 'trigger',
      payload: alert,
    }),
  });
}
```

### 4. Producer back-pressure: fail fast when queue is too deep

```typescript
// Optionally track queue depth in KV and refuse new orders when backlog is severe
export async function enqueueOrder(
  order: OrderMessage,
  env: Env
): Promise<'queued' | 'shed'> {
  const depthRaw = await env.KV.get('queue:order-fulfilment:depth');
  const depth = depthRaw ? parseInt(depthRaw, 10) : 0;

  if (depth > 50_000) {
    // Return 503 to the client rather than making the backlog worse
    return 'shed';
  }

  await env.ORDER_QUEUE.send(order, { contentType: 'json' });
  return 'queued';
}
```

---

## Implementation Details

### Retry amplification: the maths

With `max_retries = 5` and 3 consumer workers each processing 10 messages per batch:

- 100 messages enter the queue
- Each retries 5 times before DLQ
- Total processing attempts: 100 × (1 + 5) = 600
- If each attempt takes 200 ms: 600 × 200 ms = 120 s of CPU time
- If the cause of failure is a downstream outage, all 600 attempts are wasted

Mitigation: use `delaySeconds` on retry to implement exponential back-off rather than hammering
the downstream immediately:

```typescript
msg.retry({ delaySeconds: Math.min(2 ** msg.attempts * 5, 300) });
// attempt 1: 5 s, attempt 2: 10 s, attempt 3: 20 s, attempt 4: 40 s, attempt 5: 80 s
```

### What we'd do differently

1. **Set `max_concurrency` from day one** — never leave it unbounded for a consumer that calls a
   rate-limited API.
2. **Monitor the DLQ at launch** — add a scheduled Worker that counts DLQ depth and alerts if
   non-zero.
3. **Load test with realistic burst** — we only tested at 1× expected traffic; 10× for 11 minutes
   was sufficient to surface every problem.
4. **Use `delaySeconds` on all retries** — the default is immediate retry, which is almost never
   the right behaviour for an external API error.
5. **Track `msg.attempts`** — surface it in logs so you can identify messages that are repeatedly
   failing before they reach the DLQ.

```typescript
// Logging wrapper
async function processWithLogging(
  msg: Message<OrderMessage>,
  env: Env
): Promise<void> {
  console.log(
    JSON.stringify({
      orderId: msg.body.orderId,
      attempt: msg.attempts,
      messageId: msg.id,
      enqueuedAt: msg.timestamp,
    })
  );
  await processOrder(msg, env);
}
```

---

## Anti-patterns

| Anti-pattern | Consequence |
|---|---|
| Unbounded `max_concurrency` with a rate-limited upstream | Consumer auto-scales and hammers the API |
| `batch.retryAll()` on any error | Retry storms; healthy messages re-queued alongside bad ones |
| No DLQ configured | On max retries, messages are silently dropped |
| DLQ configured but not monitored | False confidence; data loss invisible until a complaint |
| Immediate retry (no delay) on 429 | Wasted CPU; back-pressure on the upstream gets worse |
| Same Worker handling both queue and HTTP traffic | Resource contention; queue consumer may time out |

---

## Gotchas

1. **`max_concurrency` in `wrangler.toml` caps concurrent Worker invocations**, not concurrent
   messages. With `max_batch_size = 10` and `max_concurrency = 5`, you can have up to 50 messages
   in-flight simultaneously.

2. **Visibility timeout on unacknowledged messages defaults to 30 s** (configurable up to 43 200 s).
   If your consumer takes longer than the visibility timeout, the message is redelivered and you
   will process it twice.

3. **`msg.retry({ delaySeconds: N })` requires `N >= 0`**. Zero means "retry immediately"; any
   negative value throws at runtime.

4. **Queue consumers have a 15-minute wall-clock limit per invocation.** Long-running batch
   processing must be broken into smaller chunks or offloaded to Durable Objects.

5. **Cloudflare does not expose queue depth via an API** (as of 2026). You must proxy it: count
   messages in a D1 table or use the Dashboard metrics to set manual alerts.

---

## Verification

```typescript
import { describe, it, expect, vi } from 'vitest';
import { createMessageBatch } from 'cloudflare:test';

describe('queue consumer', () => {
  it('retries rate-limited messages with delay and acks successful ones', async () => {
    const ackSpy = vi.fn();
    const retrySpy = vi.fn();

    const batch = createMessageBatch<OrderMessage>('order-fulfilment', [
      { body: { orderId: 'ok-1', customerId: 'c1', items: [] }, ack: ackSpy, retry: retrySpy },
      { body: { orderId: 'rl-1', customerId: 'c2', items: [] }, ack: ackSpy, retry: retrySpy },
    ]);

    // Mock: 'ok-1' succeeds, 'rl-1' returns 429
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const body = JSON.parse(input as string);
      if (body.orderId === 'rl-1') {
        return new Response('Too many requests', {
          status: 429,
          headers: { 'Retry-After': '30' },
        });
      }
      return new Response(null, { status: 200 });
    });

    await queueConsumer.queue(batch, env);

    expect(ackSpy).toHaveBeenCalledTimes(1);  // only ok-1 acked
    expect(retrySpy).toHaveBeenCalledWith({ delaySeconds: 30 }); // rl-1 retried with delay
  });
});
```

---

## Related

- `documentation/docs/policies/lessons/d1-transaction-isolation-lessons.md`
- `documentation/docs/policies/lessons/kv-cache-stampede-lessons.md`
- `documentation/docs/policies/architecture/order-processing-pipeline.md`
- Cloudflare Queues documentation — Consumer concurrency, Dead Letter Queues

---

## Sources

- Cloudflare Queues documentation (2024–2026)
- Internal postmortem: `incidents/2025-11-black-friday-queue-storm.md`
- "Backpressure explained" — Jay Phelps
- AWS SQS visibility timeout design pattern (adapted for Workers Queues)
