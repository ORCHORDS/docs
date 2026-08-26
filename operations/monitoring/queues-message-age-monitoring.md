# Queues Message Age Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Messages in a Cloudflare Queue accumulate unprocessed age, but there is no built-in dashboard showing
per-message latency from enqueue to delivery. You need to detect when consumer lag exceeds SLO thresholds
before messages expire or dead-letter.

## Context
Cloudflare Queues delivers messages to a consumer Worker with at-least-once semantics. The platform
exposes a `timestamp` on each `Message` object representing when the message was enqueued. By comparing
that timestamp to `Date.now()` inside the consumer, you can compute message age at delivery time and
emit the distribution to Analytics Engine for long-term trend analysis and alerting.

---

## Section 1 — Producer: Embedding Enqueue Timestamp

The Queue message body should carry the wall-clock time at which it was produced so consumers can
reconstruct age regardless of retry count.

```typescript
// producer-worker.ts
export interface Env {
  MY_QUEUE: Queue<QueueMessage>;
  ANALYTICS: AnalyticsEngineDataset;
}

export interface QueueMessage {
  jobType: string;
  payload: unknown;
  enqueuedAt: number; // Unix ms — set by producer
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{ jobType: string; payload: unknown }>();

    const msg: QueueMessage = {
      jobType: body.jobType,
      payload: body.payload,
      enqueuedAt: Date.now(),
    };

    await env.MY_QUEUE.send(msg);

    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

Including `enqueuedAt` in the body survives retries and dead-letter re-queuing because the platform
preserves the message body unchanged. Do not rely solely on `message.timestamp` if you need
sub-second precision — platform delivery timestamps are truncated to the second.

---

## Section 2 — Consumer: Computing and Emitting Age Metrics

```typescript
// consumer-worker.ts
export interface Env {
  MY_QUEUE: Queue<QueueMessage>;
  ANALYTICS: AnalyticsEngineDataset;
}

interface QueueMessage {
  jobType: string;
  payload: unknown;
  enqueuedAt: number;
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    const now = Date.now();

    for (const message of batch.messages) {
      const ageMs = now - message.body.enqueuedAt;
      const ageSec = ageMs / 1000;

      // Emit per-message age to Analytics Engine
      env.ANALYTICS.writeDataPoint({
        blobs: [
          message.body.jobType,          // blob1: job type
          ageMs > 30_000 ? "slow" : "ok", // blob2: age classification
        ],
        doubles: [
          ageSec,                         // double1: age in seconds
          message.attempts,               // double2: delivery attempt count
        ],
        indexes: [message.body.jobType],  // index: shard by job type
      });

      // Flag messages that breached SLO (>30 s) before processing
      if (ageSec > 30) {
        console.warn(`[queue-age] SLO breach: ${message.body.jobType} age=${ageSec.toFixed(1)}s attempts=${message.attempts}`);
      }

      try {
        await processMessage(message.body);
        message.ack();
      } catch (err) {
        // Retry — message age keeps growing across retries
        message.retry();
      }
    }
  },
};

async function processMessage(msg: QueueMessage): Promise<void> {
  // business logic
  void msg;
}
```

`message.attempts` tracks retry depth. A high attempt count combined with rising age is a strong
signal that the consumer is unhealthy rather than simply slow.

---

## Section 3 — Analytics Engine SQL Queries for Age SLO

Query the `age_seconds` (double1) distribution to power dashboards and alerts.

```sql
-- P50 / P95 / P99 message age per job type over the last hour
SELECT
  blob1                                          AS job_type,
  quantileWeighted(0.50)(double1, 1)             AS p50_age_sec,
  quantileWeighted(0.95)(double1, 1)             AS p95_age_sec,
  quantileWeighted(0.99)(double1, 1)             AS p99_age_sec,
  count()                                        AS message_count
FROM workers_analytics.my_queue_consumer         -- dataset name from wrangler.toml
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY blob1
ORDER BY p99_age_sec DESC;
```

```sql
-- Messages that breached the 30-second SLO in the last 24 hours
SELECT
  blob1                                          AS job_type,
  countIf(double1 > 30)                          AS slo_breaches,
  count()                                        AS total,
  round(countIf(double1 > 30) / count() * 100, 2) AS breach_pct
FROM workers_analytics.my_queue_consumer
WHERE timestamp > now() - INTERVAL '24' HOUR
GROUP BY blob1
ORDER BY breach_pct DESC;
```

```sql
-- Rolling retry depth distribution (detect stuck consumers)
SELECT
  blob1                                          AS job_type,
  max(double2)                                   AS max_attempts,
  countIf(double2 >= 3)                          AS high_retry_count
FROM workers_analytics.my_queue_consumer
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY blob1;
```

Pair these queries with a Cloudflare Worker cron that posts to a Slack webhook when
`breach_pct > 5` or `max_attempts >= 3`.

---

## Anti-patterns
- Relying on `message.timestamp` alone for age — platform timestamps have 1-second granularity
  and do not carry over microsecond precision from the enqueue call.
- Logging age only on failure — you miss the silent accumulation of age on successful messages
  when the consumer is CPU-bound.
- Using a single Analytics Engine dataset for all job types without the `indexes` field — high
  cardinality across job types without an index degrades query speed.
- Setting a very short batch timeout with a slow consumer — the batch timeout resets per batch,
  so a slow consumer can artificially inflate per-message age in later batches.

## Gotchas
- `message.attempts` resets to 1 if you dead-letter and re-enqueue manually; only platform-managed
  retries increment `attempts` above 1.
- Analytics Engine has a 25-event-per-request write limit; flush in a `Promise.all` across the
  batch if you emit one data point per message and batch sizes are large.
- The Queue consumer's `max_retries` (default 3) means a message can sit in the retry backoff
  for up to several minutes even if the platform is healthy — factor that into your SLO budget.
- `Date.now()` inside a Worker returns the time the isolate was woken, not a true wall-clock value;
  for accurate age, include `enqueuedAt` in the message body (see Section 1).

## Verification
```bash
# Trigger a test message and watch consumer logs in real time
wrangler tail my-consumer-worker --format pretty

# Confirm Analytics Engine is receiving data
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=SELECT count() FROM workers_analytics.my_queue_consumer WHERE timestamp > now() - INTERVAL '5' MINUTE"
```

## Related
- `queues-consumer-lag-monitoring.md`
- `queues-throughput-capacity-planning-analytics-engine.md`
- `cloudflare-queues-async-tracing.md`
- `workers-queues-dead-letter-monitoring.md`
- `analytics-engine-write-limits-and-backpressure.md`

## Sources
- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/queues/reference/delivery-guarantees/
