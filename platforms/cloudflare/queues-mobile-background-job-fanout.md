# queues-mobile-background-job-fanout

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users submit a example project social post; the app hangs for
several seconds while content moderation and push-notification
fanout run synchronously. On LTE, requests time out and users
tap again, producing duplicate submissions.

## Context

Mobile clients are the worst place to absorb slow work:
constrained CPUs extend execution time, cellular adds 100–400 ms
per round-trip, and OS suspension cuts connections mid-flight.
Return `202 Accepted` immediately and push every slow operation
(moderation, fanout, feed indexing) onto a Cloudflare Queue.

## 1. Producer/Consumer Pattern

```toml
# wrangler.toml
[[queues.producers]]
queue = "post-jobs"
binding = "POST_QUEUE"

[[queues.consumers]]
queue             = "post-jobs"
dead_letter_queue = "post-jobs-dlq"
max_batch_size    = 50
max_batch_timeout = 5
max_retries       = 5
max_concurrency   = 10
```

The **producer** Worker handles `POST /posts`, enqueues the job,
and returns immediately:

```typescript
const idempotencyKey =
  req.headers.get("Idempotency-Key") ?? crypto.randomUUID();
await env.POST_QUEUE.send(
  { ...body, idempotencyKey }, { contentType: "json" }
);
return Response.json({ queued: true }, { status: 202 });
```

The **consumer** Worker runs the slow work asynchronously:

```typescript
async queue(batch: MessageBatch<PostJob>, env: Env) {
  for (const msg of batch.messages) {
    try {
      await runModeration(msg.body, env);
      await fanoutNotifications(msg.body, env);
      msg.ack();
    } catch {
      msg.retry({ delaySeconds: 30 }); // backs off; hits DLQ later
    }
  }
}
```

## 2. Retry and Dead-Letter Queue

After `max_retries` failures, the message routes to the
configured `dead_letter_queue` rather than being silently
dropped. Default `max_retries` is **3** (up to **100**).

```toml
[[queues.consumers]]
queue = "post-jobs-dlq"
max_batch_size = 100
max_batch_timeout = 60
```

The DLQ consumer persists the failed payload for manual
replay and fires an alert:

```typescript
async queue(batch: MessageBatch<PostJob>, env: Env) {
  await env.DB.batch(
    batch.messages.map((m) =>
      env.DB.prepare(
        `INSERT OR IGNORE INTO failed_post_jobs
         (id, payload, failed_at) VALUES (?, ?, ?)`
      ).bind(m.id, JSON.stringify(m.body), Date.now())
    )
  );
  batch.ackAll();
}
```

DLQ messages without a consumer persist **4 days** then are
permanently deleted. Per-retry `delaySeconds` is capped at
**24 hours**.

## 3. Idempotency Key to Prevent Duplicate Processing

Mobile apps retry on timeout; Queues delivers at-least-once.
Both paths produce duplicates. The mobile client generates a
UUID per user action and sends it as `Idempotency-Key`. The
consumer collapses duplicates at D1:

```typescript
async function insertPostIdempotent(job: PostJob, env: Env) {
  const { meta } = await env.DB
    .prepare(
      `INSERT OR IGNORE INTO posts
       (id, author_id, content, created_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(job.idempotencyKey, job.authorId,
          job.content, job.createdAt)
    .run();
  if (meta.changes === 0) return; // duplicate — skip side effects
  await fanoutNotifications(job, env);
}
```

## 4. Batch Notification Fanout (Helius → Queues → Push)

A Helius webhook fires on an on-chain event that may have
thousands of mobile subscribers. Enqueue events in batches
of 100 (the `sendBatch` per-call cap); the consumer bulk-
fetches subscriber tokens and fans out in chunks of 500
(FCM/APNs limit per request):

```typescript
// producer — chunk events into sendBatch calls
for (let i = 0; i < events.length; i += 100) {
  await env.NOTIFY_QUEUE.sendBatch(
    events.slice(i, i + 100).map(
      (e) => ({ body: e, contentType: "json" })
    )
  );
}

// consumer — bulk token lookup, chunked push
async queue(batch: MessageBatch<HeliusEvent>, env: Env) {
  const ids = batch.messages.map((m) => m.body.eventId);
  const { results } = await env.DB
    .prepare(
      `SELECT push_token FROM subscriptions
       WHERE event_id IN (${ids.map(() => "?").join(",")})
       AND active = 1`
    ).bind(...ids).all<{ push_token: string }>();
  const tokens = results.map((r) => r.push_token);
  for (let i = 0; i < tokens.length; i += 500)
    await sendPushBatch(tokens.slice(i, i + 500),
                        batch.messages[0].body, env);
  batch.ackAll();
}
```

## 5. Delivery Guarantees and Key Limits

Queues is **at-least-once**. Exact-once semantics would require
global coordination incompatible with edge Worker latency
targets. Guard with three layers: stable client UUID →
`processed_jobs` table check → `INSERT OR IGNORE` in D1.

**Hard limits (verified 2026-08-17):**

| Limit | Value |
|---|---|
| Max message size | 128 KB (incl. ~100 B metadata) |
| `sendBatch` per call | 100 messages / 256 KB total |
| Consumer batch size | 100 messages |
| Queue throughput | 5,000 msg/s per queue |
| Message retention | Up to 14 days (Free plan: 24 h) |
| Max retries | 100 per message |
| Consumer concurrency | 250 concurrent invocations |
| Wall-clock per invocation | 15 minutes |
| `delaySeconds` cap | 24 hours |

For payloads over 128 KB (e.g. image bytes), store in R2 and
enqueue only the object key.

## Anti-patterns

- Running AI moderation synchronously in the mobile handler.
- Sending full image blobs in the message body (128 KB cap).
- Calling `batch.ackAll()` before all processing completes;
  exceptions after that point lose messages permanently.
- Omitting a DLQ — failed messages vanish after max retries.
- Skipping idempotency on push fanout; duplicate notifications
  erode user trust immediately.

## Gotchas

- An **unhandled exception** retries the whole batch. Use
  `msg.ack()` / `msg.retry()` per message to isolate faults.
- `max_batch_timeout` is a ceiling, not a minimum — at high
  throughput batches fill before the timer fires.
- Raising `max_concurrency` without D1 connection pooling can
  exhaust D1 write capacity.
- DLQ consumers incur billable message operations.
- `delaySeconds: 0` on `msg.retry()` bypasses queue-level
  default delays; useful for priority retry paths.

## Verification

```bash
# Confirm producer returns 202
curl -X POST https://api.example project.app/posts \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"content":"hello","authorId":"u1"}' \
  -w "%{http_code}\n" -o /dev/null    # expect: 202

wrangler tail --format=pretty post-jobs-consumer
```

D1 sanity check after consumer runs:
```sql
SELECT id, created_at FROM posts ORDER BY created_at DESC LIMIT 5;
SELECT idempotency_key FROM processed_jobs
  ORDER BY processed_at DESC LIMIT 5;
```

## Related

- `documentation/categories/cloudflare/queues-batch-processing.md`
- `documentation/categories/cloudflare/queues-dlq-patterns.md`
- `documentation/categories/cloudflare/d1-best-practices.md`
- `documentation/categories/cloudflare/r2-best-practices.md`
- `documentation/categories/cloudflare/workers-best-practices.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/platform/limits/
- https://developers.cloudflare.com/queues/configuration/batching-retries/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/reference/delivery-guarantees/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
