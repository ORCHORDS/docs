# Cloudflare Queues Consumer Lag Monitoring

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Messages enqueued via Cloudflare Queues are processed slower than they arrive: the queue depth grows, consumers fall behind, and business-critical jobs (email dispatch, invoice generation, webhook fan-out) are silently delayed by minutes or hours. You need a lag metric with alerting before users notice missed SLAs.

## Context

Cloudflare Queues does not expose a native consumer-lag metric or a queue-depth counter in the dashboard. Lag must be inferred by embedding an `enqueued_at` timestamp in every message body and computing the age at consumption time. Writing that age to Analytics Engine gives you a queryable time-series of consumer lag across multiple queues.

## 1. Embed Enqueue Timestamp in Message Body

```typescript
// src/producer.ts
export interface Env {
  MY_QUEUE: Queue<QueuePayload>;
}

interface QueuePayload {
  enqueued_at: number; // Unix ms
  job_type: string;
  data: unknown;
}

export async function enqueueJob(
  env: Env,
  jobType: string,
  data: unknown
): Promise<void> {
  const payload: QueuePayload = {
    enqueued_at: Date.now(),
    job_type: jobType,
    data,
  };
  await env.MY_QUEUE.send(payload);
}
```

## 2. Measure Lag at Consumption and Write to Analytics Engine

```typescript
// src/consumer.ts
export interface ConsumerEnv {
  LAG_METRICS: AnalyticsEngineDataset;
}

interface QueuePayload {
  enqueued_at: number;
  job_type: string;
  data: unknown;
}

export default {
  async queue(
    batch: MessageBatch<QueuePayload>,
    env: ConsumerEnv
  ): Promise<void> {
    const now = Date.now();

    for (const msg of batch.messages) {
      const lagMs = now - msg.body.enqueued_at;

      // Write lag metric before processing so failed jobs are still counted
      env.LAG_METRICS.writeDataPoint({
        blobs: [batch.queue, msg.body.job_type],
        doubles: [lagMs, batch.messages.length],
        indexes: [batch.queue],
      });

      try {
        await processJob(msg.body);
        msg.ack();
      } catch (err) {
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<ConsumerEnv>;

async function processJob(payload: QueuePayload): Promise<void> {
  // business logic
}
```

## 3. wrangler.toml Bindings

```toml
[[queues.consumers]]
queue = "my-queue"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3

[[analytics_engine_datasets]]
binding = "LAG_METRICS"
dataset = "queue_consumer_lag"
```

## 4. Query Current Lag via SQL API

```typescript
// src/lag-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export async function fetchQueueLag(): Promise<
  Array<{ queue: string; p99_lag_ms: number; avg_lag_ms: number }>
> {
  const sql = `
    SELECT
      blob1 AS queue_name,
      quantileWeighted(0.99)(double1, 1) AS p99_lag_ms,
      avg(double1) AS avg_lag_ms,
      max(double1) AS max_lag_ms,
      count() AS messages_processed
    FROM queue_consumer_lag
    WHERE timestamp > now() - INTERVAL '10' MINUTE
    GROUP BY queue_name
    ORDER BY p99_lag_ms DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  const json = (await resp.json()) as { data: typeof result };
  const result: Array<{ queue: string; p99_lag_ms: number; avg_lag_ms: number }> = [];
  return json.data ?? result;
}
```

## 5. Alert When Lag Exceeds SLA

```typescript
// src/lag-alert.ts
import { fetchQueueLag } from "./lag-query";

const LAG_SLO_MS: Record<string, number> = {
  "email-dispatch": 30_000,   // 30 s
  "invoice-generation": 60_000, // 60 s
  "webhook-fanout": 10_000,   // 10 s
};

export async function alertOnLag(
  env: { ALERT_WEBHOOK_URL: string }
): Promise<void> {
  const rows = await fetchQueueLag();
  const breaches = rows.filter(
    (r) => (LAG_SLO_MS[r.queue] ?? Infinity) < r.p99_lag_ms
  );

  if (breaches.length === 0) return;

  const lines = breaches.map(
    (r) =>
      `Queue \`${r.queue}\`: p99=${r.p99_lag_ms}ms > SLO=${LAG_SLO_MS[r.queue]}ms`
  );

  await fetch(env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `Queue lag SLO breach:\n${lines.join("\n")}` }),
  });
}
```

## 6. Lag Trend Over Time (Dashboard Query)

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS ts,
  blob1 AS queue_name,
  quantileWeighted(0.99)(double1, 1) AS p99_lag_ms
FROM queue_consumer_lag
WHERE timestamp > now() - INTERVAL '2' HOUR
GROUP BY ts, queue_name
ORDER BY ts ASC
```

## Anti-patterns

- **Using message `timestamp` from the envelope instead of a payload field**: the envelope timestamp reflects when the queue service received the message, not when your code enqueued it; for producer-to-consumer lag use the payload field.
- **Measuring lag only on success**: retry storms inflate lag; always write the metric before the `try` block.
- **Single global lag threshold**: different job types have different SLAs; segment by `job_type` blob.
- **Ignoring batch size**: a small batch from a deep queue does not mean low lag; `double2` (batch size) helps distinguish throughput problems from lag problems.

## Gotchas

- Cloudflare Queues delivers messages at least once; a lag spike may coincide with a retry wave, not new enqueues.
- `Date.now()` in the consumer reflects the Worker invocation time, not the message delivery time; the difference is negligible in practice but can add up under heavy batch retries.
- Analytics Engine does not support sub-second timestamps; lag values below 1 second appear as 0 in some aggregations.
- Queue names with hyphens are valid blob values; no escaping needed.

## Verification

1. Send 100 messages with `enqueued_at = Date.now() - 120_000` (simulate 2-minute lag).
2. Confirm the consumer writes data points with `double1 ≈ 120000`.
3. Run the SQL query and verify p99 ≈ 120000 ms.
4. Lower the SLO threshold to `1` ms and trigger the cron; confirm the webhook fires.

## Related

- `cloudflare-queues-async-tracing.md`
- `workers-queues-dead-letter-monitoring.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `queue-depth-monitoring.md`
- `slo-alerting-burn-rate.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
