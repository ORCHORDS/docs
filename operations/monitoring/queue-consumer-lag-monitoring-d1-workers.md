# Monitoring Queue Consumer Lag in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Queues does not expose a built-in "depth" or "lag" metric. When a Queue consumer falls behind — due to downstream API slowdowns, consumer errors, or traffic spikes — messages wait longer than expected before processing. Without lag monitoring you only discover the problem when business logic starts failing or when users report stale data, by which time the queue may have thousands of unprocessed messages.

---

## Context

Each message is published with an `enqueued_at` ISO timestamp embedded in its body. The consumer Worker reads `enqueued_at` on receipt, computes the delta between enqueue time and current time, and writes one row per message to a D1 `queue_lag` table. A Cron Trigger Worker runs every hour and computes P50 and P95 lag per queue name from the rows accumulated in that hour. When P95 lag exceeds a configurable 60-second threshold the Worker posts a Slack alert with queue name, P95 value, and message count. This approach works without any Cloudflare internal APIs because all telemetry originates from data the application itself controls.

---

## Section 1 — wrangler.toml / Schema

```toml
# Producer worker — sends messages
name = "order-producer"
main = "src/producer.ts"
compatibility_date = "2025-01-01"

[[queues.producers]]
binding = "ORDER_QUEUE"
queue  = "orders"

---

# Consumer + monitor worker — consumes messages AND runs the cron
name = "order-consumer"
main = "src/consumer.ts"
compatibility_date = "2025-01-01"

[[queues.consumers]]
queue = "orders"
max_batch_size    = 100
max_batch_timeout = 5     # seconds to wait for a full batch
max_retries       = 3
dead_letter_queue = "orders-dlq"

[[d1_databases]]
binding = "DB"
database_name = "monitoring"
database_id   = "<your-d1-database-id>"

[triggers]
crons = ["0 * * * *"]  # Every hour

[vars]
SLACK_WEBHOOK_URL   = "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
QUEUE_NAME          = "orders"
LAG_THRESHOLD_MS    = "60000"   # 60 seconds in milliseconds
```

```sql
-- D1 migration: 0003_create_queue_lag.sql
CREATE TABLE IF NOT EXISTS queue_lag (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  queue_name    TEXT    NOT NULL,
  message_id    TEXT    NOT NULL UNIQUE,
  enqueued_at   INTEGER NOT NULL,   -- Unix epoch ms
  processed_at  INTEGER NOT NULL,   -- Unix epoch ms
  lag_ms        INTEGER NOT NULL,   -- processed_at - enqueued_at
  recorded_hour INTEGER NOT NULL    -- UNIX epoch seconds, truncated to hour
);

CREATE INDEX IF NOT EXISTS idx_queue_lag_queue_hour
  ON queue_lag (queue_name, recorded_hour);

CREATE INDEX IF NOT EXISTS idx_queue_lag_lag_ms
  ON queue_lag (lag_ms);
```

---

## Section 2 — Producer Worker

```typescript
// src/producer.ts
export interface Env {
  ORDER_QUEUE: Queue;
}

interface OrderMessage {
  orderId: string;
  customerId: string;
  amount: number;
  enqueued_at: string; // ISO 8601 — the lag anchor
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<Omit<OrderMessage, "enqueued_at">>();

    const message: OrderMessage = {
      ...body,
      enqueued_at: new Date().toISOString(), // injected by producer, not caller
    };

    await env.ORDER_QUEUE.send(message);

    return new Response(JSON.stringify({ queued: true }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Section 3 — Consumer + Aggregator Worker

```typescript
// src/consumer.ts
export interface Env {
  DB: D1Database;
  SLACK_WEBHOOK_URL: string;
  QUEUE_NAME: string;
  LAG_THRESHOLD_MS: string;
}

interface OrderMessage {
  orderId: string;
  customerId: string;
  amount: number;
  enqueued_at: string; // ISO 8601
}

interface QueueMessageBody {
  id: string;
  body: OrderMessage;
}

// Truncate a Unix-epoch-ms timestamp to the start of its hour (in seconds)
function toHourBucket(epochMs: number): number {
  return Math.floor(epochMs / 1000 / 3600) * 3600;
}

async function recordLagBatch(
  db: D1Database,
  queueName: string,
  messages: QueueMessageBody[]
): Promise<void> {
  const processedAt = Date.now();

  // Filter out messages that lack enqueued_at (defensive — should never happen)
  const validMessages = messages.filter(
    (m) => typeof m.body.enqueued_at === "string" && m.body.enqueued_at.length > 0
  );

  if (validMessages.length === 0) return;

  const statements = validMessages.map((m) => {
    const enqueuedAtMs = new Date(m.body.enqueued_at).getTime();
    const lagMs = processedAt - enqueuedAtMs;
    const recordedHour = toHourBucket(processedAt);

    return db
      .prepare(
        `INSERT OR IGNORE INTO queue_lag
           (queue_name, message_id, enqueued_at, processed_at, lag_ms, recorded_hour)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .bind(
        queueName,
        m.id,
        enqueuedAtMs,
        processedAt,
        lagMs,
        recordedHour
      );
  });

  // Batch insert to minimise D1 round-trips (max 100 per batch)
  const BATCH_SIZE = 100;
  for (let i = 0; i < statements.length; i += BATCH_SIZE) {
    await db.batch(statements.slice(i, i + BATCH_SIZE));
  }
}

async function processOrders(messages: OrderMessage[]): Promise<void> {
  // Placeholder for real business logic (e.g., writing to database, sending emails)
  console.log(`Processing ${messages.length} orders`);
}

interface LagRow {
  lag_ms: number;
}

interface HourStats {
  queue_name: string;
  count: number;
  p50: number;
  p95: number;
}

async function computeHourlyStats(
  db: D1Database,
  queueName: string
): Promise<HourStats | null> {
  const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
  const currentHour = toHourBucket(Date.now());

  // Fetch all lag_ms values for the previous hour bucket, sorted for percentile math
  const result = await db
    .prepare(
      `SELECT lag_ms
       FROM queue_lag
       WHERE queue_name = ? AND recorded_hour = ?
       ORDER BY lag_ms ASC`
    )
    .bind(queueName, toHourBucket((currentHour - 1) * 1000))
    .all<LagRow>();

  if (!result.results || result.results.length === 0) return null;

  const values = result.results.map((r) => r.lag_ms);
  const count = values.length;
  const p50 = percentile(values, 50);
  const p95 = percentile(values, 95);

  return { queue_name: queueName, count, p50, p95 };
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const index = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

async function maybeAlertSlack(
  webhookUrl: string,
  stats: HourStats,
  thresholdMs: number
): Promise<void> {
  if (stats.p95 <= thresholdMs) return;

  const blocks = [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: [
          `:warning: *Queue Lag Alert* — \`${stats.queue_name}\``,
          `Messages processed (last hour): *${stats.count}*`,
          `P50 lag: *${formatMs(stats.p50)}*`,
          `P95 lag: *${formatMs(stats.p95)}* (threshold: ${formatMs(thresholdMs)})`,
        ].join("\n"),
      },
    },
  ];

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });

  if (!response.ok) {
    throw new Error(`Slack webhook failed: ${response.status}`);
  }
}

async function pruneOldLagRows(db: D1Database): Promise<void> {
  // Keep 30 days of data; delete older rows to prevent unbounded growth
  const thirtyDaysAgoHour = toHourBucket(Date.now() - 30 * 24 * 60 * 60 * 1000);
  await db
    .prepare(`DELETE FROM queue_lag WHERE recorded_hour < ?`)
    .bind(thirtyDaysAgoHour)
    .run();
}

export default {
  // Queue consumer handler
  async queue(
    batch: MessageBatch<OrderMessage>,
    env: Env
  ): Promise<void> {
    const messages = batch.messages as unknown as QueueMessageBody[];

    // 1. Record lag for every message in the batch
    await recordLagBatch(env.DB, env.QUEUE_NAME, messages);

    // 2. Process the actual business logic
    await processOrders(messages.map((m) => m.body));

    // 3. Acknowledge the whole batch (Workers Queues auto-acks on handler return
    //    without exceptions; explicit ack is optional but clarifies intent)
    batch.ackAll();
  },

  // Hourly cron: aggregate stats and alert
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const thresholdMs = parseInt(env.LAG_THRESHOLD_MS ?? "60000", 10);

    const stats = await computeHourlyStats(env.DB, env.QUEUE_NAME);

    if (stats) {
      console.log(
        `Queue ${stats.queue_name}: count=${stats.count}, P50=${formatMs(stats.p50)}, P95=${formatMs(stats.p95)}`
      );
      await maybeAlertSlack(env.SLACK_WEBHOOK_URL, stats, thresholdMs);
    } else {
      console.log(`No lag data for queue ${env.QUEUE_NAME} in the previous hour.`);
    }

    await pruneOldLagRows(env.DB);
  },
};
```

---

## Anti-patterns

- **Using `Date.now()` in the producer as `enqueued_at` and also in the consumer as `processed_at` without accounting for clock skew** — Producer and consumer Workers run in different PoPs. Use ISO strings (not raw epoch integers) in the message body and parse them with `new Date(...).getTime()` in the consumer so both values are UTC-anchored and comparable.
- **Logging lag per message to the console instead of persisting to D1** — Console logs in Workers are ephemeral; `wrangler tail` does not retain them. D1 gives you a queryable, durable history for trend analysis.
- **Setting `max_batch_timeout` too high to accumulate more messages per batch** — A high `max_batch_timeout` artificially inflates lag measurements because messages wait in the runtime before the consumer handler is invoked. Keep it at 5 seconds or less.
- **Not calling `batch.ackAll()` explicitly in error-free paths** — If the handler throws, Cloudflare Queues automatically retries the batch. Ensure your `recordLagBatch` and `processOrders` logic is idempotent, or use `INSERT OR IGNORE` (as shown) to prevent duplicate lag rows on retry.

---

## Gotchas

- Cloudflare Queues delivers messages with at-least-once semantics. The `message_id` unique constraint with `INSERT OR IGNORE` is essential to prevent duplicate lag rows inflating your percentile calculations on retry.
- The `recorded_hour` index query uses `toHourBucket(currentHour - 1)` to look at the *previous* complete hour. Querying the current (incomplete) hour underestimates P95 because the tail of the distribution has not been observed yet.
- D1 row writes from `batch()` count against the D1 per-account write limit (50,000 rows/day on the free tier). At 100 messages per batch, 500 batches/day consumes 50,000 rows — the exact free-tier limit. Plan D1 tier accordingly for high-throughput queues.
- The `scheduled` handler and `queue` handler share the same Worker binary. Both are exported from the `default` export. Ensure neither handler imports large dependencies that inflate the Worker bundle size beyond the 1 MB compressed limit.
- `batch.ackAll()` is a no-op if the handler has already returned successfully; it exists for explicit partial-ack workflows using `message.ack()` and `message.retry()`.

---

## Verification

```bash
# 1. Apply the D1 migration
npx wrangler d1 execute monitoring --file=migrations/0003_create_queue_lag.sql

# 2. Deploy both producer and consumer workers
npx wrangler deploy --config wrangler.producer.toml
npx wrangler deploy --config wrangler.consumer.toml

# 3. Enqueue a test message
curl -X POST https://order-producer.example.com/ \
  -H "Content-Type: application/json" \
  -d '{"orderId":"test-001","customerId":"c-123","amount":99.99}'

# 4. Wait for the consumer to process it (~5 seconds), then query D1
npx wrangler d1 execute monitoring \
  --command "SELECT queue_name, lag_ms, datetime(processed_at/1000, 'unixepoch') FROM queue_lag ORDER BY processed_at DESC LIMIT 5"

# 5. Manually trigger the hourly cron to test stats + Slack
npx wrangler trigger scheduled --name order-consumer --cron "0 * * * *"

# 6. Verify Slack notification arrives when P95 exceeds LAG_THRESHOLD_MS
#    (simulate by inserting a fake high-lag row into D1 first)
npx wrangler d1 execute monitoring \
  --command "INSERT INTO queue_lag (queue_name, message_id, enqueued_at, processed_at, lag_ms, recorded_hour) VALUES ('orders', 'fake-001', 0, 1, 120000, $(date -d '1 hour ago' +%s) / 3600 * 3600)"
```

---

## Related

- `workers-cpu-time-monitoring-tail-workers.md`
- `r2-storage-usage-monitoring-cron-workers.md`
- `workers-error-rate-alerting-analytics-engine.md`

---

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Queues consumer configuration — https://developers.cloudflare.com/queues/reference/configuration/
- D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
