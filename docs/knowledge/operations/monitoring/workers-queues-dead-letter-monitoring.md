# Workers Queues Dead-Letter Queue Monitoring

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Messages sent to a Cloudflare Workers Queue are silently dropped after exhausting retries: the consumer Worker throws on every delivery attempt, the platform retries up to the configured maximum, and then the message is routed to a dead-letter queue (DLQ). Operations teams have no visibility into DLQ accumulation, cannot distinguish transient retryable errors from permanent failures, and cannot alert when the DLQ depth exceeds a threshold indicating a systemic consumer bug.

---

## Context

Cloudflare Queues supports a dead-letter queue: any message that exhausts its `max_retries` attempts is forwarded to a secondary queue designated as the DLQ. The DLQ is a standard Queue binding — it has its own consumer Worker. That consumer is the only observation point for failed messages; there is no built-in dashboard showing DLQ depth or failure rate.

The DLQ consumer pattern combines three concerns:
1. **Alerting** — emit a metric immediately when a DLQ message is received so on-call engineers are paged.
2. **Inspection** — persist the failed message payload and error context to a store (R2, D1, or Logpush) for post-mortem analysis.
3. **Selective replay** — for messages whose failure was transient, re-enqueue to the original queue after human review.

Messages arrive in the DLQ consumer as a `MessageBatch` with no built-in field indicating the number of prior delivery attempts or the error that caused failure. That metadata must be carried in the message body itself (structured payload pattern).

---

## Section 1: Structured Message Payload with Retry Context

Every message sent to the primary queue should carry a `_meta` field tracking the attempt count and originating context:

```typescript
// lib/queue-message.ts
export interface QueueMessageMeta {
  messageId:   string; // caller-generated UUID
  enqueuedAt:  number; // Unix ms
  attemptCount: number; // incremented on each re-enqueue for retry tracking
  source:      string; // e.g. "order-service:checkout"
}

export interface QueueMessage<T> {
  _meta:   QueueMessageMeta;
  payload: T;
}

export function buildMessage<T>(payload: T, source: string): QueueMessage<T> {
  return {
    _meta: {
      messageId:    crypto.randomUUID(),
      enqueuedAt:   Date.now(),
      attemptCount: 0,
      source,
    },
    payload,
  };
}
```

Enqueue from a Worker:

```typescript
import { buildMessage } from "./lib/queue-message";

await env.ORDER_QUEUE.send(buildMessage(orderPayload, "checkout-worker"));
```

---

## Section 2: DLQ Consumer Worker

The DLQ consumer receives exhausted messages, emits metrics to Analytics Engine, writes the full payload to R2 for inspection, and optionally alerts via webhook:

```typescript
// dlq-consumer.ts
import type { QueueMessage } from "./lib/queue-message";

export interface Env {
  DLQ_ARCHIVE:     R2Bucket;
  ANALYTICS:       AnalyticsEngineDataset;
  ALERT_WEBHOOK_URL: string;
  PRIMARY_QUEUE:   Queue; // for selective replay
}

export default {
  async queue(batch: MessageBatch<QueueMessage<unknown>>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      await handleDeadLetter(msg, env);
      msg.ack();
    }
  },
};

async function handleDeadLetter(
  msg:  Message<QueueMessage<unknown>>,
  env:  Env,
): Promise<void> {
  const { _meta, payload } = msg.body;
  const arrivedAt = Date.now();
  const dwellMs   = arrivedAt - _meta.enqueuedAt;

  // 1. Emit metric to Analytics Engine
  env.ANALYTICS.writeDataPoint({
    blobs:   [
      "dlq_arrival",
      _meta.source,
      _meta.messageId,
      String(_meta.attemptCount),
    ],
    doubles: [dwellMs, _meta.attemptCount],
    indexes: ["dlq_event"],
  });

  // 2. Archive to R2 for post-mortem
  const archiveKey = `dlq/${_meta.source}/${_meta.messageId}-${arrivedAt}.json`;
  await env.DLQ_ARCHIVE.put(
    archiveKey,
    JSON.stringify({ _meta, payload, arrivedAt }),
    { httpMetadata: { contentType: "application/json" } },
  );

  // 3. Alert via webhook
  await fetch(env.ALERT_WEBHOOK_URL, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      summary:    `DLQ message from ${_meta.source}`,
      severity:   "high",
      messageId:  _meta.messageId,
      attempts:   _meta.attemptCount,
      dwellMs,
      archiveKey,
    }),
  }).catch((e) => {
    // Do not let webhook failure prevent ack
    console.error(JSON.stringify({ event: "dlq_alert_failed", err: String(e) }));
  });

  console.error(JSON.stringify({
    event:     "dlq_arrival",
    source:    _meta.source,
    messageId: _meta.messageId,
    attempts:  _meta.attemptCount,
    dwellMs,
    archiveKey,
  }));
}
```

---

## Section 3: wrangler.toml Configuration

```toml
name = "dlq-consumer"

[[queues.consumers]]
queue   = "order-queue-dlq"       # the DLQ queue name
max_batch_size    = 10
max_batch_timeout = 5
max_retries       = 0              # DLQ messages should NOT be retried again
dead_letter_queue = ""             # no further DLQ — log and discard

[[queues.producers]]
queue   = "order-queue"            # original queue, for selective replay
binding = "PRIMARY_QUEUE"

[[r2_buckets]]
binding    = "DLQ_ARCHIVE"
bucket_name = "dlq-archive"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "workers_queue_metrics"
```

The primary queue's `wrangler.toml` points its DLQ to `order-queue-dlq`:

```toml
[[queues.consumers]]
queue             = "order-queue"
dead_letter_queue = "order-queue-dlq"
max_retries       = 3
```

---

## Section 4: Analytics Engine Queries for DLQ Health

**DLQ arrival rate per source, last 24 hours:**

```sql
SELECT
  blob2                      AS source,
  count()                    AS dlq_count,
  avg(double1)               AS avg_dwell_ms,
  max(double2)               AS max_attempts
FROM   workers_queue_metrics
WHERE  index1 = 'dlq_event'
  AND  timestamp > now() - INTERVAL '24' HOUR
GROUP  BY source
ORDER  BY dlq_count DESC
LIMIT  20
```

**DLQ arrivals per 10-minute bucket (for rate alerting):**

```sql
SELECT
  toStartOfTenMinutes(timestamp)   AS bucket,
  count()                          AS dlq_count
FROM   workers_queue_metrics
WHERE  index1 = 'dlq_event'
  AND  timestamp > now() - INTERVAL '6' HOUR
GROUP  BY bucket
ORDER  BY bucket ASC
```

**Messages with unusually high attempt counts (indicates pathological retry cycles):**

```sql
SELECT
  blob2    AS source,
  blob3    AS message_id,
  double2  AS attempt_count,
  double1  AS dwell_ms
FROM   workers_queue_metrics
WHERE  index1    = 'dlq_event'
  AND  double2   > 5
  AND  timestamp > now() - INTERVAL '1' HOUR
ORDER  BY attempt_count DESC
LIMIT  50
```

---

## Section 5: Selective Replay from the DLQ Archive

After diagnosing the root cause of failures, replay archived messages by reading from R2 and re-enqueuing with an incremented `attemptCount`:

```typescript
// replay-tool.ts — run as a one-off Worker invocation or Cron
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { messageId } = await request.json<{ messageId: string }>();

    // Find the archived object (requires knowing the archiveKey)
    const archiveKey = new URL(request.url).searchParams.get("key");
    if (!archiveKey) return new Response("key required", { status: 400 });

    const obj = await env.DLQ_ARCHIVE.get(archiveKey);
    if (!obj) return new Response("not found", { status: 404 });

    const { _meta, payload } = await obj.json<{ _meta: any; payload: unknown }>();

    // Increment attempt count to distinguish replay from original
    const replayMessage = {
      _meta:   { ..._meta, attemptCount: _meta.attemptCount + 1, enqueuedAt: Date.now() },
      payload,
    };

    await env.PRIMARY_QUEUE.send(replayMessage);

    return Response.json({ replayed: true, messageId: _meta.messageId });
  },
};
```

---

## Section 6: Grafana Alert for DLQ Depth Spike

```yaml
# grafana/provisioning/alerts/dlq.yaml
apiVersion: 1
groups:
  - name: queues-dlq
    folder: Workers
    interval: 2m
    rules:
      - uid: dlq-arrival-spike
        title: "DLQ Arrivals > 5 in 10 min"
        condition: C
        data:
          - refId: A
            datasourceUid: cloudflare-ae
            model:
              rawSql: |
                SELECT count() AS cnt
                FROM   workers_queue_metrics
                WHERE  index1 = 'dlq_event'
                  AND  timestamp > now() - INTERVAL '10' MINUTE
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              conditions:
                - evaluator: { type: gt, params: [5] }
                  query:     { params: [A] }
        noDataState: OK
        execErrState: Alerting
        for: 0s   # alert immediately; DLQ arrivals are always urgent
        labels:
          severity: high
        annotations:
          summary: "{{ $labels.source }} sending messages to DLQ"
          runbook: "https://wiki.internal/runbooks/dlq-investigation"
```

For Slack/PagerDuty routing, attach this alert group to a contact point in Grafana configured per `cloudflare-notifications-pagerduty-webhook.md`.

---

## Anti-patterns

- **Setting `max_retries > 0` on the DLQ consumer** — this re-retries already-exhausted messages and can create a retry loop between the DLQ consumer and a second DLQ. Set `max_retries = 0` and `dead_letter_queue = ""` on the DLQ consumer.
- **Using `msg.retry()` unconditionally in the DLQ consumer** — `retry()` in the DLQ consumer re-sends to the *DLQ queue's own retry pool*, not back to the original queue. Use explicit re-enqueue to the original queue via the producer binding for intentional replay.
- **Not `ack()`-ing messages after archiving** — if `ack()` is not called, the platform will redeliver the DLQ message. The DLQ consumer should `ack()` all messages after archiving, regardless of whether the webhook alert succeeded.
- **Alerting on every individual DLQ arrival** — in a burst failure scenario, this floods the on-call channel. Use a 10-minute rate threshold (Section 6) instead of per-message alerts.
- **Storing full payload in Analytics Engine blobs** — blobs are limited to 1024 bytes per field and 1000 bytes per index value. Store payloads in R2 and store only the R2 key reference in Analytics Engine.

---

## Gotchas

- Cloudflare Queues does not expose a DLQ depth metric via the REST API or dashboard; the only visibility is through the DLQ consumer Worker itself.
- `MessageBatch.messages` contains `Message` objects; calling `batch.ackAll()` after the loop is equivalent to calling `msg.ack()` on each message — use whichever is appropriate for your error-handling logic.
- The DLQ consumer's `max_batch_timeout` should be kept short (≤5 s) to ensure alert webhook calls within the handler complete before the batch times out. Timeout causes re-delivery of the entire batch.
- R2 `put()` is eventually consistent for listing but immediately consistent for `get()` by key; replay by exact key is reliable immediately after archival.
- If the DLQ consumer itself throws and `max_retries = 0` on the DLQ consumer, the message is silently dropped by the platform. Always wrap the consumer body in a top-level try/catch and `ack()` even on error to prevent unbounded re-delivery.

```typescript
// Safe top-level handler
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await handleDeadLetter(msg as any, env);
      } catch (e) {
        console.error(JSON.stringify({ event: "dlq_handler_error", err: String(e) }));
      } finally {
        msg.ack(); // always ack — never redeliver DLQ messages
      }
    }
  },
};
```

---

## Verification

1. Deploy the primary queue consumer with `max_retries = 3` and the DLQ consumer bound to `order-queue-dlq`.
2. Send a test message to `order-queue` from a test Worker that always throws in the consumer body.
3. Wait for 3 retries to exhaust (observe via `wrangler tail` on the primary consumer).
4. Confirm the DLQ consumer receives the message: `wrangler tail dlq-consumer` shows a `dlq_arrival` log line.
5. Query Analytics Engine SQL API and verify a row with `index1 = 'dlq_event'` and correct `blob2` (source) appears.
6. Confirm the R2 archive object exists: `wrangler r2 object get dlq-archive <archiveKey>`.
7. Trigger the Grafana alert by sending 6+ failing messages within 10 minutes and verify the alert fires.

---

## Related

- `cloudflare-queues-async-tracing.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-notifications-pagerduty-webhook.md`
- `workers-tail-real-time-log-streaming.md`
- `alert-severity-levels.md`

---

## Sources

- Cloudflare Queues Dead Letter Queues: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Queues consumer configuration: https://developers.cloudflare.com/queues/configuration/configure-queues/
- R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Analytics Engine Worker binding API: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding-api/
- Queues message retries: https://developers.cloudflare.com/queues/configuration/message-retries/
