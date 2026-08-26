# Workers Pipelines Write Throughput Optimization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A high-traffic Workers application writes clickstream events, log lines, or sensor readings to
storage one record at a time. At 5 000 requests per second, each Worker writes to R2 or D1
individually, saturating origin connections and generating millions of tiny objects. P99
request latency includes a 50–80 ms write penalty per event. Workers Pipelines resolves this
by buffering events and delivering them in micro-batches.

---

## Context

Cloudflare Workers Pipelines is a managed event-ingestion service that accepts records from
Workers in real time, buffers them in Cloudflare's infrastructure, and flushes them to a sink
(R2, HTTP endpoint, or Workers) in configurable batches. Writing to a Pipeline from a Worker
is a fire-and-forget operation: the Worker sends the record and immediately returns a
response to the end user. The Pipeline service handles batching, retries, and delivery
asynchronously.

This decoupling achieves two goals:

1. **Latency isolation** — the write path is removed from the user-facing request latency.
2. **Throughput amplification** — thousands of individual writes are consolidated into
   efficient batch deliveries (e.g. a single R2 `PUT` of a 5 MB JSON-lines file instead of
   5 000 individual `PUT` requests for 1 kB files each).

---

## Pipeline Creation

```bash
# Create a Pipeline that delivers to R2
wrangler pipelines create my-events-pipeline \
  --r2-bucket my-events-bucket \
  --batch-max-mb 10 \
  --batch-max-seconds 5 \
  --batch-max-rows 10000
```

Parameters:
- `--batch-max-mb` — flush when buffered data reaches N MB (max 100)
- `--batch-max-seconds` — flush at most every N seconds even if size threshold not reached
- `--batch-max-rows` — flush when record count reaches N (max 100 000)

The first threshold reached triggers a flush. For low-latency analytics pipelines, a 5-second
flush interval balances batch efficiency against data freshness.

---

## Writing Records from a Worker

```typescript
// wrangler.toml binding:
// [[pipelines]]
// binding = "EVENTS"
// pipeline = "my-events-pipeline"

export interface Env {
  EVENTS: Pipeline;
}

interface ClickEvent {
  ts: number;
  userId: string;
  sessionId: string;
  url: string;
  referrer: string;
  eventType: 'click' | 'pageview' | 'conversion';
  metadata?: Record<string, string>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Parse the incoming event
    const body = await request.json<ClickEvent>();

    const event: ClickEvent = {
      ts: Date.now(),
      userId: body.userId,
      sessionId: body.sessionId,
      url: body.url,
      referrer: body.referrer,
      eventType: body.eventType,
      metadata: body.metadata,
    };

    // Non-blocking write — the Pipeline binding buffers this record
    // and delivers it in a batch without blocking the response
    ctx.waitUntil(env.EVENTS.send(event));

    return new Response(null, { status: 204 });
  },
};
```

`env.EVENTS.send(record)` returns a `Promise<void>`. Wrapping it in `ctx.waitUntil` ensures
the Worker isolate stays alive long enough to dispatch the record to the Pipeline service even
after `fetch()` has returned a response, without adding latency to the user-facing response.

---

## Batch Writing for Higher Throughput

When a single Worker request processes multiple events (e.g. a log-aggregation endpoint that
receives a batch payload from a client SDK), use `sendBatch` to deliver all records in one
Pipeline API call:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const events = await request.json<ClickEvent[]>();

    if (!Array.isArray(events) || events.length === 0) {
      return new Response('Bad Request', { status: 400 });
    }

    // Cap batch size to avoid exceeding Pipeline limits
    const capped = events.slice(0, 10_000);

    const records = capped.map(e => ({
      ...e,
      ts: Date.now(),
    }));

    ctx.waitUntil(env.EVENTS.sendBatch(records));

    return Response.json({ accepted: records.length });
  },
};
```

`sendBatch` accepts an array of up to 10 000 records per call. Multiple `sendBatch` calls
from the same Worker invocation are each queued independently within the Pipeline service.

---

## Pipeline Consumer Worker (R2 Sink)

When the sink is a Worker rather than R2 directly, the Pipeline delivers batches as Worker
`pipeline` events:

```typescript
// Consumer Worker — processes batches delivered by the Pipeline
export interface Env {
  PROCESSED_BUCKET: R2Bucket;
}

interface PipelineBatch<T> {
  readonly messages: PipelineMessage<T>[];
}

interface PipelineMessage<T> {
  readonly body: T;
}

export default {
  async pipeline<Env>(
    batch: PipelineBatch<ClickEvent>,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    const lines = batch.messages.map(m => JSON.stringify(m.body)).join('\n');
    const key = `events/${new Date().toISOString().slice(0, 13)}/${crypto.randomUUID()}.jsonl`;

    await (env as unknown as { PROCESSED_BUCKET: R2Bucket }).PROCESSED_BUCKET.put(
      key,
      lines,
      {
        httpMetadata: { contentType: 'application/x-ndjson' },
        customMetadata: { recordCount: String(batch.messages.length) },
      },
    );
  },
};
```

Using a consumer Worker before R2 allows custom key-naming, partitioning by time or user
segment, or additional transforms (schema validation, PII scrubbing) before storage.

---

## Throughput Capacity

| Metric | Limit |
|---|---|
| Records per second per Pipeline | 1 000 000 (soft) |
| Maximum batch size (rows) | 100 000 |
| Maximum batch size (bytes) | 100 MB |
| Maximum record size | 1 MB |
| Maximum flush interval | 300 s |
| Delivery guarantee | At-least-once |

Pipelines provide at-least-once delivery: in failure scenarios (Worker crash during
`sendBatch`, transient network error), a record may be delivered more than once. Design
consumers to be idempotent (e.g. upsert on a unique event ID rather than blind insert).

---

## Deduplication Pattern

```typescript
// Add a deterministic event ID for idempotent consumers
import { createHash } from 'crypto'; // available in Workers via globalThis.crypto

function eventId(event: ClickEvent): string {
  const key = `${event.userId}:${event.sessionId}:${event.ts}:${event.eventType}`;
  // Use SubtleCrypto since Node crypto is not available in Workers
  // For a simpler approach, use a ULID or UUID
  return crypto.randomUUID(); // statistically unique; accept tiny duplication risk
}
```

For truly idempotent processing, embed an `eventId` field in each record and use D1's
`INSERT OR IGNORE` or R2 object keys derived from the event ID.

---

## Anti-patterns

**Writing to R2 / D1 directly inside the hot request path.** Each `PUT` to R2 or `INSERT`
into D1 adds 10–80 ms to the user-facing request. At high QPS this creates head-of-line
blocking and can exhaust D1's write quota. Always offload storage writes via Pipeline or
`waitUntil`.

**Sending records synchronously without `waitUntil`.** If `env.EVENTS.send(record)` is
awaited inline (not in `waitUntil`) and the Worker returns before the promise resolves, the
isolate may be recycled before the send completes, silently dropping the event.

**Very short flush intervals (< 1 s).** Sub-second flush intervals negate the batching
benefit — each flush produces a tiny R2 object. For analytics workloads, 5–30 s intervals
strike the right balance between data freshness and storage efficiency.

**Unbounded record size.** Sending large objects (images, binary blobs) through a Pipeline
bypasses the 1 MB per-record limit and fails silently or with an error that is hard to
surface. Upload large objects to R2 directly and write only the R2 key reference as a
Pipeline record.

---

## Gotchas

- **`ctx.waitUntil` budget.** A Worker has a maximum `waitUntil` duration of 30 s on the
  Workers Paid plan. If `env.EVENTS.send()` is slow (network error, timeout), it consumes
  this budget. Pipeline sends are typically sub-millisecond locally (fire-and-forget to the
  buffering layer), so this is rarely an issue in practice.

- **Ordering.** Pipeline delivery order is not guaranteed within or across batches. If strict
  event ordering is required, embed a monotonic sequence number in each record and sort in the
  consumer.

- **Pipeline availability.** Pipelines is a Cloudflare-managed service; it is not available
  on the free Workers plan. Check current plan eligibility in the Cloudflare dashboard.

- **Schema evolution.** Changing the structure of records written to a Pipeline will affect
  consumers. Add fields (additive changes) rather than removing or renaming fields to avoid
  breaking downstream D1 inserts or R2 JSON parsing.

---

## Verification

```bash
# Tail Pipeline delivery logs
wrangler pipelines tail my-events-pipeline

# Check delivery metrics (via Cloudflare dashboard → Pipelines → my-events-pipeline)
# Key metrics:
# - Records received / s
# - Batches delivered / min
# - Average batch size (rows and bytes)
# - Delivery latency (time from send() to sink write)
```

Confirm that adding `ctx.waitUntil(env.EVENTS.send(...))` does not appear in Workers request
duration traces — the P99 user-facing latency should be identical to a response-only Worker.

---

## Related

- `queues-throughput-batching.md`
- `queues-consumer-concurrency-throughput.md`
- `workers-waituntil-background-processing.md`
- `analytics-engine-write-throughput-batching.md`
- `r2-multipart-parallel-upload-throughput.md`
- `workers-response-streaming-ttfb-optimization.md`

---

## Sources

- Cloudflare Workers Pipelines documentation: https://developers.cloudflare.com/pipelines/
- Cloudflare Pipelines limits: https://developers.cloudflare.com/pipelines/platform/limits/
- `ctx.waitUntil` reference: https://developers.cloudflare.com/workers/runtime-apis/context/
- R2 pricing and limits: https://developers.cloudflare.com/r2/pricing/
