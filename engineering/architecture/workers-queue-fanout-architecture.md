# workers-queue-fanout-architecture

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A Workers endpoint must trigger downstream work—push notifications,
emails, webhooks, analytics events—without blocking the HTTP response.
Doing it synchronously adds 200–800 ms to every request. Dropping work
on Worker timeout (30 s CPU limit) is silently lost. Mobile push
fanout to 50 k devices from a single request causes Workers CPU
exhaustion.

## Context

Cloudflare Queues provides durable, at-least-once delivery between
Workers. A producer Worker enqueues messages; a consumer Worker
processes batches asynchronously. The response to the client returns
immediately after enqueue. Failed messages can be retried or routed
to a dead-letter queue (DLQ). This pattern is the correct way to
do async fanout on the Workers platform without an external broker.

## 1. Producer-Consumer Pattern

```
HTTP request
     │
     ▼
Producer Worker ──enqueue──► Queue (durable)
     │                           │
     ▼                           ▼ (async batch)
Response 202             Consumer Worker
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 Push API  Email API  Analytics
```

Producer code — enqueue and return immediately:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.json<NotifyPayload>();
    await env.NOTIFY_QUEUE.send({
      type: "push",
      userIds: body.userIds,
      title: body.title,
      body: body.body,
      // tag deduplicates if same notification queued twice
      contentId: body.contentId,
    });
    return new Response(null, { status: 202 });
  },
};
```

Consumer code — process in batches:

```typescript
export default {
  async queue(
    batch: MessageBatch<NotifyPayload>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendPushNotification(msg.body, env);
        msg.ack();               // remove from queue
      } catch (err) {
        msg.retry({ delaySeconds: 30 });  // back-pressure retry
      }
    }
  },
};
```

## 2. Dead Letter Queue Handling

Configure a DLQ binding in `wrangler.toml` so messages that exhaust
retries land somewhere inspectable rather than being silently dropped.

```toml
[[queues.producers]]
binding = "NOTIFY_QUEUE"
queue = "notify-prod"

[[queues.consumers]]
queue = "notify-prod"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "notify-dlq"

[[queues.consumers]]
queue = "notify-dlq"
max_batch_size = 50
max_batch_timeout = 10
max_retries = 0   # DLQ consumer never re-queues
```

DLQ consumer pattern — log and alert:

```typescript
export default {
  async queue(
    batch: MessageBatch<NotifyPayload>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      // Persist for manual replay or audit
      await env.DB.prepare(
        "INSERT INTO dlq_events (payload, failed_at) VALUES (?, ?)"
      )
        .bind(JSON.stringify(msg.body), Date.now())
        .run();
      // Alert on-call if DLQ count spikes
      await env.ALERT_QUEUE.send({ dlqEvent: msg.body });
      msg.ack();
    }
  },
};
```

DLQ volume metrics to track:

```
dlq_messages_received_total   — rate over 5 min window
dlq_distinct_error_types      — categorize by error field
retry_exhausted_ratio         — dlq / (ack + dlq)
```

## 3. Mobile Push Notification Fanout

Sending to 50 k device tokens from one consumer invocation exceeds
the Workers CPU wall. Use a two-level fanout: one queue fans out
into per-platform sub-queues; platform workers batch to provider
APIs (APNs, FCM).

```
NOTIFY_QUEUE ──► fanout consumer ──► IOS_QUEUE  ──► APNs worker
                                  └─► ANDROID_QUEUE ──► FCM worker
                                  └─► WEB_QUEUE  ──► Web Push worker
```

Fanout consumer splits by platform:

```typescript
export default {
  async queue(
    batch: MessageBatch<NotifyPayload>,
    env: Env
  ): Promise<void> {
    const ios: DeviceMsg[] = [];
    const android: DeviceMsg[] = [];
    const web: DeviceMsg[] = [];

    for (const msg of batch.messages) {
      const devices = await getDeviceTokens(msg.body.userIds, env);
      for (const d of devices) {
        const entry = { token: d.token, payload: msg.body };
        if (d.platform === "ios") ios.push(entry);
        else if (d.platform === "android") android.push(entry);
        else web.push(entry);
      }
      msg.ack();
    }

    // sendBatch is atomic — all or none written
    if (ios.length) await env.IOS_QUEUE.sendBatch(
      ios.map((m) => ({ body: m }))
    );
    if (android.length) await env.ANDROID_QUEUE.sendBatch(
      android.map((m) => ({ body: m }))
    );
    if (web.length) await env.WEB_QUEUE.sendBatch(
      web.map((m) => ({ body: m }))
    );
  },
};
```

Platform queue consumer uses provider batch APIs:

```
APNs HTTP/2 allows 1 000 concurrent streams per connection.
FCM v1 does not have a batch endpoint — use Promise.all with
concurrency limited to 500 to avoid 429s.
```

## 4. Batch Processing Strategies

| Strategy            | Setting                  | When to use                      |
|---------------------|--------------------------|----------------------------------|
| Low-latency         | timeout=1s, size=10      | Webhooks, real-time side effects |
| Throughput          | timeout=30s, size=100    | Email, analytics writes          |
| Cost-optimized      | timeout=60s, size=250    | Audit logs, cold analytics       |
| DLQ replay          | size=50, retries=0       | Manual drain of failures         |

Delay delivery for scheduled notifications (max 12 hours):

```typescript
await env.NOTIFY_QUEUE.send(payload, {
  delaySeconds: secondsUntilDelivery,   // max 43 200
});
```

## 5. Idempotency on Retry

Queues guarantee at-least-once delivery. Consumer must be idempotent.

```typescript
async function sendPushNotification(
  payload: NotifyPayload,
  env: Env
): Promise<void> {
  const key = `push:sent:${payload.contentId}:${payload.userId}`;
  const already = await env.KV.get(key);
  if (already) return;           // deduplicate on retry

  await callPushProvider(payload);

  // TTL matches notification freshness window
  await env.KV.put(key, "1", { expirationTtl: 86_400 });
}
```

## Anti-Patterns

- **Sending per-device from the producer Worker** — saturates CPU;
  always fan out through a queue.
- **Using KV for queue state** — KV is eventually consistent and not
  a FIFO queue; messages can appear out-of-order or not at all under
  cache inconsistency windows.
- **Acking before side effects complete** — if ack is called and the
  push API call throws, the message is gone with no retry.
- **Unlimited retries without exponential delay** — hammers a
  degraded provider; always set `delaySeconds` in `msg.retry()`.
- **One queue for all fanout types** — prevents per-type tuning of
  batch size, retry, and DLQ; segment by workload category.

## Gotchas

- `sendBatch` on the producer is transactional within the call but
  there is no cross-queue transaction; partial fanout is possible if
  the worker crashes between `sendBatch` calls.
- `max_batch_timeout` clock starts when the first message arrives,
  not when the batch is full—tune accordingly.
- Consumer Workers have a 15-minute wall clock limit, not the
  30-second CPU limit of HTTP Workers; long provider calls are safe.
- Message body max size is 128 KB; large payloads should store data
  in R2/D1 and enqueue only a reference ID.
- FCM tokens rotate; stale token 404s should remove the token from
  the database, not retry.

## Verification

```bash
# Tail consumer invocations
wrangler tail notify-consumer --format pretty

# Check DLQ depth (use Cloudflare dashboard or REST API)
curl -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/queues"

# Smoke test enqueue
curl -X POST https://your-worker.example.com/notify \
  -H "Content-Type: application/json" \
  -d '{"userIds":["u1"],"title":"Test","body":"Hello","contentId":"c1"}'
# Expected: HTTP 202
```

## Related

- `documentation/categories/architecture/dead-letter-queue-architecture.md`
- `documentation/categories/architecture/workers-do-websocket-architecture.md`
- `documentation/categories/architecture/at-least-once-delivery.md`
- `documentation/categories/architecture/idempotency-design.md`
- `documentation/categories/architecture/backpressure-patterns.md`

## Source URLs

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/queues/reference/batch-messages/
- https://developers.cloudflare.com/queues/examples/send-errors-to-dead-letter-queue/
