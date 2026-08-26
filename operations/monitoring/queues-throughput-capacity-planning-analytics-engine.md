# Queues Throughput Capacity Planning with Analytics Engine

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Queues workload that handles 50 000 messages per hour today is projected to grow 5x over the next quarter, but there is no baseline data to determine whether the current consumer concurrency and batch size configuration can absorb the increased load without unbounded lag accumulation. You need throughput, saturation, and headroom metrics to drive capacity decisions before traffic exceeds limits.

## Context

Cloudflare Queues does not expose a throughput counter or a consumer-saturation metric natively. Both must be derived from consumer-side instrumentation: the number of messages processed per batch, the wall-clock time to drain each batch, and the resulting effective messages-per-second rate. Writing these to Analytics Engine over weeks gives you a growth trend line and a saturation model. The key capacity limits are the per-queue messages-per-second send rate, the `max_batch_size` (up to 100), and the `max_concurrency` consumer setting.

## 1. Throughput Instrumentation in the Consumer

```typescript
// src/consumer.ts
export interface ConsumerEnv {
  THROUGHPUT_METRICS: AnalyticsEngineDataset;
  MY_QUEUE: Queue<JobPayload>;
}

interface JobPayload {
  enqueued_at: number;
  job_type: string;
  payload_bytes: number;
}

export default {
  async queue(
    batch: MessageBatch<JobPayload>,
    env: ConsumerEnv
  ): Promise<void> {
    const batchStart = performance.now();
    const batchSize = batch.messages.length;
    const queueName = batch.queue;
    let successCount = 0;
    let failureCount = 0;
    let totalPayloadBytes = 0;

    for (const msg of batch.messages) {
      try {
        await processMessage(msg.body);
        msg.ack();
        successCount++;
        totalPayloadBytes += msg.body.payload_bytes ?? 0;
      } catch {
        msg.retry({ delaySeconds: 30 });
        failureCount++;
      }
    }

    const drainMs = performance.now() - batchStart;
    const throughputMps =
      drainMs > 0 ? (successCount / drainMs) * 1000 : 0; // messages per second

    // Saturation index: ratio of batch_size to max_batch_size (100)
    // 1.0 = consumer is running at full batch capacity
    const saturationIndex = batchSize / 100;

    env.THROUGHPUT_METRICS.writeDataPoint({
      blobs: [queueName, saturationIndex >= 0.9 ? "saturated" : "normal"],
      doubles: [
        batchSize,
        drainMs,
        throughputMps,
        successCount,
        failureCount,
        totalPayloadBytes,
        saturationIndex,
      ],
      indexes: [queueName],
    });
  },
} satisfies ExportedHandler<ConsumerEnv>;

async function processMessage(payload: JobPayload): Promise<void> {
  // business logic placeholder
  await new Promise((resolve) => setTimeout(resolve, 5));
}
```

## 2. wrangler.toml Configuration

```toml
name = "queue-capacity-monitor"
main = "src/consumer.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "my-queue"
max_batch_size = 100
max_batch_timeout = 5          # seconds to wait for a full batch
max_retries = 3
max_concurrency = 10           # tune this based on capacity planning

[[analytics_engine_datasets]]
binding = "THROUGHPUT_METRICS"
dataset = "queue_throughput"
```

## 3. Throughput and Saturation Query

```typescript
// src/capacity-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface ThroughputRow {
  queue_name: string;
  window: string;
  avg_batch_size: number;
  p99_drain_ms: number;
  total_messages: number;
  avg_throughput_mps: number;
  peak_throughput_mps: number;
  saturation_rate_pct: number;
  failure_rate_pct: number;
}

export async function fetchThroughputStats(
  intervalHours = 24
): Promise<ThroughputRow[]> {
  const sql = `
    SELECT
      blob1 AS queue_name,
      avg(double1) AS avg_batch_size,
      quantileWeighted(0.99)(double2, 1) AS p99_drain_ms,
      sum(double4) AS total_messages,
      avg(double3) AS avg_throughput_mps,
      max(double3) AS peak_throughput_mps,
      round(100.0 * countIf(blob2 = 'saturated') / count(), 2) AS saturation_rate_pct,
      round(100.0 * sum(double5) / (sum(double4) + sum(double5)), 2) AS failure_rate_pct
    FROM queue_throughput
    WHERE timestamp > now() - INTERVAL '${intervalHours}' HOUR
    GROUP BY queue_name
    ORDER BY peak_throughput_mps DESC
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

  if (!resp.ok) throw new Error(`SQL API error: ${resp.status}`);
  const json = (await resp.json()) as { data: ThroughputRow[] };
  return json.data ?? [];
}
```

## 4. Growth Trend and Headroom Projection

```typescript
// src/capacity-projection.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface DailyTrend {
  day: string;
  queue_name: string;
  total_messages: number;
  peak_throughput_mps: number;
}

/** Return daily totals over the last 30 days for linear trend projection. */
export async function fetchDailyTrend(): Promise<DailyTrend[]> {
  const sql = `
    SELECT
      toString(toStartOfInterval(timestamp, INTERVAL '1' DAY)) AS day,
      blob1 AS queue_name,
      sum(double4) AS total_messages,
      max(double3) AS peak_throughput_mps
    FROM queue_throughput
    WHERE timestamp > now() - INTERVAL '30' DAY
    GROUP BY day, queue_name
    ORDER BY day ASC
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

  if (!resp.ok) throw new Error(`SQL API error: ${resp.status}`);
  const json = (await resp.json()) as { data: DailyTrend[] };
  return json.data ?? [];
}

/** Simple linear regression to project days until a throughput ceiling is hit. */
export function projectDaysToLimit(
  trend: DailyTrend[],
  limitMps: number
): number | null {
  if (trend.length < 2) return null;

  const xs = trend.map((_, i) => i);
  const ys = trend.map((r) => r.peak_throughput_mps);
  const n = xs.length;
  const sumX = xs.reduce((a, b) => a + b, 0);
  const sumY = ys.reduce((a, b) => a + b, 0);
  const sumXY = xs.reduce((acc, x, i) => acc + x * ys[i], 0);
  const sumX2 = xs.reduce((acc, x) => acc + x * x, 0);

  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  if (slope <= 0) return null; // not growing

  const intercept = (sumY - slope * sumX) / n;
  const currentX = n - 1;
  const daysUntilLimit = (limitMps - (slope * currentX + intercept)) / slope;
  return Math.ceil(daysUntilLimit);
}
```

## 5. Capacity Alert with Headroom Warning

```typescript
// src/capacity-alert.ts
import { fetchThroughputStats } from "./capacity-query";
import { fetchDailyTrend, projectDaysToLimit } from "./capacity-projection";

// Cloudflare Queues max send rate: 400 messages/second per queue (as of 2024)
const QUEUE_SEND_LIMIT_MPS = 400;
const SATURATION_WARN_PCT = 70; // warn when consumer batches are 70% full on average
const DAYS_TO_LIMIT_WARN = 30;  // warn if projected to hit ceiling within 30 days

export async function checkCapacityHeadroom(
  webhookUrl: string
): Promise<void> {
  const [stats, trend] = await Promise.all([
    fetchThroughputStats(24),
    fetchDailyTrend(),
  ]);

  const alerts: string[] = [];

  for (const row of stats) {
    if (row.saturation_rate_pct > SATURATION_WARN_PCT) {
      alerts.push(
        `Queue \`${row.queue_name}\` consumer saturated ${row.saturation_rate_pct}% of batches in the last 24 h`
      );
    }
    if (row.peak_throughput_mps > QUEUE_SEND_LIMIT_MPS * 0.8) {
      alerts.push(
        `Queue \`${row.queue_name}\` peak throughput ${row.peak_throughput_mps.toFixed(0)} mps is > 80% of the send-rate limit`
      );
    }
  }

  const queueTrend = trend.filter((r) => r.queue_name === "my-queue");
  const days = projectDaysToLimit(queueTrend, QUEUE_SEND_LIMIT_MPS);
  if (days !== null && days <= DAYS_TO_LIMIT_WARN) {
    alerts.push(
      `Queue \`my-queue\` is projected to hit the send-rate limit in ${days} days at current growth rate`
    );
  }

  if (alerts.length === 0) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `Queues capacity planning alert:\n${alerts.join("\n")}`,
    }),
  });
}
```

## 6. Weekly Capacity Report Query

```sql
SELECT
  toString(toStartOfInterval(timestamp, INTERVAL '1' WEEK)) AS week,
  blob1 AS queue_name,
  sum(double4) AS total_messages_processed,
  max(double3) AS peak_mps,
  avg(double7) AS avg_saturation_index,
  round(100.0 * sum(double5) / (sum(double4) + sum(double5)), 2) AS failure_rate_pct
FROM queue_throughput
WHERE timestamp > now() - INTERVAL '12' WEEK
GROUP BY week, queue_name
ORDER BY week ASC
```

## Anti-patterns

- **Measuring throughput at the producer (send rate) only**: send rate does not reflect whether the consumer keeps up; a consumer that processes 10 messages per second while the producer sends 100 per second is building invisible lag.
- **Using `max_batch_timeout` as a throughput signal**: a batch that times out before reaching `max_batch_size` means the queue is under-loaded, not over-loaded; use the saturation index (actual size / max size) instead.
- **Planning capacity against average throughput only**: queues face bursty traffic; capacity must accommodate the p99 peak, not the mean.
- **Ignoring retry amplification**: a failure rate of 5% with `max_retries = 3` means effective message throughput is 1.15x the original; factor retry-amplified traffic into ceiling projections.
- **Setting `max_concurrency` to 1 for simplicity**: single-consumer throughput is bounded by single-batch drain time; scale `max_concurrency` with observed saturation before hitting the platform send-rate limit.

## Gotchas

- Cloudflare Queues' `max_batch_size` caps at 100 messages; the `double1` saturation numerator can never exceed 100, so the saturation index is naturally bounded between 0 and 1.
- `performance.now()` in a Worker resets to 0 at each invocation start; the drain time measurement is correct only within a single `queue()` handler call.
- Analytics Engine aggregates over a minimum of 1 data point per write; a very low-traffic queue (< 1 batch per minute) may have sparse data that makes trend projection unreliable.
- Cloudflare's actual queue send-rate limit can change with plan upgrades or product updates; treat the constant in `capacity-alert.ts` as a configuration value, not a hard-coded invariant.
- The linear regression projection assumes linear growth; traffic that follows a power-law or seasonal pattern will produce misleading projections — inspect the raw trend data visually before acting on projections.

## Verification

1. Deploy the consumer Worker and send 500 messages in rapid succession to trigger saturated batches.
2. After 2 minutes, query the SQL API and confirm rows with `blob2 = 'saturated'` and `double7 >= 0.9` are present.
3. Lower `SATURATION_WARN_PCT` to `0` in the alert Worker and run it manually; confirm the webhook fires.
4. Restore the threshold, populate 7 days of synthetic trend data via test sends, and run `projectDaysToLimit` with a low limit; confirm the alert fires.
5. Confirm the weekly capacity report query returns non-empty rows grouped by week.

## Related

- `queues-consumer-lag-monitoring.md`
- `workers-queues-dead-letter-monitoring.md`
- `cloudflare-queues-async-tracing.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `capacity-planning-metrics.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/platform/limits/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
