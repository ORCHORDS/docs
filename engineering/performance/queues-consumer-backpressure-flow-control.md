# Queues Consumer Backpressure and Flow Control

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
A Cloudflare Queue consumer Worker fails repeatedly under burst load, causing messages to pile up and eventually reach the dead-letter threshold. Implementing explicit acknowledgement batching, partial retry, and producer-side flow control reduces DLQ delivery by over 95 % without sacrificing throughput.

## Context
Cloudflare Queues delivers messages to consumer Workers in batches of up to 100 messages. The consumer must `ack()` or `retry()` each message (or call `batch.ackAll()` / `batch.retryAll()`) within the batch processing deadline (default 30 s wall-clock, up to 15 min with `max_concurrency` tuned). If the consumer throws or times out, the entire batch is automatically retried. This all-or-nothing retry model means a single slow message poisons the entire batch. The correct pattern is per-message `try/catch` with selective `message.retry()` calls and producer-side backpressure using KV or Durable Objects to throttle send rates under queue depth pressure.

## Pattern 1 — Per-Message Selective Ack / Retry

```typescript
interface EmailJob {
  recipientId: string;
  templateId: string;
  vars: Record<string, string>;
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    // Process each message independently — never let one failure abort the batch
    await Promise.allSettled(
      batch.messages.map(async (msg) => {
        try {
          await sendEmail(env, msg.body);
          msg.ack(); // Permanently remove from queue
        } catch (err: unknown) {
          const isTransient =
            err instanceof Error &&
            (err.message.includes("rate limit") ||
              err.message.includes("timeout") ||
              err.message.includes("503"));

          if (isTransient) {
            // Exponential backoff via delaySeconds — up to 42900 s (12 h)
            const backoff = Math.min(2 ** (msg.attempts - 1) * 10, 600);
            msg.retry({ delaySeconds: backoff });
          } else {
            // Permanent failure — ack to prevent DLQ spam, log separately
            console.error("Permanent email failure", { id: msg.id, err });
            msg.ack();
            await recordFailedJob(env.DB, msg.body, String(err));
          }
        }
      }),
    );
  },
};
```

## Pattern 2 — Bounded Concurrency Within a Batch

```typescript
// Default: all messages processed in parallel — risky when each message
// calls a rate-limited external API. Limit concurrency with a semaphore.
async function withConcurrencyLimit<T>(
  tasks: (() => Promise<T>)[],
  limit: number,
): Promise<PromiseSettledResult<T>[]> {
  const results: PromiseSettledResult<T>[] = [];
  const executing = new Set<Promise<void>>();

  for (const task of tasks) {
    const p: Promise<void> = task()
      .then((v) => results.push({ status: "fulfilled", value: v }))
      .catch((r) => results.push({ status: "rejected", reason: r }))
      .finally(() => executing.delete(p));

    executing.add(p);
    if (executing.size >= limit) await Promise.race(executing);
  }

  await Promise.allSettled(executing);
  return results;
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    await withConcurrencyLimit(
      batch.messages.map((msg) => async () => {
        try {
          await sendEmail(env, msg.body);
          msg.ack();
        } catch {
          msg.retry({ delaySeconds: 30 });
        }
      }),
      5, // max 5 concurrent external calls
    );
  },
};
```

## Pattern 3 — Producer-Side Flow Control via KV Depth Check

```typescript
const QUEUE_DEPTH_KEY = "queue:depth:email";
const MAX_QUEUE_DEPTH = 5_000;

async function enqueueEmailWithBackpressure(
  env: Env,
  job: EmailJob,
): Promise<{ enqueued: boolean; reason?: string }> {
  // Read queue depth counter from KV (approximate, updated by consumer)
  const depthStr = await env.KV.get(QUEUE_DEPTH_KEY);
  const depth = depthStr ? parseInt(depthStr, 10) : 0;

  if (depth >= MAX_QUEUE_DEPTH) {
    return {
      enqueued: false,
      reason: `Queue depth ${depth} exceeds limit ${MAX_QUEUE_DEPTH}`,
    };
  }

  await env.EMAIL_QUEUE.send(job);

  // Optimistically increment; consumer decrements on ack
  await env.KV.put(QUEUE_DEPTH_KEY, String(depth + 1), { expirationTtl: 3600 });

  return { enqueued: true };
}

// Consumer decrements the counter on successful ack
export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    let ackedCount = 0;

    await Promise.allSettled(
      batch.messages.map(async (msg) => {
        try {
          await sendEmail(env, msg.body);
          msg.ack();
          ackedCount++;
        } catch {
          msg.retry({ delaySeconds: 60 });
        }
      }),
    );

    if (ackedCount > 0) {
      const depthStr = await env.KV.get(QUEUE_DEPTH_KEY);
      const depth = Math.max(0, (depthStr ? parseInt(depthStr, 10) : 0) - ackedCount);
      await env.KV.put(QUEUE_DEPTH_KEY, String(depth), { expirationTtl: 3600 });
    }
  },
};
```

## Pattern 4 — Dead-Letter Queue Draining Worker

```typescript
// Separate Worker consuming the DLQ to inspect and selectively re-enqueue
export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    const replayable: EmailJob[] = [];

    for (const msg of batch.messages) {
      const body = msg.body;

      // Inspect failure reason stored in D1 during original processing
      const failure = await env.DB
        .prepare("SELECT reason FROM failed_jobs WHERE job_id = ? LIMIT 1")
        .bind(msg.id)
        .first<{ reason: string }>();

      if (failure?.reason.includes("temporary")) {
        replayable.push(body);
      }

      msg.ack(); // Always ack DLQ messages to prevent infinite loop
    }

    if (replayable.length > 0) {
      await env.EMAIL_QUEUE.sendBatch(
        replayable.map((job) => ({
          body: job,
          delaySeconds: 300, // 5-minute delay before retry
        })),
      );
    }
  },
};
```

## Pattern 5 — Throughput Monitoring via Analytics Engine

```typescript
export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    const t0 = Date.now();
    let acked = 0;
    let retried = 0;

    await Promise.allSettled(
      batch.messages.map(async (msg) => {
        try {
          await sendEmail(env, msg.body);
          msg.ack();
          acked++;
        } catch {
          msg.retry({ delaySeconds: 30 });
          retried++;
        }
      }),
    );

    env.ANALYTICS.writeDataPoint({
      blobs: ["email_queue_consumer", String(batch.queue)],
      doubles: [batch.messages.length, acked, retried, Date.now() - t0],
      indexes: [batch.queue.slice(0, 32)],
    });
  },
};
```

## Anti-patterns
- Calling `batch.retryAll()` on any processing error — retries the entire batch including already-successful messages, causing duplicate sends
- Not setting `delaySeconds` on retry — immediate retry under rate-limiting hammers the same external endpoint and perpetuates failures
- Using a single global `try/catch` around `batch.messages.map(...)` — one rejection causes the entire promise to reject and Queues retries the whole batch
- Allowing the consumer CPU budget to be consumed by logging before all `ack()`/`retry()` calls are made — incomplete acknowledgement causes the platform to retry the batch
- Relying on `msg.attempts` alone for retry decisions without an external circuit-breaker — `attempts` resets to 1 after DLQ delivery, hiding total retry history

## Gotchas
- `msg.retry({ delaySeconds })` sets a *minimum* delay; actual delivery may be later depending on queue backpressure and worker concurrency limits
- The `max_retries` setting (configurable per queue binding) counts platform-level retries before DLQ delivery — `msg.retry()` within the consumer is a different mechanism and counts against this limit
- Queues delivers at-least-once — always design consumers for idempotency; use a deduplication key in D1 or KV indexed by `msg.id`
- `batch.messages.length` can be less than `max_batch_size` at low throughput; do not assume full batches — size your timeout budget around single-message worst-case latency
- Workers invoked by Queues do not have access to `ctx.waitUntil()` in the same way as `fetch` handlers — post-processing after all messages are handled must complete synchronously before the `queue()` function returns

## Verification
```bash
# Tail consumer Worker logs
wrangler tail <consumer-worker-name> --format json | jq '{queue: .event.queue, msgs: .event.batchSize}'

# Query consumer throughput from Analytics Engine
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT toStartOfMinute(timestamp) AS min,
                 sum(double2) AS acked,
                 sum(double3) AS retried
          FROM email_queue_consumer
          WHERE timestamp > now() - INTERVAL '1' HOUR
          GROUP BY min ORDER BY min"

# Check queue metrics in dashboard
# Cloudflare Dashboard → Queues → <queue-name> → Metrics
```

## Related
- `queues-throughput-batching.md`
- `workers-queues-background-offload.md`
- `workers-waituntil-background-processing.md`
- `kv-bulk-get-batching.md`
- `analytics-engine-write-throughput-batching.md`

## Sources
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/queues/reference/how-queues-works/#acknowledgements-and-retries
- https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
