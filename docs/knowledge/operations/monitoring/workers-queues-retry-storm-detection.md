# Workers Queues Retry Storm Detection

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Queues consumer begins failing — downstream database unavailable, an API returning
500s, a schema mismatch — and Cloudflare's automatic retry with exponential backoff
re-enqueues messages repeatedly. If the failure persists, message retry counts
accumulate, the queue backlog grows, and eventually messages overflow into the
dead-letter queue or are dropped when the 97-hour retention window expires.
You need to detect this amplification early, before messages are lost and before the
retry backlog causes capacity issues in the consumer.

## Context

Cloudflare Queues retries failed messages up to the `maxRetries` value (default 3,
maximum 100) with exponential backoff up to the `retryDelay` maximum. Each retry
re-enqueues the message, making it indistinguishable from new work in the consumer's
`batch` parameter — the message is not tagged with its original enqueue timestamp by
default. Tail Workers can observe per-invocation queue metadata (batch size, message
count) and error outcomes. Analytics Engine captures these signals for trending.
This article covers detecting retry amplification: the ratio of consumer failures to
consumer successes rising without a corresponding rise in new producer throughput.

Existing articles cover dead-letter queue monitoring (`workers-queues-dead-letter-monitoring`)
and consumer lag (`queues-consumer-lag-monitoring`). This article focuses specifically
on the retry-storm signature and early-warning alerting before dead-letter overflow.

---

## Embedding retry metadata in messages at produce time

```typescript
// src/producer.ts
interface QueueMessage<T> {
  payload: T;
  producedAt: number;   // Unix ms — lets consumer detect messages aged > maxRetry window
  attemptHint: number;  // 0 on first send; consumer increments and re-enqueues manually
                        // for observability (Cloudflare does not expose internal retry count)
}

export async function enqueue<T>(queue: Queue, payload: T): Promise<void> {
  const msg: QueueMessage<T> = { payload, producedAt: Date.now(), attemptHint: 0 };
  await queue.send(msg);
}
```

## Consumer — tracking per-message attempt counts

```typescript
// src/consumer.ts
export default {
  async queue(batch: MessageBatch<QueueMessage<unknown>>, env: Env): Promise<void> {
    const batchStart = Date.now();
    let successCount = 0;
    let failCount = 0;

    for (const msg of batch.messages) {
      const { payload, producedAt, attemptHint } = msg.body;
      const ageMs = Date.now() - producedAt;

      try {
        await processMessage(payload, env);
        msg.ack();
        successCount++;

        env.AE.writeDataPoint({
          blobs:   ["success", batch.queue],
          doubles: [1, attemptHint, ageMs],
          indexes: [env.SERVICE_NAME],
        });
      } catch (err) {
        failCount++;
        // Re-enqueue with incremented attemptHint for observability
        if (attemptHint < 10) {
          await env.SELF_QUEUE.send({ payload, producedAt, attemptHint: attemptHint + 1 });
        }
        msg.ack(); // ack to control retry ourselves; or use msg.retry() for platform retries

        env.AE.writeDataPoint({
          blobs:   ["failure", batch.queue],
          doubles: [1, attemptHint, ageMs],
          indexes: [env.SERVICE_NAME],
        });
      }
    }

    // Emit batch-level summary for storm detection
    env.AE.writeDataPoint({
      blobs:   ["batch_summary", batch.queue],
      doubles: [successCount, failCount, batch.messages.length, Date.now() - batchStart],
      indexes: ["queue_batch"],
    });
  },
};
```

## Analytics Engine query — detecting retry-storm signature

```sql
-- Retry storm: failure ratio rising AND avg attemptHint > 2 in the same window
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE)  AS bucket,
  blob2                                               AS queue_name,
  countIf(blob1 = 'failure')                          AS failures,
  countIf(blob1 = 'success')                          AS successes,
  countIf(blob1 = 'failure') / count()                AS failure_ratio,
  avg(if(blob1 = 'failure', double2, null))           AS avg_attempt_hint_on_failure
FROM MY_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '30' MINUTE
  AND index1 = 'checkout-service'
GROUP BY bucket, queue_name
ORDER BY bucket DESC;
```

A retry storm manifests as `failure_ratio > 0.7` AND `avg_attempt_hint_on_failure > 2`
sustained for 2+ consecutive 5-minute buckets.

## Cron-based storm alerting

```typescript
// src/storm-alert.ts — runs every 5 minutes via cron trigger
export async function detectRetryStorm(env: Env): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: JSON.stringify({
        query: `
          SELECT
            countIf(blob1 = 'failure') AS failures,
            count()                    AS total,
            avg(double2)               AS avg_attempt
          FROM MY_AE_DATASET
          WHERE timestamp >= NOW() - INTERVAL '10' MINUTE
            AND index1 = ?
            AND blob1 IN ('success', 'failure')
        `,
        parameters: [env.SERVICE_NAME],
      }),
    }
  );

  const { data } = await res.json<{ data: Array<{ failures: number; total: number; avg_attempt: number }> }>();
  if (!data.length || data[0].total < 20) return;

  const { failures, total, avg_attempt } = data[0];
  const ratio = failures / total;

  if (ratio > 0.7 && avg_attempt > 2) {
    await env.PAGERDUTY_QUEUE.send({
      severity: "critical",
      summary: `Retry storm on ${env.SERVICE_NAME}: ${(ratio * 100).toFixed(1)}% failure rate, avg attempt ${avg_attempt.toFixed(1)}`,
      dedup_key: `retry-storm-${env.SERVICE_NAME}`,
    });
  }
}
```

## Tail Worker — real-time batch failure rate monitoring

```typescript
// tail/src/index.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptName !== "queue-consumer") continue;
      if (event.outcome === "exception") {
        // Entire batch failed (consumer threw unhandled error)
        env.AE.writeDataPoint({
          blobs:   ["batch_exception", "queue-consumer"],
          doubles: [1],
          indexes: ["tail_queue"],
        });
      }
    }
  },
};
```

Unhandled batch exceptions cause Cloudflare to retry the entire batch, which is
the most dangerous form of retry storm. Track `batch_exception` rate separately
from per-message failures.

---

## Anti-patterns

- **Using `msg.retry()` inside a catch block without a max-attempt guard**: this
  delegates retry count tracking to Cloudflare's internal counter which you cannot
  observe. If the consumer keeps throwing, messages silently exhaust retries and
  reach the dead-letter queue without observable escalation.
- **Setting `maxRetries` to 100 without alerting on dead-letter rate**: high retry
  limits delay the visible signal by hours while the storm amplifies.
- **Alerting only on dead-letter overflow**: by the time messages reach the dead-letter
  queue, the storm has already been running for the full retry window. Alert on
  failure ratio first.

## Gotchas

- Cloudflare Queues does not expose the platform-internal retry count to the consumer
  in `msg.body`; you must embed attempt tracking in the message payload itself if you
  need to observe it.
- The `batch.messages` array during a retry may be smaller than the original batch if
  some messages were acked; do not assume batch size equals original enqueue count.
- `msg.ack()` after manually re-enqueuing to `SELF_QUEUE` requires the queue binding
  to exist in `wrangler.toml` and the consumer's outbound queue permission to include it.
- Analytics Engine `writeDataPoint` inside a queue consumer counts against the Worker's
  subrequest budget (1000 per invocation). On large batches, batch the writes.

## Verification

```bash
# Check dead-letter queue depth — rising DLQ is a lagging indicator of a storm
wrangler queues consumer list my-dlq

# Directly query AE for failure ratio over last 15 minutes
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT countIf(blob1='"'"'failure'"'"') AS f, count() AS t, f/t AS ratio FROM MY_AE_DATASET WHERE timestamp >= NOW() - INTERVAL '"'"'15'"'"' MINUTE AND index1='"'"'checkout-service'"'"'"}' \
  | jq '{failures: .data[0].f, total: .data[0].t, ratio: .data[0].ratio}'
```

Expected during normal operation: `ratio < 0.05`. Above 0.5 sustained is a storm.

## Related

- `workers-queues-dead-letter-monitoring.md`
- `queues-consumer-lag-monitoring.md`
- `queues-message-age-monitoring.md`
- `queues-throughput-capacity-planning-analytics-engine.md`
- `tail-worker-structured-error-classification-d1.md`

## Sources

- Cloudflare Queues retry and dead-letter: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Cloudflare Queues consumer configuration: https://developers.cloudflare.com/queues/reference/configuration/
- Analytics Engine writeDataPoint: https://developers.cloudflare.com/analytics/analytics-engine/
