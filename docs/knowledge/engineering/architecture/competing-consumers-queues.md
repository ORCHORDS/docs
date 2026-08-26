# Competing Consumers Pattern with Cloudflare Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A background image-processing pipeline must resize, watermark, and classify thousands of uploaded
images without blocking uploads. A single-threaded consumer cannot keep pace. Adding more Workers
risks double-processing the same image. The competing consumers pattern solves this: multiple
Workers pull from the same Queue, each claiming an exclusive batch of messages, processing them
independently, and acknowledging only their own messages.

## Context

Cloudflare Queues natively implements competing consumers through its batch delivery model: the
Queue service partitions messages across all active consumer invocations automatically. Unlike
broker-per-partition models (Kafka), Cloudflare Queues requires no manual partition assignment.
The platform guarantees that a message is delivered to exactly one consumer invocation at a time
(within the visibility timeout); if that invocation does not acknowledge before the timeout, the
message becomes visible again for another consumer.

Key properties relevant to this pattern:

- **Exclusive batch claim**: Each consumer invocation receives a non-overlapping batch.
- **Visibility timeout**: Unacknowledged messages are re-queued after the timeout.
- **Backpressure**: The Queue service caps the number of concurrent consumer invocations,
  providing implicit rate limiting.
- **Max concurrency**: Configurable via `max_concurrency` in `wrangler.toml`.

## Basic Competing Consumer Setup

```typescript
// image-processor.ts — one consumer class, many concurrent instances
interface ImageJob {
  jobId: string;
  r2Key: string;
  operations: ("resize" | "watermark" | "classify")[];
  userId: string;
  uploadedAt: string;
}

export default {
  async queue(batch: MessageBatch<ImageJob>, env: Env): Promise<void> {
    // Cloudflare invokes this handler concurrently across multiple isolates.
    // Each invocation receives an exclusive, non-overlapping batch.
    const results = await Promise.allSettled(
      batch.messages.map((msg) => processImage(msg, env))
    );

    // Individual message acknowledgement: ack successes, retry failures.
    results.forEach((result, i) => {
      const msg = batch.messages[i];
      if (result.status === "fulfilled") {
        msg.ack();
      } else {
        console.error(`Job ${msg.body.jobId} failed:`, result.reason);
        msg.retry({ delaySeconds: backoff(msg.attempts) });
      }
    });
  },
} satisfies ExportedHandler<Env>;

async function processImage(msg: Message<ImageJob>, env: Env): Promise<void> {
  const { jobId, r2Key, operations } = msg.body;

  // Idempotency check — guard against redelivery.
  const alreadyDone = await env.KV.get(`job:done:${jobId}`);
  if (alreadyDone) return; // Already processed by another consumer instance.

  // Retrieve the image from R2.
  const obj = await env.IMAGE_BUCKET.get(r2Key);
  if (!obj) throw new Error(`R2 object not found: ${r2Key}`);
  const imageBytes = await obj.arrayBuffer();

  // Run requested operations.
  let processed = imageBytes;
  for (const op of operations) {
    processed = await applyOperation(op, processed, env);
  }

  // Write result back to R2 under a deterministic output key.
  await env.IMAGE_BUCKET.put(`processed/${r2Key}`, processed, {
    customMetadata: { jobId, operations: operations.join(",") },
  });

  // Update D1 job status.
  await env.DB.prepare(
    "UPDATE image_jobs SET status = 'done', finished_at = ? WHERE id = ?"
  ).bind(new Date().toISOString(), jobId).run();

  // Mark as done in KV to guard against race conditions on redelivery.
  await env.KV.put(`job:done:${jobId}`, "1", { expirationTtl: 86400 });
}

async function applyOperation(
  op: "resize" | "watermark" | "classify",
  bytes: ArrayBuffer,
  env: Env
): Promise<ArrayBuffer> {
  // Delegate to Cloudflare Images transform Worker or external API.
  const res = await fetch(`https://image-ops.internal/${op}`, {
    method: "POST",
    body: bytes,
    headers: { Authorization: `Bearer ${env.IMAGE_OPS_KEY}` },
  });
  if (!res.ok) throw new Error(`${op} failed: ${res.status}`);
  return res.arrayBuffer();
}

function backoff(attempt: number): number {
  return Math.min(5 * Math.pow(2, attempt), 120);
}
```

## Concurrency Control via wrangler.toml

```toml
# wrangler.toml

name = "image-processor"
main = "src/image-processor.ts"

[[queues.consumers]]
queue = "image-jobs"
max_batch_size = 10          # Messages per invocation
max_batch_timeout = 3        # Seconds to wait for a full batch
max_retries = 4              # Per-message retry limit
dead_letter_queue = "image-jobs-dlq"
max_concurrency = 20         # Max simultaneous consumer invocations
visibility_timeout_secs = 60 # Re-queue if not acked within 60 s
```

Setting `max_concurrency` caps resource cost and prevents thundering-herd overload on external
APIs. Without it the Queue service scales consumer concurrency unboundedly.

## Rate-Limited Competing Consumer

When a downstream API (e.g. a third-party classifier) enforces a per-second rate limit, a single
Durable Object can act as a global token bucket that all competing consumers must acquire from
before calling the API.

```typescript
// RateLimitDO.ts
const CAPACITY = 50;   // tokens
const REFILL_RATE = 50; // tokens per second

export class RateLimitDO implements DurableObject {
  private tokens = CAPACITY;
  private lastRefill = Date.now();

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const needed = parseInt(url.searchParams.get("n") ?? "1", 10);

    // Refill tokens based on elapsed time.
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(CAPACITY, this.tokens + elapsed * REFILL_RATE);
    this.lastRefill = now;

    if (this.tokens >= needed) {
      this.tokens -= needed;
      return Response.json({ granted: true });
    }
    const waitMs = Math.ceil(((needed - this.tokens) / REFILL_RATE) * 1000);
    return Response.json({ granted: false, retryAfterMs: waitMs }, { status: 429 });
  }
}

// Consumer integration: acquire token before calling external API.
async function acquireRateLimit(env: Env, n = 1): Promise<void> {
  const id = env.RATE_LIMIT_DO.idFromName("classifier-global");
  const stub = env.RATE_LIMIT_DO.get(id);

  let attempts = 0;
  while (attempts < 5) {
    const res = await stub.fetch(`https://rl/?n=${n}`);
    const body = await res.json<{ granted: boolean; retryAfterMs?: number }>();
    if (body.granted) return;
    await new Promise<void>((r) => setTimeout(r, body.retryAfterMs ?? 200));
    attempts++;
  }
  throw new Error("Rate limit acquire timed out");
}
```

## Poison Message Handling

A poison message crashes every consumer that receives it — triggering retries until the max is
exhausted, at which point it moves to the DLQ. To detect and isolate poison messages early:

```typescript
// Wrap processImage in a per-message timeout.
async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms)
  );
  return Promise.race([promise, timeout]);
}

// In the queue handler:
batch.messages.map((msg) =>
  withTimeout(processImage(msg, env), 25_000) // 25 s per image
    .then(() => msg.ack())
    .catch((err) => {
      if (msg.attempts >= 3) {
        // Send to DLQ explicitly rather than waiting for max_retries.
        msg.ack(); // Remove from main queue.
        env.DLQ_QUEUE.send({ original: msg.body, error: err.message });
      } else {
        msg.retry({ delaySeconds: backoff(msg.attempts) });
      }
    })
);
```

## Anti-patterns

- **Sharing mutable state between consumer invocations**: Each invocation is an isolated Worker
  instance. In-memory state is never shared. Use KV, D1, or Durable Objects for shared state.
- **Not implementing idempotency**: At-least-once delivery means a message can arrive twice.
  Every consumer must be idempotent (check KV or DB before writing).
- **Acking the entire batch on partial failure**: `batch.ackAll()` silently discards unprocessed
  messages if any threw before the ack call. Always ack and retry at the individual message level.
- **Blocking the batch on a single slow message**: Use `Promise.allSettled()`, not `Promise.all()`.
  One slow image must not stall the other 49 in the batch.
- **Setting max_batch_size too high for CPU-intensive work**: Images or ML inference can easily
  hit the 30-second CPU time limit. Keep batch sizes small for heavy operations.

## Gotchas

- The `max_concurrency` setting controls the number of simultaneous *invocations*, not the total
  number of messages being processed. With `max_batch_size=10` and `max_concurrency=20`, up to
  200 messages may be processed simultaneously.
- Consumer Workers and producer Workers must be configured as **separate scripts** in separate
  `wrangler.toml` files or as separate named entries if using `wrangler.toml` services.
- Cloudflare Queues does not guarantee **ordering** within or across batches. If processing order
  matters, embed sequence numbers in message payloads and sort within the consumer.
- The visibility timeout clock starts the moment the batch is delivered, not when `processImage()`
  starts. Long-running operations must complete well within `visibility_timeout_secs`.

## Verification

```bash
# Enqueue 100 test jobs and observe concurrent consumer invocations:
for i in $(seq 1 100); do
  curl -s -X POST https://api.example.com/images/upload \
    -d "{\"r2Key\":\"test/image-$i.jpg\",\"operations\":[\"resize\"]}" &
done
wait

# Check job status in D1:
wrangler d1 execute image-db --command \
  "SELECT status, COUNT(*) FROM image_jobs GROUP BY status;"

# Inspect DLQ for poison messages:
wrangler queues message list image-jobs-dlq --limit 10
```

## Related

- `competing-consumers-durable-objects.md`
- `async-job-queue-cloudflare-queues-do.md`
- `temporal-decoupling-cloudflare-queues.md`
- `dead-letter-queue-architecture.md`
- `at-least-once-delivery.md`
- `idempotency-design.md`
- `backpressure-patterns.md`

## Sources

- Cloudflare Queues concurrency — https://developers.cloudflare.com/queues/platform/concurrency/
- Cloudflare Queues batching and retries — https://developers.cloudflare.com/queues/reference/batching-retries/
- Enterprise Integration Patterns — "Competing Consumers" — Hohpe & Woolf, Addison-Wesley 2003
