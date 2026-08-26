# Competing Consumers: Workers + Queues Concurrency

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single Consumer Worker can't keep up with queue depth during traffic spikes. You want horizontal scale-out: multiple concurrent consumer instances pulling from the same queue, each processing a separate batch, without double-processing the same message.

## Context

Cloudflare Queues handles consumer distribution automatically — you do not run multiple queue bindings or manage assignment yourself. The platform spawns up to `max_concurrency` Consumer Worker instances simultaneously. Your responsibility is:

1. Configuring `max_concurrency` to match your downstream capacity.
2. Writing **idempotent** consumers so at-least-once delivery doesn't produce duplicates.
3. Observing throughput vs queue depth via Analytics Engine to tune the setting.

## Competing Consumer Implementation

```typescript
// consumer-worker/index.ts
import type { MessageBatch, Message } from '@cloudflare/workers-types';

interface JobMessage {
  job_id: string;
  payload: unknown;
}

export default {
  async queue(batch: MessageBatch<JobMessage>, env: Env): Promise<void> {
    // Process messages concurrently within the batch
    await Promise.allSettled(
      batch.messages.map((msg) => processWithDedup(msg, env))
    );
  },
};

async function processWithDedup(
  msg: Message<JobMessage>,
  env: Env,
): Promise<void> {
  const { job_id, payload } = msg.body;

  // --- Idempotency check via D1 processed_ids table ---
  const existing = await env.DB.prepare(
    'SELECT 1 FROM processed_ids WHERE job_id = ?1 LIMIT 1',
  ).bind(job_id).first();

  if (existing) {
    // Already processed — ack and move on
    msg.ack();
    return;
  }

  try {
    await doWork(payload, env);  // domain-specific processing

    // Record as processed atomically before acking
    await env.DB.prepare(
      'INSERT OR IGNORE INTO processed_ids (job_id, processed_at) VALUES (?1, ?2)',
    ).bind(job_id, new Date().toISOString()).run();

    msg.ack();
  } catch (err) {
    console.error(`job ${job_id} failed:`, err);
    msg.retry({ delaySeconds: 30 });  // exponential back-off caller-side
  }
}

// Analytics Engine write — one datapoint per batch for throughput tracking
async function recordMetrics(
  env: Env,
  batchSize: number,
  durationMs: number,
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs:   ['consumer-worker'],
    doubles: [batchSize, durationMs],
    indexes: ['queue-throughput'],
  });
}
```

## D1 Schema for Deduplication

```sql
CREATE TABLE processed_ids (
  job_id       TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
-- Prune rows older than your idempotency window (cron job / scheduled Worker)
CREATE INDEX idx_processed_ids_ts ON processed_ids (processed_at);
```

## Wrangler Configuration

```jsonc
// wrangler.jsonc
{
  "name": "consumer-worker",
  "queues": {
    "consumers": [
      {
        "queue": "jobs-queue",
        "max_batch_size":    25,
        "max_batch_timeout": 5,
        "max_retries":       3,
        "dead_letter_queue": "jobs-dlq",
        "max_concurrency":   10   // <-- key setting: up to 10 parallel instances
      }
    ]
  },
  "d1_databases": [{ "binding": "DB", "database_name": "jobs-db", "database_id": "..." }],
  "analytics_engine_datasets": [{ "binding": "ANALYTICS", "dataset": "worker-metrics" }]
}
```

## Monitoring Throughput vs Queue Depth

```sql
-- Analytics Engine SQL API query (run via /v4/{account_id}/analytics_engine/sql)
SELECT
  toStartOfMinute(timestamp)               AS minute,
  SUM(double1)                             AS messages_processed,
  AVG(double2)                             AS avg_duration_ms
FROM worker_metrics
WHERE
  blob1 = 'consumer-worker'
  AND timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY minute
ORDER BY minute DESC;
```

Compare `messages_processed` against Queues' `numMessagesDelayed` metric in the dashboard. If queue depth grows despite `max_concurrency = 10`, increase it or reduce per-message work.

## At-Least-Once vs Exactly-Once

| Guarantee | What it means | Your job |
|---|---|---|
| **At-least-once** (Queues default) | Every message is delivered at least once; retries and duplicates are possible | Write idempotent consumers using `processed_ids` |
| **Exactly-once processing** | No built-in; must be constructed | Combine at-least-once delivery + idempotent DB insert (`INSERT OR IGNORE`) |

Queues does **not** offer exactly-once delivery. Exactly-once *processing* is achievable by making the side-effect (the D1 write) idempotent.

## Anti-patterns

- **Shared mutable state between instances** — Workers share nothing; don't assume instance A's in-memory cache is visible to instance B.
- **Acking before the side-effect commits** — if the D1 write fails after an early `msg.ack()`, the message is lost.
- **Setting `max_concurrency` too high** — each instance holds a D1 connection; excessive concurrency saturates D1's connection pool. Start at 10, profile, then scale.
- **Unbounded `processed_ids` table** — add a scheduled Worker to `DELETE FROM processed_ids WHERE processed_at < datetime('now', '-24 hours')`.

## Gotchas

- `msg.retry({ delaySeconds })` requires Queues' retry delay feature — confirm your account plan supports it.
- `Promise.allSettled` (not `Promise.all`) inside the queue handler prevents one failed message from aborting the entire batch.
- `max_concurrency` is per-queue binding, not per-Worker script — a Worker with two queue bindings can have different concurrency on each.
- Changing `max_concurrency` in `wrangler.jsonc` takes effect on the next `wrangler deploy`; there is no hot-reload.

## Verification

```bash
# Flood the queue with 500 test messages
for i in $(seq 1 500); do
  wrangler queues send jobs-queue "{\"job_id\":\"job-$i\",\"payload\":{\"n\":$i}}"
done

# Watch consumer count in real time
wrangler tail consumer-worker --format json | jq '.outcome'

# Confirm dedup: send the same job_id twice, check D1 has one row
wrangler d1 execute jobs-db \
  --command "SELECT COUNT(*) FROM processed_ids WHERE job_id='job-1'"
```

## Related

- `fan-in-aggregation-workers-queues-d1.md`
- `async-request-reply-workers-durable-objects.md`
- Cloudflare Queues — Consumer Concurrency docs
- Analytics Engine SQL API

## Sources

- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/queues/reference/delivery-guarantees/
