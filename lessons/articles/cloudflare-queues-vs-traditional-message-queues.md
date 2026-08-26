# Decision Record: Choosing Cloudflare Queues Over Traditional Message Queues

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Decision:** Adopt Cloudflare Queues as the primary async messaging layer for all Worker-to-Worker background work

---

## Use Case

The platform needed an asynchronous messaging layer to decouple high-throughput write paths (engagement events, project export jobs, email notification dispatch) from synchronous HTTP request handlers. The team evaluated Cloudflare Queues, AWS SQS, Upstash for Redis Streams, and a self-hosted NATS cluster before committing to Cloudflare Queues.

---

## Context

The platform runs entirely on Cloudflare Workers. All compute is serverless; there are no long-running processes. Any messaging solution must be:

1. Accessible from a Worker binding without an outbound HTTP call to a third-party service
2. Durable across Worker restarts and Cloudflare's multi-region topology
3. Capable of at-least-once delivery with configurable retry and dead-letter behaviour
4. Priced at a level compatible with high-volume, low-margin SaaS unit economics

At the time of evaluation (Q2 2026), the platform processed approximately 8 million engagement events per day with seasonal peaks at 4x that volume.

---

## Options Considered

### Option A: Cloudflare Queues

Native Cloudflare product. Workers send messages via a binding (`env.MY_QUEUE.send()`). A separate consumer Worker processes batches. Delivery is at-least-once with configurable retry delays and a dead-letter queue.

**Pricing (as of evaluation):** $0.40 per million message operations (send + deliver = 2 operations per message = $0.80/M messages). First 1M operations per month free.

**Limits:** Maximum message size 128 KB; maximum batch size 100 messages; maximum consumer concurrency governed by Worker concurrency limits.

### Option B: AWS SQS

Industry-standard, battle-tested, extremely high throughput, rich ecosystem. Workers would need to call the SQS API over HTTPS using an IAM-signed request. The AWS SDK requires a Node.js-compatible environment; a lightweight fetch-based SQS client would need to be written or sourced.

**Pricing:** $0.40 per million requests. Standard queue, first 1M free.

**Operational overhead:** AWS account, IAM roles, cross-region latency (us-east-1 or eu-west-1 depending on traffic origin), SDK compatibility shim for Workers runtime.

### Option C: Upstash Redis Streams (via HTTP API)

Upstash provides a Redis-compatible HTTP API, which is fully compatible with the Workers fetch API. Redis Streams provide ordered, consumer-group-aware message delivery. Message retention is configurable.

**Pricing:** Per-request pricing, similar order of magnitude to SQS. Upstash is a third-party vendor.

**Concerns:** Ordering guarantees complicate consumer scaling. Consumer group state must be managed explicitly. Delivery semantics differ from a purpose-built queue.

### Option D: Self-Hosted NATS

Highest throughput ceiling of any option. Requires running persistent infrastructure (at minimum a NATS cluster on fly.io or a VPS). Workers would call NATS JetStream over HTTPS.

**Operational overhead:** Significant. Cluster maintenance, certificate rotation, capacity planning, monitoring — all for infrastructure the team must own.

---

## Decision

**Cloudflare Queues (Option A).**

---

## Rationale

### 1. Zero-Egress Binding Model

The most important factor was operational simplicity. With Cloudflare Queues, the producer Worker calls `env.MY_QUEUE.send(payload)` — a binding call, not an outbound HTTP request. This means:

- No authentication secrets to manage (no AWS IAM keys, no Upstash API tokens)
- No TLS handshake overhead on the critical path
- No cross-cloud latency (the queue is co-located with the Worker runtime)
- No SDK compatibility issues

For a team of four engineers running a platform entirely on Cloudflare, eliminating a third-party dependency entirely was worth accepting a lower throughput ceiling.

### 2. Native Dead-Letter Queue Support

Cloudflare Queues supports a dead-letter queue (DLQ) binding out of the box. Messages that fail delivery after the configured retry count are automatically moved to the DLQ. The team can inspect, replay, or alert on DLQ messages without building that infrastructure.

SQS also supports DLQs, but the cross-cloud integration adds complexity. Upstash and NATS require custom dead-letter handling.

### 3. Pricing Alignment With Usage Pattern

At 8 million engagement events per day (240M/month), Cloudflare Queues costs approximately $0.192/day ($5.76/month after the free tier). This is below the noise floor of the platform's infrastructure bill. The simplicity premium is effectively free at this scale.

At 10x scale (2.4B events/month), the cost is approximately $1,920/month — still cheaper than the engineering cost of operating SQS integration or a NATS cluster.

### 4. Batch Consumer Model Fits the Use Case

The platform's consumer Workers process events in batches. Cloudflare Queues delivers up to 100 messages per consumer invocation. The consumer can process the entire batch in a single D1 transaction:

```ts
export default {
  async queue(batch: MessageBatch<EngagementEvent>, env: Env) {
    const rows = batch.messages.map(m => m.body);
    await env.DB.batch(
      rows.map(r =>
        env.DB.prepare(
          'INSERT OR IGNORE INTO plays (project_id, user_id, ts) VALUES (?, ?, ?)'
        ).bind(r.projectId, r.userId, r.ts)
      )
    );
    batch.ackAll();
  }
};
```

This batching model naturally amortises D1 write overhead across many messages, reducing per-event write cost.

### 5. Future Worker-to-Worker Fan-Out

Cloudflare Queues supports sending from one Worker to a queue consumed by a different Worker, enabling fan-out patterns without direct Worker invocation. The platform plans to use this for notification dispatch: an engagement event enqueued by the API Worker is consumed by a notification Worker that decides whether to send an email, push notification, or in-app notification. This pattern is trivial with Queues bindings and would require explicit HTTP calls or a third-party pub/sub layer with SQS.

---

## Trade-Offs Accepted

### Lower Throughput Ceiling Than SQS

SQS supports tens of thousands of messages per second per queue. Cloudflare Queues' effective throughput is lower. At peak traffic (32 million events/day = ~370 events/second average, ~1,500 events/second burst), Cloudflare Queues comfortably handles the load. If the platform reaches 100x current scale, this decision should be revisited.

### No FIFO / Strict Ordering

Cloudflare Queues is a standard (best-effort ordering) queue. It does not guarantee FIFO delivery. For engagement events this is acceptable — the order of play counts being recorded is irrelevant. For use cases requiring strict ordering (e.g., payment state machine transitions), Cloudflare Queues is not appropriate without an additional ordering mechanism.

### No Message Filtering / Routing at Queue Level

SQS with SNS supports message attribute filtering, allowing different consumers to receive different message subsets from a single topic. Cloudflare Queues is point-to-point: one queue, one consumer Worker. Routing logic must live in the consumer. The team accepted this and routes by message type inside the consumer:

```ts
switch (msg.type) {
  case 'play': return handlePlay(msg, env);
  case 'like': return handleLike(msg, env);
  case 'fork': return handleFork(msg, env);
}
```

---

## Anti-Patterns

- **Using KV as a queue.** KV has no delivery guarantee, no retry, no ordering, and no consumer model. It is a key-value store, not a queue. Teams sometimes abuse KV as a "poor man's queue" by writing job keys and polling; this approach loses messages on consumer failure and has no dead-letter mechanism.
- **Direct Worker-to-Worker invocation for background work.** Using `fetch()` to call another Worker for fire-and-forget work ties the producer to the consumer's availability. If the consumer is slow or unavailable, the producer blocks. Use Queues for true decoupling.
- **Acknowledging messages before processing.** Call `batch.ackAll()` only after the batch has been successfully processed. If the consumer throws before acking, Queues will redeliver. Premature acks cause silent message loss.
- **Treating Queues as a guaranteed-once delivery system.** Cloudflare Queues is at-least-once. Consumers must be idempotent. Use `ON CONFLICT DO NOTHING` in D1, or a deduplication key in KV, to handle redelivery safely.

---

## Gotchas

- The `wrangler.toml` must declare both the `[[queues.producers]]` binding for the sender Worker and `[[queues.consumers]]` for the consumer Worker. Getting the binding names wrong in one file produces a silent failure at runtime where the queue is never consumed.
- Cloudflare Queues does not support message priorities. All messages in a queue are treated equally. If some message types are more urgent than others, use separate queues.
- Consumer concurrency is not independently configurable; it follows Worker concurrency. If the consumer is CPU-intensive, it may back up under high throughput. Design consumer batches to complete in under 30 seconds.
- The DLQ must be a separate queue (also declared in `wrangler.toml`). Messages moved to the DLQ are not automatically retried from there; explicit replay logic is required.
- `env.MY_QUEUE.send()` can fail if the Cloudflare Queues service is unavailable. The producer should handle this with a try/catch and fall back to logging or a secondary path.

---

## Verification

Decision validated by:

1. Load test at 10,000 messages/second burst: consumer lag peaked at 4.2 seconds before catching up. Acceptable for engagement data.
2. Failure injection: consumer Worker threw on every message; Queues retried with exponential backoff; all messages eventually landed in DLQ. DLQ alert fired within 2 minutes.
3. 90-day production operation (Q2–Q3 2026): zero message loss events; DLQ had 3 entries (all due to malformed payloads from a client bug, not infrastructure failure).

---

## Related

- `d1-write-contention-viral-event-postmortem.md`
- `queue-consumers-must-be-idempotent.md`
- `queue-backlog-death-spirals.md`
- `retry-storm-queue-poison-message.md`
- `cloudflare-storage-primitive-selection.md`
- `webhook-delivery-is-not-guaranteed.md`

---

## Sources

- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare Queues pricing: https://developers.cloudflare.com/queues/platform/pricing/
- AWS SQS pricing: https://aws.amazon.com/sqs/pricing/
- Upstash Redis Streams: https://upstash.com/docs/redis/features/streams
